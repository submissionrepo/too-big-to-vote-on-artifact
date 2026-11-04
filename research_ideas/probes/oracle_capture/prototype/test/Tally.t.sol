// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";
import {TallyAdapter} from "../src/TallyAdapter.sol";
import {MockCTF, MockPrices, MockMargins} from "./Fallback.t.sol";

/// The margin source carries Yes's share of the votes cast (a vote for one half counting half, a vote for "too early"
/// counting against Yes), or ASK_AGAIN when "too early" led the round (MarginReaderVotesCast).
contract TallyTest is Test {
    MockCTF ctf;
    MockPrices prices;
    MockMargins margins;
    TallyAdapter adapter;

    bytes32 constant Q = keccak256("rare-earth");
    bytes32 constant R = keccak256("dvm-request-827");

    function setUp() public {
        ctf = new MockCTF();
        prices = new MockPrices();
        margins = new MockMargins();
        adapter = new TallyAdapter(ctf, prices, margins, 2_000);
        adapter.registerQuestion(Q, R);
    }

    // March 2025, the payout-deciding request: YES held 58.53% of the votes cast; rho = (0.5853 - 0.2) / 0.6 = 0.6421
    function test_march_pays_the_ramp() public {
        prices.set(Q, 1 ether);
        margins.set(R, 5853);
        adapter.settle(Q);
        assertEq(ctf.payout(0), 6421);
        assertEq(ctf.payout(1), 3579);
    }

    // the same vote read against the staked supply (the reader that runs on today's contract): 53.80%
    function test_staked_share_pays_about_half() public {
        prices.set(Q, 1 ether);
        margins.set(R, 5380);
        adapter.settle(Q);
        assertEq(ctf.payout(0), 5633);
        assertEq(ctf.payout(1), 4367);
    }

    // NO won with 96% of the votes cast, Yes holding 4%: below mu, NO is paid in full
    function test_supermajority_pays_in_full() public {
        prices.set(Q, 0);
        margins.set(R, 400);
        adapter.settle(Q);
        assertEq(ctf.payout(0), 0);
        assertEq(ctf.payout(1), 10_000);
    }

    // a Yes share of zero is a valid tally, not a missing one
    function test_unanimous_no_pays_no() public {
        prices.set(Q, 0);
        margins.set(R, 0);
        adapter.settle(Q);
        assertEq(ctf.payout(0), 0);
        assertEq(ctf.payout(1), 10_000);
    }

    function test_threshold_of_full_payment() public {
        prices.set(Q, 1 ether);
        margins.set(R, 8000);       // exactly 1 - mu
        adapter.settle(Q);
        assertEq(ctf.payout(0), 10_000);
        assertEq(ctf.payout(1), 0);
    }

    function test_optimistic_resolution_needs_no_tally() public {
        bytes32 q2 = keccak256("undisputed");
        adapter.registerQuestion(q2, bytes32(0));
        prices.set(q2, 1 ether);
        adapter.settle(q2);
        assertEq(ctf.payout(0), 10_000);
        assertEq(ctf.payout(1), 0);
    }

    // a vote for one half counts half: a round that voted one half unanimously pays one half
    function test_half_votes_pay_half() public {
        prices.set(Q, 0.5 ether);
        margins.set(R, 5000);
        adapter.settle(Q);
        assertEq(ctf.payout(0), 5_000);
        assertEq(ctf.payout(1), 5_000);
    }

    function test_too_early_lead_asks_again() public {
        prices.set(Q, 1 ether);
        margins.set(R, adapter.ASK_AGAIN());
        vm.expectRevert(TallyAdapter.AskAgain.selector);
        adapter.settle(Q);
    }

    // a stake of sigma moves the payout by at most sigma / (1 - 2 mu): 1,000 bps of votes move it by at most 1,667 bps
    function testFuzz_lipschitz(uint16 w, uint16 d) public view {
        w = uint16(bound(w, 0, 10_000));
        d = uint16(bound(d, 0, 10_000 - w));
        uint256 a = adapter.ramp(w);
        uint256 b = adapter.ramp(w + d);
        assertLe(b - a, (uint256(d) * 10_000 + 5_999) / 6_000);
    }

    function test_rejects_mu_of_one_half() public {
        vm.expectRevert(TallyAdapter.BadMu.selector);
        new TallyAdapter(ctf, prices, margins, 5_000);
    }
}
