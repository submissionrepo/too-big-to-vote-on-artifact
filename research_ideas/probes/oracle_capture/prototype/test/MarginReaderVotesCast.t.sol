// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";
import {MarginReaderVotesCast, IVoteTally} from "../src/MarginReaderVotesCast.sol";
import {IVotingV2} from "../src/Interfaces.sol";

/// Mock of the VotingV2 index view plus the missing tally view. Request 827 carries the decoded tallies of the March
/// 2025 request that decided the market's payout (in wei): Yes 12,292,521.21 UMA, No 1,143.71, one half 27.77, too
/// early 8,706,370.61, cast 21,000,063.29. (Request 828, the first dispute's, settled only that dispute's bonds.)
/// Requests 1 and 2 are synthetic: a round led by "too early", and a No that wins with "too early" votes.
contract MockVoting {
    bytes32 public constant ID = keccak256("request-827");
    bytes32 public constant ID_EARLY = keccak256("too-early-leads");
    bytes32 public constant ID_NO = keccak256("no-wins");

    function resolvedPriceRequestIds(uint256 index) external pure returns (bytes32) {
        if (index == 827) return ID;
        if (index == 1) return ID_EARLY;
        if (index == 2) return ID_NO;
        return bytes32(0);
    }

    function voteTally(uint256 index)
        external
        pure
        returns (uint256 yes, uint256 no, uint256 half, uint256 tooEarly, uint256 cast)
    {
        if (index == 827) {
            return (12292521206971279123932254, 1143706659947835651849, 27766834054390931203,
                    8706370610005000795290322, 21000063290470282145805628);
        }
        if (index == 1) return (40 ether, 10 ether, 0, 50 ether, 100 ether);
        return (0, 70 ether, 0, 30 ether, 100 ether);
    }
}

contract MarginReaderVotesCastTest is Test {
    MockVoting m;
    MarginReaderVotesCast reader;

    function setUp() public {
        m = new MockVoting();
        reader = new MarginReaderVotesCast(IVotingV2(address(m)), IVoteTally(address(m)));
    }

    function test_yes_share_of_march_request() public {
        uint256 g0 = gasleft();
        uint16 bps = reader.register(m.ID(), 827);
        emit log_named_uint("gas register (votes cast, mock)", g0 - gasleft());
        emit log_named_uint("Yes share bps (votes cast)", bps);
        assertEq(bps, 5853);            // (12,292,521 + 28/2) / 21,000,063 = 58.5% of the votes cast, below 1 - mu = 80%
        bytes32 id = m.ID();
        vm.expectRevert();
        reader.register(id, 828);       // index check
    }

    function test_too_early_lead_asks_again() public {
        assertEq(reader.register(m.ID_EARLY(), 1), reader.ASK_AGAIN());
    }

    // "too early" counts against Yes: a No win with no Yes votes is a Yes share of zero, which is a known value
    function test_no_win_is_a_known_zero() public {
        assertEq(reader.register(m.ID_NO(), 2), 0);
        (bool known, uint16 bps) = reader.marginBps(m.ID_NO());
        assertTrue(known);
        assertEq(bps, 0);
    }
}
