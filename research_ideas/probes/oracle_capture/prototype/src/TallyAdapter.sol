// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IConditionalTokens, IResolvedPriceSource, IMarginSource} from "./Interfaces.sol";

/// @title TallyAdapter
/// @notice Tally settlement R_mu from the paper. A question that the oracle settled without a vote pays as the oracle
///         says. A question settled by a DVM vote pays a Yes share rho(f) = clip((f - mu) / (1 - 2 mu), 0, 1) and a No
///         share 1 - rho(f), where f is Yes's share of the votes cast in basis points, a vote for one half counting half
///         and a vote for "too early" counting against Yes; when "too early" led the round the question is asked
///         again. No market price enters, so the payout can be moved only by votes, and a stake of sigma moves it by at
///         most sigma / (1 - 2 mu). Inputs: the oracle's answer (as today) and Yes's share of the votes cast, read on
///         Ethereum by MarginReaderVotesCast and carried by the bridge. Settling a round the DVM rolled needs the same
///         share for that round, which the deployed contract does not expose; the prototype covers resolved rounds.
contract TallyAdapter {
    uint16 public constant BPS = 10_000;
    uint16 public constant ASK_AGAIN = type(uint16).max;

    IConditionalTokens public immutable ctf;
    IResolvedPriceSource public immutable prices;
    IMarginSource public immutable margins;
    uint16 public immutable muBps; // e.g. 2_000 for mu = 0.20

    struct Question {
        bytes32 requestId; // DVM request id, 0 if resolved optimistically
        bool settled;
    }

    mapping(bytes32 => Question) public questions;

    event Settled(bytes32 indexed questionID, uint256 payoutYes, uint256 payoutNo, uint16 shareBps);

    error AlreadySettled();
    error NotReady();
    error UnknownMargin();
    error AskAgain();
    error BadMu();

    constructor(IConditionalTokens _ctf, IResolvedPriceSource _prices, IMarginSource _margins, uint16 _muBps) {
        if (2 * uint256(_muBps) >= BPS) revert BadMu();
        ctf = _ctf;
        prices = _prices;
        margins = _margins;
        muBps = _muBps;
    }

    /// @dev Registration is permissionless in the prototype; production binds it to the adapter's own request flow.
    function registerQuestion(bytes32 questionID, bytes32 requestId) external {
        questions[questionID] = Question(requestId, false);
    }

    /// @notice rho(f) in basis points: 0 at or below mu, 1 at or above 1 - mu, linear in between.
    function ramp(uint16 shareBps) public view returns (uint256) {
        if (shareBps <= muBps) return 0;
        uint256 r = (uint256(shareBps) - muBps) * BPS / (BPS - 2 * uint256(muBps));
        return r > BPS ? BPS : r;
    }

    function settle(bytes32 questionID) external {
        Question storage q = questions[questionID];
        if (q.settled) revert AlreadySettled();
        (bool ready, int256 price) = prices.resolvedPrice(questionID);
        if (!ready) revert NotReady();
        uint256[] memory payouts = new uint256[](2);
        uint16 share;
        if (q.requestId == bytes32(0)) {
            // settled without a vote: as the oracle says
            if (price == 0.5 ether) {
                payouts[0] = 1;
                payouts[1] = 1;
            } else if (price == 1 ether) {
                payouts[0] = BPS;
            } else {
                payouts[1] = BPS;
            }
            share = price == 1 ether ? BPS : (price == 0.5 ether ? BPS / 2 : 0);
        } else {
            bool known;
            (known, share) = margins.marginBps(q.requestId);
            if (!known) revert UnknownMargin();
            if (share == ASK_AGAIN) revert AskAgain();
            uint256 yes = ramp(share);
            payouts[0] = yes;
            payouts[1] = BPS - yes;
        }
        q.settled = true;
        ctf.reportPayouts(questionID, payouts);
        emit Settled(questionID, payouts[0], payouts[1], share);
    }
}
