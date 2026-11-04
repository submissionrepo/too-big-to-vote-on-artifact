// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IVotingV2, IMarginSource} from "./Interfaces.sol";

/// A round's tally by answer. VotingV2 keeps it (ResultComputationV2.Data: voteFrequency per price and totalVotes) but
/// does not expose it; this interface is the one view a voting-contract upgrade, or the bridge message, would have to add.
interface IVoteTally {
    function voteTally(uint256 requestIndex)
        external
        view
        returns (uint256 yes, uint256 no, uint256 half, uint256 tooEarly, uint256 cast);
}

/// @title MarginReaderVotesCast
/// @notice The input of tally settlement: Yes's share of the votes cast, a vote for one half counting half, in basis
///         points. A vote for "too early" counts against Yes. When "too early" leads the round the question is asked
///         again, which the reader records as ASK_AGAIN.
contract MarginReaderVotesCast is IMarginSource {
    uint16 public constant ASK_AGAIN = type(uint16).max;

    IVotingV2 public immutable voting;
    IVoteTally public immutable tallies;

    mapping(bytes32 => uint32) private _stored; // share + 1; 0 means unknown

    event MarginRegistered(bytes32 indexed requestId, uint256 indexed requestIndex, uint16 bps);

    error IndexMismatch(bytes32 expected, bytes32 found);
    error NoVotes();

    constructor(IVotingV2 _voting, IVoteTally _tallies) {
        voting = _voting;
        tallies = _tallies;
    }

    function register(bytes32 requestId, uint256 requestIndex) external returns (uint16 bps) {
        bytes32 found = voting.resolvedPriceRequestIds(requestIndex);
        if (found != requestId) revert IndexMismatch(requestId, found);
        (uint256 yes, uint256 no, uint256 half, uint256 tooEarly, uint256 cast) = tallies.voteTally(requestIndex);
        if (cast == 0) revert NoVotes();
        if (tooEarly > yes && tooEarly > no && tooEarly > half) {
            bps = ASK_AGAIN;
        } else {
            bps = uint16(((2 * yes + half) * 10_000) / (2 * cast));
        }
        _stored[requestId] = uint32(bps) + 1;
        emit MarginRegistered(requestId, requestIndex, bps);
    }

    function marginBps(bytes32 requestId) external view returns (bool known, uint16 bps) {
        uint32 s = _stored[requestId];
        known = s != 0;
        bps = known ? uint16(s - 1) : 0;
    }
}
