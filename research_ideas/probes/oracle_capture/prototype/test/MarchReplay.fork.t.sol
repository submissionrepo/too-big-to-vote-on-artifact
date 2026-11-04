// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";

interface IVotingStatus {
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
}

/// Replays the end of the March 2025 vote on a fork of Ethereum mainnet. The fork is taken one block before the first
/// reveal of the three wallets (fixture built by build_march_fixture.py from the chain); every later reveal
/// transaction of round 10085 for the minerals-deal request is replayed with its original sender, calldata and
/// timestamp, optionally skipping some of the three wallets' reveals. After the round ends, the live VotingV2 code
/// says whether the request resolved. Run with FORK_URL set (an archive endpoint); skipped otherwise.
contract MarchReplayForkTest is Test {
    IVotingStatus constant VOTING = IVotingStatus(0x004395edb43EFca9885CEdad51EC9fAf93Bd34ac);
    uint8 constant ACTIVE = 1;
    uint8 constant RESOLVED = 2;

    string json;

    function _replay(string memory skip) internal returns (uint8 status, uint32 round) {
        string memory url = vm.envOr("FORK_URL", string(""));
        json = vm.readFile("fixtures/march_reveals.json");
        vm.createSelectFork(url, vm.parseJsonUint(json, ".forkBlock"));
        address[] memory froms = vm.parseJsonAddressArray(json, ".froms");
        address[] memory tos = vm.parseJsonAddressArray(json, ".tos");
        bytes[] memory inputs = vm.parseJsonBytesArray(json, ".inputs");
        uint256[] memory blocks = vm.parseJsonUintArray(json, ".blocks");
        uint256[] memory stamps = vm.parseJsonUintArray(json, ".timestamps");
        string[] memory whales = vm.parseJsonStringArray(json, ".whales");
        for (uint256 k = 0; k < froms.length; k++) {
            if (bytes(whales[k]).length == 1 && _contains(skip, whales[k])) continue;
            vm.roll(blocks[k]);
            vm.warp(stamps[k]);
            vm.prank(froms[k], froms[k]);
            (bool ok, ) = tos[k].call(inputs[k]);
            require(ok, "replayed reveal reverted");
        }
        vm.warp(vm.parseJsonUint(json, ".roundEnd") + 3600);
        IVotingStatus.PendingRequestAncillary[] memory q = new IVotingStatus.PendingRequestAncillary[](1);
        q[0] = IVotingStatus.PendingRequestAncillary(
            vm.parseJsonBytes32(json, ".identifier"), vm.parseJsonUint(json, ".time"), vm.parseJsonBytes(json, ".ancillaryData"));
        IVotingStatus.RequestState[] memory st = VOTING.getPriceRequestStatuses(q);
        return (st[0].status, st[0].lastVotingRound);
    }

    function _contains(string memory set, string memory c) internal pure returns (bool) {
        bytes memory s = bytes(set);
        bytes1 x = bytes(c)[0];
        for (uint256 i = 0; i < s.length; i++) if (s[i] == x) return true;
        return false;
    }

    function _skipIfNoFork() internal returns (bool) {
        if (bytes(vm.envOr("FORK_URL", string(""))).length == 0) {
            emit log("FORK_URL not set; skipping");
            return true;
        }
        return false;
    }

    function test_as_it_happened_resolves() public {
        if (_skipIfNoFork()) return;
        (uint8 status, uint32 round) = _replay("");
        emit log_named_uint("status (2 = resolved)", status);
        assertEq(status, RESOLVED);
        assertEq(round, 10085);
    }

    function test_without_wallet_C_rolls() public {
        if (_skipIfNoFork()) return;
        (uint8 status, ) = _replay("C");
        emit log_named_uint("status without C (1 = active, rolled)", status);
        assertEq(status, ACTIVE);
    }

    function test_without_wallet_A_rolls() public {
        if (_skipIfNoFork()) return;
        (uint8 status, ) = _replay("A");
        assertEq(status, ACTIVE);
    }

    function test_without_wallet_B_rolls() public {
        if (_skipIfNoFork()) return;
        (uint8 status, ) = _replay("B");
        assertEq(status, ACTIVE);
    }

    function test_without_all_three_rolls() public {
        if (_skipIfNoFork()) return;
        (uint8 status, ) = _replay("ABC");
        assertEq(status, ACTIVE);
    }
}
