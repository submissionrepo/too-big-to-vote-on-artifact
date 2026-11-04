// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IVotingV2, IMarginSource} from "./Interfaces.sol";

/// @title MarginReader
/// @notice Reads, for a resolved DVM request, the share of the staked supply that voted for the winning answer
///         (x* in the paper), using only VotingV2's public views. Anyone may register a request by giving its
///         index in `resolvedPriceRequestIds`; the contract checks the index against the request id and stores
///         the margin so that downstream consumers (or the bridge) can read it with one SLOAD.
///
///         x* = totalCorrectVotes / cumulativeStakeAtRound, in basis points, rounded down.
contract MarginReader is IMarginSource {
    IVotingV2 public immutable voting;

    mapping(bytes32 => uint16) private _margin;   // requestId -> bps, 0 = unknown (a real margin is never 0)
    mapping(bytes32 => uint32) public roundOf;    // requestId -> resolving round

    event MarginRegistered(bytes32 indexed requestId, uint256 indexed requestIndex, uint32 round, uint16 bps);

    error IndexMismatch(bytes32 expected, bytes32 found);
    error EmptyRound();

    constructor(IVotingV2 _voting) {
        voting = _voting;
    }

    /// @notice Register the margin of a resolved request.
    /// @param requestId keccak256(abi.encode(identifier, time, ancillaryData)) as VotingV2 stores it
    /// @param requestIndex position of the request in VotingV2.resolvedPriceRequestIds
    function register(bytes32 requestId, uint256 requestIndex) external returns (uint16 bps) {
        bytes32 found = voting.resolvedPriceRequestIds(requestIndex);
        if (found != requestId) revert IndexMismatch(requestId, found);
        IVotingV2.SlashingTracker memory t = voting.requestSlashingTrackers(requestIndex);
        (, , , uint128 staked, ) = voting.rounds(t.lastVotingRound);
        if (staked == 0) revert EmptyRound();
        bps = uint16((t.totalCorrectVotes * 10_000) / staked);
        _margin[requestId] = bps;
        roundOf[requestId] = t.lastVotingRound;
        emit MarginRegistered(requestId, requestIndex, t.lastVotingRound, bps);
    }

    function marginBps(bytes32 requestId) external view returns (bool known, uint16 bps) {
        bps = _margin[requestId];
        known = bps != 0;
    }

    /// @notice Pure helper: the request id VotingV2 uses.
    function requestIdOf(bytes32 identifier, uint256 time, bytes calldata ancillaryData) external pure returns (bytes32) {
        return keccak256(abi.encode(identifier, time, ancillaryData));
    }
}
