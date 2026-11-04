// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";

interface IVotingV2Fork {
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

    function getPrice(bytes32 identifier, uint256 time, bytes memory ancillaryData) external view returns (int256);

    function getVoterStakePostUpdate(address voter) external returns (uint128);

    function voterStakes(address voter)
        external
        view
        returns (uint128, uint128, uint128, uint128, int128, uint64, uint64, address);
}

interface IOracleRootTunnel {
    function publishPrice(bytes32 identifier, uint256 time, bytes memory ancillaryData) external;
}

interface IFxChild {
    function onStateReceive(uint256 stateId, bytes calldata data) external;
}

interface IUmaCtfAdapterFork {
    function resolve(bytes32 questionID) external;

    function ready(bytes32 questionID) external view returns (bool);
}

interface ICTFFork {
    function payoutNumerators(bytes32 conditionId, uint256 index) external view returns (uint256);

    function payoutDenominator(bytes32 conditionId) external view returns (uint256);

    function balanceOf(address owner, uint256 id) external view returns (uint256);

    function redeemPositions(address collateralToken, bytes32 parentCollectionId, bytes32 conditionId, uint256[] calldata indexSets)
        external;
}

interface IERC20Fork {
    function balanceOf(address who) external view returns (uint256);
}

interface IManagedOO {
    function settle(address requester, bytes32 identifier, uint256 timestamp, bytes memory ancillaryData)
        external
        returns (uint256);
}

/// The capture of "Israel x Hezbollah ceasefire by April 18, 2026?" replayed on forks of both chains.
///
/// Ethereum (fork at the last block of round 10281's commit phase): in the capture run, the round's 19 largest voters
/// on this request re-commit "No" from their own senders, reusing their historical salts; then every historical reveal
/// transaction that revealed this request is replayed with its sender, block and timestamp, the 19 voters' with this
/// request's price word set to "No" and everything else unchanged. In the baseline run nothing is changed. After the
/// round, the live VotingV2 resolves the request, and the live OracleRootTunnel publishes the price; we keep the
/// state-sync message it emits.
///
/// Polygon (fork at the block before the historical price delivery): the only simulated step is the bridge's system
/// call, which hands the message to the live FxChild exactly as Polygon validators would. The live child tunnel, managed
/// optimistic oracle, Polymarket adapter and conditional-token contract then settle the market, and the market's largest
/// "No" holders redeem. Fixture: build_ceasefire_fixture.py (ceasefire_meta.json and one calldata file per transaction). Run with FORK_URL (Ethereum archive) and POLYGON_URL
/// (Polygon archive); skipped otherwise.
contract CeasefireCaptureForkTest is Test {
    IVotingV2Fork constant VOTING = IVotingV2Fork(0x004395edb43EFca9885CEdad51EC9fAf93Bd34ac);
    IOracleRootTunnel constant ROOT_TUNNEL = IOracleRootTunnel(0x9B40E25dDd4518F36c50ce8AEf53Ee527419D55d);
    address constant STATE_SENDER = 0x28e4F3a7f651294B9564800b2D01f35189A5bFbE;
    IFxChild constant FX_CHILD = IFxChild(0x8397259c983751DAf40400790063935a11afa28a);
    address constant SYSTEM = 0x0000000000000000000000000000000000001001;
    IUmaCtfAdapterFork constant ADAPTER = IUmaCtfAdapterFork(0x65070BE91477460D8A7AeEb94ef92fe056C2f2A7);
    ICTFFork constant CTF = ICTFFork(0x4D97DCd97eC945f40cF65F87097ACe5EA0476045);
    IERC20Fork constant USDCE = IERC20Fork(0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174);
    bytes32 constant STATE_SYNCED = keccak256("StateSynced(uint256,address,bytes)");
    IManagedOO constant OO = IManagedOO(0x2C0367a9DB231dDeBd88a94b4f6461a6e47C58B1);
    bytes32 constant YES_OR_NO = "YES_OR_NO_QUERY";
    // settle() on the managed oracle is restricted to RESOLVER_ROLE; this holder settled the request on chain
    address constant RESOLVER = 0x9725e8172A108f2BaD87ef31eA4Ea729e939d869;

    string json;

    struct EthResult {
        uint8 status;
        int256 price;
        uint256 stateId;
        bytes message;
        uint256 coalitionStakeBefore;
        uint256 coalitionStakeAfter;
        uint256 fallbacks;
    }

    function _skip() internal returns (bool) {
        if (bytes(vm.envOr("FORK_URL", string(""))).length == 0 || bytes(vm.envOr("POLYGON_URL", string(""))).length == 0) {
            emit log("FORK_URL or POLYGON_URL not set; skipping");
            return true;
        }
        return false;
    }

    function _ethereum(bool capture) internal returns (EthResult memory r) {
        json = vm.readFile("fixtures/ceasefire_meta.json");
        vm.createSelectFork(vm.envString("FORK_URL"), vm.parseJsonUint(json, ".ethForkBlock"));
        address[] memory coalition = vm.parseJsonAddressArray(json, ".coalitionVoters");
        for (uint256 i = 0; i < coalition.length; i++) {
            (uint128 s, , , , , , , ) = VOTING.voterStakes(coalition[i]);
            r.coalitionStakeBefore += s;
        }
        if (capture) {
            address[] memory senders = vm.parseJsonAddressArray(json, ".commitSenders");
            bytes[] memory commits = vm.parseJsonBytesArray(json, ".commitInputs");
            for (uint256 i = 0; i < senders.length; i++) {
                vm.prank(senders[i], senders[i]);
                (bool ok, ) = address(VOTING).call(commits[i]);
                require(ok, "re-commit reverted");
            }
        }
        address[] memory froms = vm.parseJsonAddressArray(json, ".froms");
        address[] memory tos = vm.parseJsonAddressArray(json, ".tos");
        uint256[] memory blocks = vm.parseJsonUintArray(json, ".blocks");
        uint256[] memory stamps = vm.parseJsonUintArray(json, ".timestamps");
        address[] memory callers = vm.parseJsonAddressArray(json, ".callers");
        for (uint256 k = 0; k < froms.length; k++) {
            if (!this.replayOne(k, capture, froms[k], tos[k], blocks[k], stamps[k])) {
                // the whole transaction fails on the fork (a wrapper or another call in its batch): deliver this
                // request's own reveal from the voter's direct caller, as recorded in its VoteRevealed event
                this.revealSingle(k, capture, callers[k]);
                r.fallbacks++;
            }
        }
        vm.roll(blocks[froms.length - 1] + 300);
        vm.warp(vm.parseJsonUint(json, ".roundEnd") + 1800);

        bytes32 identifier = vm.parseJsonBytes32(json, ".identifier");
        uint256 time = vm.parseJsonUint(json, ".time");
        bytes memory anc = vm.parseJsonBytes(json, ".ancillaryData");
        IVotingV2Fork.PendingRequestAncillary[] memory q = new IVotingV2Fork.PendingRequestAncillary[](1);
        q[0] = IVotingV2Fork.PendingRequestAncillary(identifier, time, anc);
        r.status = VOTING.getPriceRequestStatuses(q)[0].status;
        vm.prank(address(ROOT_TUNNEL));
        r.price = VOTING.getPrice(identifier, time, anc);

        // the live root tunnel publishes the DVM price; StateSender's StateSynced log is the bridge message
        vm.recordLogs();
        ROOT_TUNNEL.publishPrice(identifier, time, anc);
        Vm.Log[] memory logs = vm.getRecordedLogs();
        for (uint256 i = 0; i < logs.length; i++) {
            if (logs[i].emitter == STATE_SENDER && logs[i].topics[0] == STATE_SYNCED) {
                r.stateId = uint256(logs[i].topics[1]);
                r.message = abi.decode(logs[i].data, (bytes));
            }
        }
        require(r.message.length > 0, "no state-sync message");
        emit log_named_bytes("state-sync message", r.message);
        for (uint256 i = 0; i < coalition.length; i++) r.coalitionStakeAfter += VOTING.getVoterStakePostUpdate(coalition[i]);
    }

    /// One replayed reveal, in its own call frame so that its calldata (read from a per-transaction file) does not
    /// accumulate in the test's memory.
    function replayOne(uint256 k, bool capture, address from, address to, uint256 blk, uint256 ts)
        external
        returns (bool ok)
    {
        bytes memory input =
            vm.readFileBinary(string.concat("fixtures/ceasefire/", capture ? "dev_" : "in_", vm.toString(k), ".bin"));
        vm.roll(blk);
        vm.warp(ts);
        vm.prank(from, from);
        (ok, ) = to.call(input);
        if (!ok) emit log_named_uint("transaction replay failed, delivering the request's reveal alone: k", k);
    }

    function revealSingle(uint256 k, bool capture, address caller) external {
        bytes memory input =
            vm.readFileBinary(string.concat("fixtures/ceasefire/", capture ? "cfdev_" : "cf_", vm.toString(k), ".bin"));
        vm.prank(caller, caller);
        (bool ok, ) = address(VOTING).call(input);
        require(ok, "single reveal reverted");
    }

    function _polygon(EthResult memory e)
        internal
        returns (uint256 yesNum, uint256 noNum, uint256 noHeld, uint256 usdcPaid)
    {
        vm.createSelectFork(vm.envString("POLYGON_URL"), vm.parseJsonUint(json, ".polygonForkBlock"));
        bytes32 questionID = vm.parseJsonBytes32(json, ".questionID");
        bytes32 conditionId = vm.parseJsonBytes32(json, ".conditionId");
        uint256 noPosition = vm.parseJsonUint(json, ".noPosition");
        assertFalse(ADAPTER.ready(questionID), "price already on Polygon at the fork block");
        vm.prank(SYSTEM);
        FX_CHILD.onStateReceive(e.stateId, e.message);
        // as on the chain: the resolver settles the oracle's request (block 85,805,624, through a multicall), passing no
        // price, then the adapter resolves the market
        vm.prank(RESOLVER);
        OO.settle(address(ADAPTER), YES_OR_NO, vm.parseJsonUint(json, ".ooTimestamp"), vm.parseJsonBytes(json, ".ooAncillary"));
        ADAPTER.resolve(questionID);
        yesNum = CTF.payoutNumerators(conditionId, 0);
        noNum = CTF.payoutNumerators(conditionId, 1);
        address[] memory holders = vm.parseJsonAddressArray(json, ".noHolders");
        uint256[] memory sets = new uint256[](2);
        sets[0] = 1;
        sets[1] = 2;
        for (uint256 i = 0; i < holders.length; i++) {
            uint256 bal = CTF.balanceOf(holders[i], noPosition);
            if (bal == 0) continue;
            noHeld += bal;
            uint256 before = USDCE.balanceOf(holders[i]);
            vm.prank(holders[i]);
            CTF.redeemPositions(address(USDCE), bytes32(0), conditionId, sets);
            usdcPaid += USDCE.balanceOf(holders[i]) - before;
        }
    }

    function _report(string memory tag, EthResult memory e, uint256 y, uint256 n, uint256 held, uint256 paid) internal {
        emit log(tag);
        emit log_named_uint("  DVM status (2 = resolved)", e.status);
        emit log_named_int("  DVM price (1e18 = Yes, 0 = No)", e.price);
        emit log_named_uint("  CTF payout numerator Yes", y);
        emit log_named_uint("  CTF payout numerator No", n);
        emit log_named_decimal_uint("  No shares held by the listed holders", held, 6);
        emit log_named_decimal_uint("  USDC.e paid to them on redemption", paid, 6);
        emit log_named_decimal_uint("  coalition stake before (UMA)", e.coalitionStakeBefore, 18);
        emit log_named_decimal_uint("  coalition stake after the round (UMA)", e.coalitionStakeAfter, 18);
        emit log_named_uint("  transactions delivered as a single reveal", e.fallbacks);
    }

    function test_baseline_pays_yes() public {
        if (_skip()) return;
        EthResult memory e = _ethereum(false);
        assertEq(e.status, 2);
        assertEq(e.price, 1e18);
        (uint256 y, uint256 n, uint256 held, uint256 paid) = _polygon(e);
        _report("baseline: the round as it happened", e, y, n, held, paid);
        assertEq(y, 1);
        assertEq(n, 0);
        assertEq(paid, 0);
    }

    function test_coalition_captures_no() public {
        if (_skip()) return;
        EthResult memory e = _ethereum(true);
        assertEq(e.status, 2);
        assertEq(e.price, 0);
        (uint256 y, uint256 n, uint256 held, uint256 paid) = _polygon(e);
        _report("capture: the 19 largest voters on the request vote No", e, y, n, held, paid);
        assertEq(y, 0);
        assertEq(n, 1);
        assertEq(paid, held);
    }
}
