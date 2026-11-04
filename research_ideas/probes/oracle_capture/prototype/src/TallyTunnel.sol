// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IMarginSource} from "./Interfaces.sol";

/// The two ends of Polygon's state-sync bridge, as in the FxPortal contracts that UMA's oracle tunnel already uses.
interface IFxStateSender {
    function sendMessageToChild(address receiver, bytes calldata data) external;
}

interface IFxMessageProcessor {
    function processMessageFromRoot(uint256 stateId, address rootMessageSender, bytes calldata data) external;
}

/// @title TallyRootTunnel (Ethereum)
/// @notice Carries Yes's share of a DVM vote, as read by MarginReaderVotesCast, to Polygon. Anyone may relay a share
///         once the reader knows it; the message is (requestId, shareBps).
contract TallyRootTunnel {
    IMarginSource public immutable reader;
    IFxStateSender public immutable fxRoot;
    address public childTunnel;
    address public immutable deployer;

    event Relayed(bytes32 indexed requestId, uint16 shareBps);

    error Unknown();
    error AlreadySet();

    constructor(IMarginSource _reader, IFxStateSender _fxRoot) {
        reader = _reader;
        fxRoot = _fxRoot;
        deployer = msg.sender;
    }

    /// @dev One-time wiring, as FxBaseRootTunnel.setFxChildTunnel does.
    function setChildTunnel(address _child) external {
        if (childTunnel != address(0) || msg.sender != deployer) revert AlreadySet();
        childTunnel = _child;
    }

    function relay(bytes32 requestId) external {
        (bool known, uint16 bps) = reader.marginBps(requestId);
        if (!known) revert Unknown();
        fxRoot.sendMessageToChild(childTunnel, abi.encode(requestId, bps));
        emit Relayed(requestId, bps);
    }
}

/// @title TallyChildTunnel (Polygon)
/// @notice Receives shares from the root tunnel through the bridge and serves them to TallyAdapter. Messages are
///         accepted only from the bridge's child endpoint and only when sent by the root tunnel.
contract TallyChildTunnel is IFxMessageProcessor, IMarginSource {
    address public immutable fxChild;
    address public immutable rootTunnel;
    mapping(bytes32 => uint32) internal stored; // share + 1; 0 means unknown (a Yes share of 0 is a valid tally)

    event Received(bytes32 indexed requestId, uint16 shareBps);

    error NotBridge();
    error NotRoot();

    constructor(address _fxChild, address _rootTunnel) {
        fxChild = _fxChild;
        rootTunnel = _rootTunnel;
    }

    function processMessageFromRoot(uint256, address rootMessageSender, bytes calldata data) external {
        if (msg.sender != fxChild) revert NotBridge();
        if (rootMessageSender != rootTunnel) revert NotRoot();
        (bytes32 requestId, uint16 bps) = abi.decode(data, (bytes32, uint16));
        stored[requestId] = uint32(bps) + 1;
        emit Received(requestId, bps);
    }

    function marginBps(bytes32 requestId) external view returns (bool known, uint16 bps) {
        uint32 s = stored[requestId];
        known = s != 0;
        bps = known ? uint16(s - 1) : 0;
    }
}
