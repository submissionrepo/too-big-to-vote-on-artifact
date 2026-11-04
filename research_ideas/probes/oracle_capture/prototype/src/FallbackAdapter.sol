// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IConditionalTokens, IResolvedPriceSource, IMarginSource} from "./Interfaces.sol";
import {PriceAccumulator} from "./PriceAccumulator.sol";

/// @title FallbackAdapter
/// @notice Settlement rule F_mu from the paper, on top of the usual Polymarket flow:
///         - the question resolved optimistically, or by a DVM vote whose winner holds at least (1 - mu) of the
///           votes cast (or of the staked supply, with the reader that runs on today's contract): pay 0 / 1 as the
///           oracle says;
///         - otherwise (a contested vote, or a request the DVM deleted): pay every share the pre-dispute
///           time-weighted price of the market itself, so that capturing a contested vote earns nothing beyond
///           what the market already priced.
///         With `onlyAgainstMarket` set, the contract implements the disagreement variant F_mu^d: a contested vote
///         is replaced by the reference price only when its winner was the market's underdog before the dispute
///         (reference price of the winning answer below one half); a contested vote that agrees with the market's
///         favorite pays 0 / 1. Deleted requests pay the reference price under both rules.
///         The only new on-chain inputs are the winner share (MarginReader on mainnet, bridged) and the TWAP
///         (PriceAccumulator fed by the exchange). The 50/50 answer p3 keeps its usual meaning.
contract FallbackAdapter {
    uint16 public constant BPS = 10_000;

    IConditionalTokens public immutable ctf;
    IResolvedPriceSource public immutable prices;
    IMarginSource public immutable margins;
    PriceAccumulator public immutable accumulator;
    uint16 public immutable muBps;         // e.g. 2_000 for mu = 0.20
    uint64 public immutable windowLength;  // e.g. 24 hours
    bool public immutable onlyAgainstMarket; // false: F_mu; true: the disagreement variant F_mu^d

    struct Question {
        bytes32 requestId;      // DVM request id, 0 if resolved optimistically
        uint256 yesTokenId;     // outcome token whose TWAP is the reference price
        uint64 disputeTime;     // the window must end at or before this
        bool deleted;           // the DVM deleted the request after rolling
        bool settled;
    }

    mapping(bytes32 => Question) public questions;

    event Settled(bytes32 indexed questionID, bool tape, uint256 payoutYes, uint256 payoutNo, uint16 marginBps, uint16 twapBps);

    error AlreadySettled();
    error NotReady();
    error UnknownMargin();

    constructor(
        IConditionalTokens _ctf,
        IResolvedPriceSource _prices,
        IMarginSource _margins,
        PriceAccumulator _accumulator,
        uint16 _muBps,
        uint64 _windowLength,
        bool _onlyAgainstMarket
    ) {
        ctf = _ctf;
        prices = _prices;
        margins = _margins;
        accumulator = _accumulator;
        muBps = _muBps;
        windowLength = _windowLength;
        onlyAgainstMarket = _onlyAgainstMarket;
    }

    /// @dev Registration is permissionless in the prototype; production binds it to the adapter's own request flow.
    function registerQuestion(bytes32 questionID, bytes32 requestId, uint256 yesTokenId, uint64 disputeTime, bool deleted)
        external
    {
        questions[questionID] = Question(requestId, yesTokenId, disputeTime, deleted, false);
    }

    /// @notice Settle `questionID`. `i`, `j` bracket the TWAP window in the accumulator (ignored on the 0/1 path).
    function settle(bytes32 questionID, uint256 i, uint256 j) external {
        Question storage q = questions[questionID];
        if (q.settled) revert AlreadySettled();
        uint256[] memory payouts = new uint256[](2);
        uint16 margin = BPS; // optimistic resolution counts as unanimous
        uint16 twap = 0;
        bool tape = q.deleted;

        int256 price = 0;
        if (!tape) {
            bool ready;
            (ready, price) = prices.resolvedPrice(questionID);
            if (!ready) revert NotReady();
            if (q.requestId != bytes32(0)) {
                bool known;
                (known, margin) = margins.marginBps(q.requestId);
                if (!known) revert UnknownMargin();
            }
            tape = margin < BPS - muBps && price != 0.5 ether; // a 50/50 answer is paid as 50/50 either way
        }

        if (tape) {
            twap = accumulator.twapWindow(q.yesTokenId, i, j, q.disputeTime, windowLength);
            if (onlyAgainstMarket && !q.deleted) {
                // the variant keeps a contested vote that agrees with the market's favorite
                uint16 winnerTwap = price == 1 ether ? twap : BPS - twap;
                if (2 * uint256(winnerTwap) >= BPS) tape = false;
            }
        }

        if (tape) {
            payouts[0] = twap;          // YES
            payouts[1] = BPS - twap;    // NO
        } else if (price == 1 ether) {
            payouts[0] = 1;
            payouts[1] = 0;
        } else if (price == 0) {
            payouts[0] = 0;
            payouts[1] = 1;
        } else {
            payouts[0] = 1;             // p3: 50/50
            payouts[1] = 1;
        }
        q.settled = true;
        ctf.reportPayouts(questionID, payouts);
        emit Settled(questionID, tape, payouts[0], payouts[1], margin, twap);
    }
}
