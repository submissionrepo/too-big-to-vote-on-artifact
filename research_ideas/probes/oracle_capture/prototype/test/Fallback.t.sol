// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";
import {FallbackAdapter} from "../src/FallbackAdapter.sol";
import {PriceAccumulator} from "../src/PriceAccumulator.sol";
import {IConditionalTokens, IResolvedPriceSource, IMarginSource} from "../src/Interfaces.sol";

contract MockCTF is IConditionalTokens {
    bytes32 public lastQuestion;
    uint256[] public lastPayouts;

    function reportPayouts(bytes32 questionId, uint256[] calldata payouts) external {
        lastQuestion = questionId;
        delete lastPayouts;
        for (uint256 k = 0; k < payouts.length; k++) lastPayouts.push(payouts[k]);
    }

    function payout(uint256 k) external view returns (uint256) {
        return lastPayouts[k];
    }
}

contract MockPrices is IResolvedPriceSource {
    mapping(bytes32 => int256) public p;
    mapping(bytes32 => bool) public ready;

    function set(bytes32 q, int256 price) external {
        p[q] = price;
        ready[q] = true;
    }

    function resolvedPrice(bytes32 q) external view returns (bool, int256) {
        return (ready[q], p[q]);
    }
}

/// Stores share + 1 in one slot, as the child tunnel does, so that a share of zero is known and settle's gas matches
/// a settlement fed by the bridge.
contract MockMargins is IMarginSource {
    mapping(bytes32 => uint32) public stored;

    function set(bytes32 r, uint16 bps) external {
        stored[r] = uint32(bps) + 1;
    }

    function marginBps(bytes32 r) external view returns (bool known, uint16 bps) {
        uint32 s = stored[r];
        known = s != 0;
        bps = known ? uint16(s - 1) : 0;
    }
}

contract FallbackTest is Test {
    MockCTF ctf;
    MockPrices prices;
    MockMargins margins;
    PriceAccumulator acc;
    FallbackAdapter adapter;
    FallbackAdapter variant;

    bytes32 constant Q = keccak256("rare-earth");
    bytes32 constant R = keccak256("dvm-request-828");
    uint256 constant YES = 6072587425042370362;
    uint64 constant DISPUTE = 1742680702; // 2025-03-22 22:38:22 UTC

    function setUp() public {
        ctf = new MockCTF();
        prices = new MockPrices();
        margins = new MockMargins();
        acc = new PriceAccumulator(address(this));
        adapter = new FallbackAdapter(ctf, prices, margins, acc, 2_000, 24 hours, false);
        variant = new FallbackAdapter(ctf, prices, margins, acc, 2_000, 24 hours, true);

        // 25 hourly observations ending exactly at the dispute time, mimicking the hourly YES series of 2025-03-22
        uint16[25] memory px = [
            uint16(1700), 1650, 1620, 1600, 1580, 1600, 1650, 1700, 1750, 1800, 1850, 1800,
            1750, 1700, 1680, 1660, 1650, 1640, 1630, 1620, 1610, 1600, 1620, 1700, 1699
        ];
        for (uint256 k = 0; k < 25; k++) {
            vm.warp(DISPUTE - 24 hours + k * 1 hours);
            acc.record(YES, px[k]);
        }
        adapter.registerQuestion(Q, R, YES, DISPUTE, false);
        variant.registerQuestion(Q, R, YES, DISPUTE, false);
        vm.warp(DISPUTE + 3 days);
    }

    function test_contested_vote_pays_the_tape() public {
        prices.set(Q, 1 ether);     // DVM said YES
        margins.set(R, 5018);       // winner held 50.18% of staked, below 1 - mu = 80%
        adapter.settle(Q, 0, 24);
        uint256 y = ctf.payout(0);
        uint256 n = ctf.payout(1);
        assertEq(y + n, 10_000);
        assertGt(y, 1550);
        assertLt(y, 1750);          // the 24h TWAP of the series above
    }

    function test_uncontested_vote_pays_zero_one() public {
        prices.set(Q, 1 ether);
        margins.set(R, 9600);       // 96% of staked agreed
        adapter.settle(Q, 0, 24);
        assertEq(ctf.payout(0), 1);
        assertEq(ctf.payout(1), 0);
    }

    function test_optimistic_resolution_needs_no_margin() public {
        bytes32 q2 = keccak256("undisputed");
        adapter.registerQuestion(q2, bytes32(0), YES, DISPUTE, false);
        prices.set(q2, 0);
        adapter.settle(q2, 0, 0);
        assertEq(ctf.payout(0), 0);
        assertEq(ctf.payout(1), 1);
    }

    function test_deleted_request_pays_the_tape() public {
        bytes32 q3 = keccak256("deleted");
        adapter.registerQuestion(q3, R, YES, DISPUTE, true);
        adapter.settle(q3, 0, 24);
        assertEq(ctf.payout(0) + ctf.payout(1), 10_000);
    }

    function test_window_must_end_before_dispute() public {
        prices.set(Q, 1 ether);
        margins.set(R, 5018);
        vm.warp(DISPUTE + 1 hours);
        acc.record(YES, 9740);      // the post-reveal jump must not enter the reference price
        vm.expectRevert(PriceAccumulator.BadWindow.selector);
        adapter.settle(Q, 0, 25);
    }

    function test_fifty_fifty_answer_unchanged() public {
        prices.set(Q, 0.5 ether);
        margins.set(R, 5018);
        adapter.settle(Q, 0, 24);
        assertEq(ctf.payout(0), 1);
        assertEq(ctf.payout(1), 1);
    }

    // F_mu pays the tape on a contested vote even when the vote agrees with the market's favorite
    function test_contested_vote_for_the_favorite_pays_the_tape() public {
        prices.set(Q, 0);           // DVM said NO, the side the market priced at about 83 cents
        margins.set(R, 7000);
        adapter.settle(Q, 0, 24);
        assertEq(ctf.payout(0) + ctf.payout(1), 10_000);
        assertGt(ctf.payout(1), 8250);
    }

    // the disagreement variant: a contested vote against the market's favorite is replaced by the tape ...
    function test_variant_vote_against_the_favorite_pays_the_tape() public {
        prices.set(Q, 1 ether);     // YES won, priced at about 17 cents before the dispute
        margins.set(R, 5018);
        variant.settle(Q, 0, 24);
        assertEq(ctf.payout(0) + ctf.payout(1), 10_000);
        assertLt(ctf.payout(0), 1750);
    }

    // ... a contested vote for the favorite pays 0 / 1 ...
    function test_variant_vote_for_the_favorite_pays_zero_one() public {
        prices.set(Q, 0);           // NO won, the market's favorite
        margins.set(R, 7000);
        variant.settle(Q, 0, 24);
        assertEq(ctf.payout(0), 0);
        assertEq(ctf.payout(1), 1);
    }

    // ... and a deleted request still pays the tape
    function test_variant_deleted_request_pays_the_tape() public {
        bytes32 q4 = keccak256("deleted-variant");
        variant.registerQuestion(q4, R, YES, DISPUTE, true);
        variant.settle(q4, 0, 24);
        assertEq(ctf.payout(0) + ctf.payout(1), 10_000);
    }

    function test_variant_uncontested_vote_pays_zero_one() public {
        prices.set(Q, 1 ether);
        margins.set(R, 9600);
        variant.settle(Q, 0, 24);
        assertEq(ctf.payout(0), 1);
        assertEq(ctf.payout(1), 0);
    }
}
