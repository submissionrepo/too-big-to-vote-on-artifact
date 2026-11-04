// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title PriceAccumulator
/// @notice Uniswap-v2 style time-weighted price accumulator for an outcome token. The exchange (or a trusted
///         reporter in this prototype) records the price after each fill; anyone can later read the TWAP between
///         two recorded observations. Prices are in basis points of one unit of collateral (0 .. 10_000).
///
///         The window used by the settlement rule must end at or before the dispute time of the question, so the
///         reference price is fixed before any vote is cast.
contract PriceAccumulator {
    struct Observation {
        uint64 timestamp;
        uint16 priceBps;
        uint176 cumulative; // sum of priceBps * seconds since the first observation
    }

    address public immutable reporter;
    mapping(uint256 => Observation[]) private _obs; // tokenId -> observations

    event Recorded(uint256 indexed tokenId, uint64 timestamp, uint16 priceBps);

    error NotReporter();
    error BadWindow();
    error BadPrice();

    constructor(address _reporter) {
        reporter = _reporter;
    }

    /// @notice Record the current price of `tokenId`. Called by the exchange on every fill in production.
    function record(uint256 tokenId, uint16 priceBps) external {
        if (msg.sender != reporter) revert NotReporter();
        if (priceBps > 10_000) revert BadPrice();
        Observation[] storage o = _obs[tokenId];
        uint176 cum = 0;
        if (o.length > 0) {
            Observation storage last = o[o.length - 1];
            cum = last.cumulative + uint176(uint256(last.priceBps) * (block.timestamp - last.timestamp));
        }
        o.push(Observation(uint64(block.timestamp), priceBps, cum));
        emit Recorded(tokenId, uint64(block.timestamp), priceBps);
    }

    function observationCount(uint256 tokenId) external view returns (uint256) {
        return _obs[tokenId].length;
    }

    function observation(uint256 tokenId, uint256 i) external view returns (Observation memory) {
        return _obs[tokenId][i];
    }

    /// @notice TWAP between observations i < j, in basis points.
    function twapBetween(uint256 tokenId, uint256 i, uint256 j) public view returns (uint16) {
        Observation[] storage o = _obs[tokenId];
        if (!(i < j && j < o.length)) revert BadWindow();
        uint256 dt = o[j].timestamp - o[i].timestamp;
        if (dt == 0) revert BadWindow();
        return uint16((o[j].cumulative - o[i].cumulative) / dt);
    }

    /// @notice TWAP over the window [end - length, end] where `end` must be <= `latestAllowed` (the dispute time).
    ///         The caller supplies the bracketing observation indices; the contract checks them.
    function twapWindow(uint256 tokenId, uint256 i, uint256 j, uint64 latestAllowed, uint64 length)
        external
        view
        returns (uint16)
    {
        Observation[] storage o = _obs[tokenId];
        if (!(i < j && j < o.length)) revert BadWindow();
        if (o[j].timestamp > latestAllowed) revert BadWindow();
        if (o[j].timestamp - o[i].timestamp < length) revert BadWindow();
        return twapBetween(tokenId, i, j);
    }
}
