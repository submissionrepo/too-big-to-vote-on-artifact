// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";

interface IVotingBlock {
    struct PendingRequestAncillary {
        bytes32 identifier;
        uint256 time;
        bytes ancillaryData;
    }

    struct RequestState {
        uint8 status; // 0 NotRequested, 1 Active, 2 Resolved, 3 Future, 4 ToDelete
        uint32 lastVotingRound;
    }

    function getPriceRequestStatuses(PendingRequestAncillary[] memory requests) external view returns (RequestState[] memory);

    function commitVote(bytes32 identifier, uint256 time, bytes memory ancillaryData, bytes32 hash) external;

    function revealVote(bytes32 identifier, uint256 time, int256 price, bytes memory ancillaryData, int256 salt) external;

    function getVoterStakePostUpdate(address voter) external returns (uint128);

    function voterStakes(address voter)
        external
        view
        returns (uint128, uint128, uint128, uint128, int128, uint64, uint64, address);

    function processResolvablePriceRequests() external;
}

interface IAdapterBlock {
    function ready(bytes32 questionID) external view returns (bool);

    function resolve(bytes32 questionID) external;

    function flag(bytes32 questionID) external;

    function isFlagged(bytes32 questionID) external view returns (bool);

    function resolveManually(bytes32 questionID, uint256[] calldata payouts) external;
}

interface ICTFBlock {
    function payoutNumerators(bytes32 conditionId, uint256 index) external view returns (uint256);

    function payoutDenominator(bytes32 conditionId) external view returns (uint256);
}

interface IERC20Block {
    function balanceOf(address who) external view returns (uint256);
}

/// A coalition of the four largest voters blocks a payout vote until the DVM deletes it, on forks of both chains.
///
/// Ethereum (fork at the last block of round 10314's commit phase): the four largest voters on "Will Donald Trump
/// publicly insult someone on June 21, 2026?" re-commit "Yes" and reveal it inside their historical multicalls; every
/// other reveal is replayed as it happened, so the round rolls. In each later round the test constructs the same vote:
/// every voter of round 10314 commits and reveals the answer it revealed there, from the same sender, with a fresh salt.
/// These later rounds are constructed, not replayed. The live VotingV2 rolls the request until it deletes it.
///
/// Polygon (fork at the block before the historical delivery of the price): with no price ever to arrive, the live
/// adapter cannot resolve the question and the market's collateral stays locked; an administrator of the adapter can
/// flag the question and, an hour later, pay any vector it chooses. Fixture: build_block_fixture.py.
/// Run with FORK_URL and POLYGON_URL; skipped otherwise.
contract BlockToDeletionForkTest is Test {
    IVotingBlock constant VOTING = IVotingBlock(0x004395edb43EFca9885CEdad51EC9fAf93Bd34ac);
    IAdapterBlock constant ADAPTER = IAdapterBlock(0x65070BE91477460D8A7AeEb94ef92fe056C2f2A7);
    ICTFBlock constant CTF = ICTFBlock(0x4D97DCd97eC945f40cF65F87097ACe5EA0476045);
    IERC20Block constant USDCE = IERC20Block(0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174);
    uint256 constant ROUND = 172_800;
    bytes32 constant ROLLED = keccak256("RequestRolled(bytes32,uint256,bytes,uint32)");
    bytes32 constant DELETED = keccak256("RequestDeleted(bytes32,uint256,bytes,uint32)");

    string json;
    bytes32 identifier;
    uint256 time;
    bytes anc;

    function _skip() internal returns (bool) {
        if (bytes(vm.envOr("FORK_URL", string(""))).length == 0 || bytes(vm.envOr("POLYGON_URL", string(""))).length == 0) {
            emit log("FORK_URL or POLYGON_URL not set; skipping");
            return true;
        }
        return false;
    }

    function _status() internal view returns (uint8 status, uint32 round) {
        IVotingBlock.PendingRequestAncillary[] memory q = new IVotingBlock.PendingRequestAncillary[](1);
        q[0] = IVotingBlock.PendingRequestAncillary(identifier, time, anc);
        IVotingBlock.RequestState memory s = VOTING.getPriceRequestStatuses(q)[0];
        return (s.status, s.lastVotingRound);
    }

    function replayOne(uint256 k, bool capture, address from, address to, uint256 blk, uint256 ts) external {
        bytes memory input =
            vm.readFileBinary(string.concat("fixtures/block/", capture ? "dev_" : "in_", vm.toString(k), ".bin"));
        vm.roll(blk);
        vm.warp(ts);
        vm.prank(from, from);
        (bool ok, ) = to.call(input);
        require(ok, "replayed reveal reverted");
    }

    function _salt(address voter, uint256 roundId) internal pure returns (int256) {
        return int256(uint256(keccak256(abi.encode(voter, roundId))) >> 2);
    }

    function commitOne(address voter, address caller, int256 price, uint256 roundId) external {
        bytes32 h = keccak256(abi.encodePacked(price, _salt(voter, roundId), voter, time, anc, roundId, identifier));
        vm.prank(caller, caller);
        VOTING.commitVote(identifier, time, anc, h);
    }

    function revealOne(address voter, address caller, int256 price, uint256 roundId) external {
        vm.prank(caller, caller);
        VOTING.revealVote(identifier, time, price, anc, _salt(voter, roundId));
    }

    function test_four_largest_block_until_deletion() public {
        if (_skip()) return;
        json = vm.readFile("fixtures/block_meta.json");
        identifier = vm.parseJsonBytes32(json, ".identifier");
        time = vm.parseJsonUint(json, ".time");
        anc = vm.parseJsonBytes(json, ".ancillaryData");
        uint256 round0 = vm.parseJsonUint(json, ".roundId");

        // ---- Ethereum: the replayed round, with the four largest voting Yes
        vm.createSelectFork(vm.envString("FORK_URL"), vm.parseJsonUint(json, ".ethForkBlock"));
        address[] memory coalition = vm.parseJsonAddressArray(json, ".coalitionVoters");
        uint256 stakeBefore;
        for (uint256 i = 0; i < coalition.length; i++) {
            (uint128 s, , , , , , , ) = VOTING.voterStakes(coalition[i]);
            stakeBefore += s;
        }
        {
            address[] memory senders = vm.parseJsonAddressArray(json, ".commitSenders");
            bytes[] memory commits = vm.parseJsonBytesArray(json, ".commitInputs");
            for (uint256 i = 0; i < senders.length; i++) {
                vm.prank(senders[i], senders[i]);
                (bool ok, ) = address(VOTING).call(commits[i]);
                require(ok, "re-commit reverted");
            }
            address[] memory froms = vm.parseJsonAddressArray(json, ".froms");
            address[] memory tos = vm.parseJsonAddressArray(json, ".tos");
            uint256[] memory blocks = vm.parseJsonUintArray(json, ".blocks");
            uint256[] memory stamps = vm.parseJsonUintArray(json, ".timestamps");
            for (uint256 k = 0; k < froms.length; k++) this.replayOne(k, true, froms[k], tos[k], blocks[k], stamps[k]);
            vm.roll(blocks[froms.length - 1] + 300);
        }
        vm.recordLogs();
        vm.warp((round0 + 1) * ROUND + 60);
        VOTING.processResolvablePriceRequests();
        (uint8 st, uint32 lr) = _status();
        emit log_named_uint("after the replayed round: status (1 = active, rolled)", st);
        emit log_named_uint("  next voting round", lr);
        assertEq(st, 1);

        // ---- constructed rounds: the same electorate votes the same answers until the request is deleted
        address[] memory voters = vm.parseJsonAddressArray(json, ".allVoters");
        address[] memory callers = vm.parseJsonAddressArray(json, ".allCallers");
        int256[] memory prices = vm.parseJsonIntArray(json, ".allPrices");
        uint256 rounds;
        uint256 r = round0 + 1;
        while (st == 1 && rounds < 8) {
            vm.warp(r * ROUND + 60);
            vm.roll(block.number + 7200);
            for (uint256 i = 0; i < voters.length; i++) {
                try this.commitOne(voters[i], callers[i], prices[i], r) {} catch {}
            }
            vm.warp(r * ROUND + ROUND / 2 + 60);
            vm.roll(block.number + 7200);
            for (uint256 i = 0; i < voters.length; i++) {
                try this.revealOne(voters[i], callers[i], prices[i], r) {} catch {}
            }
            vm.warp((r + 1) * ROUND + 60);
            vm.roll(block.number + 7200);
            VOTING.processResolvablePriceRequests();
            (st, lr) = _status();
            rounds++;
            emit log_named_uint(string.concat("constructed round ", vm.toString(r), ": status"), st);
            r++;
        }
        Vm.Log[] memory logs = vm.getRecordedLogs();
        uint256 nRolled;
        uint256 nDeleted;
        for (uint256 i = 0; i < logs.length; i++) {
            if (logs[i].emitter != address(VOTING)) continue;
            if (logs[i].topics[0] == ROLLED && logs[i].topics[1] == identifier) nRolled++;
            if (logs[i].topics[0] == DELETED && logs[i].topics[1] == identifier) nDeleted++;
        }
        emit log_named_uint("RequestRolled events for this identifier", nRolled);
        emit log_named_uint("RequestDeleted events for this identifier", nDeleted);
        assertTrue(st != 1 && st != 2, "request neither deleted nor still pending");
        uint256 stakeAfter;
        for (uint256 i = 0; i < coalition.length; i++) stakeAfter += VOTING.getVoterStakePostUpdate(coalition[i]);
        emit log_named_decimal_uint("coalition stake before (UMA)", stakeBefore, 18);
        emit log_named_decimal_uint("coalition stake after deletion (UMA)", stakeAfter, 18);

        // ---- Polygon: no price will arrive; only the adapter's administrator can settle the market
        vm.createSelectFork(vm.envString("POLYGON_URL"), vm.parseJsonUint(json, ".polygonForkBlock"));
        bytes32 questionID = vm.parseJsonBytes32(json, ".questionID");
        bytes32 conditionId = vm.parseJsonBytes32(json, ".conditionId");
        assertFalse(ADAPTER.ready(questionID));
        vm.expectRevert();
        ADAPTER.resolve(questionID);
        assertEq(CTF.payoutDenominator(conditionId), 0);
        address admin = vm.parseJsonAddress(json, ".admin");
        vm.prank(admin);
        ADAPTER.flag(questionID);
        assertTrue(ADAPTER.isFlagged(questionID));
        uint256[] memory payouts = new uint256[](2);
        payouts[0] = 0;
        payouts[1] = 1;
        vm.prank(admin);
        vm.expectRevert();
        ADAPTER.resolveManually(questionID, payouts);
        vm.warp(block.timestamp + 3601);
        vm.prank(admin);
        ADAPTER.resolveManually(questionID, payouts);
        emit log_named_uint("payout denominator after the administrator settles", CTF.payoutDenominator(conditionId));
        assertEq(CTF.payoutNumerators(conditionId, 1), 1);
    }
}
