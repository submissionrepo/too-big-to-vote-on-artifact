// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// Minimal views of UMA VotingV2 (mainnet 0x004395edb43EFca9885CEdad51EC9fAf93Bd34ac) used by the prototype.
interface IVotingV2 {
    struct SlashingTracker {
        uint256 wrongVoteSlashPerToken;
        uint256 noVoteSlashPerToken;
        uint256 totalSlashed;
        uint256 totalCorrectVotes;
        uint32 lastVotingRound;
    }

    function requestSlashingTrackers(uint256 requestIndex) external view returns (SlashingTracker memory);

    function rounds(uint256 roundId)
        external
        view
        returns (
            address slashingLibrary,
            uint128 minParticipationRequirement,
            uint128 minAgreementRequirement,
            uint128 cumulativeStakeAtRound,
            uint32 numberOfRequestsToVote
        );

    function resolvedPriceRequestIds(uint256 index) external view returns (bytes32);
}

/// Gnosis ConditionalTokens: only the resolution entry point is needed.
interface IConditionalTokens {
    function reportPayouts(bytes32 questionId, uint256[] calldata payouts) external;
}

/// The resolved answer of the question, as the adapter sees it after the optimistic oracle settles.
interface IResolvedPriceSource {
    function resolvedPrice(bytes32 questionID) external view returns (bool ready, int256 price);
}

/// A share of the DVM vote that resolved a question, in basis points: for MarginReader the winner's share of the staked
/// supply (what today's contract exposes), for MarginReaderVotesCast Yes's share of the votes cast (what tally settlement
/// reads). On Polygon this value has to arrive through the UMA bridge; the readers compute it on mainnet.
interface IMarginSource {
    function marginBps(bytes32 requestId) external view returns (bool known, uint16 bps);
}
