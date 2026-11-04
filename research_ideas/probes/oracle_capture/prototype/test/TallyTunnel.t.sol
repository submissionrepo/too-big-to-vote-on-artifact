// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";
import {TallyRootTunnel, TallyChildTunnel, IFxStateSender, IFxMessageProcessor} from "../src/TallyTunnel.sol";
import {TallyAdapter} from "../src/TallyAdapter.sol";
import {IMarginSource} from "../src/Interfaces.sol";
import {MockCTF, MockPrices, MockMargins} from "./Fallback.t.sol";

/// Stands in for Polygon's state sync: delivers each message to the child from the bridge's child endpoint.
contract MockFxRoot is IFxStateSender {
    address public immutable fxChild;
    uint256 public stateId;

    constructor(address _fxChild) {
        fxChild = _fxChild;
    }

    function sendMessageToChild(address receiver, bytes calldata data) external {
        stateId++;
        FxChildRelay(fxChild).deliver(receiver, stateId, msg.sender, data);
    }
}

contract FxChildRelay {
    function deliver(address receiver, uint256 id, address sender, bytes calldata data) external {
        IFxMessageProcessor(receiver).processMessageFromRoot(id, sender, data);
    }
}

contract TallyTunnelTest is Test {
    MockMargins reader;   // stands in for MarginReader on Ethereum (fork-tested separately)
    FxChildRelay fxChild;
    MockFxRoot fxRoot;
    TallyRootTunnel root;
    TallyChildTunnel child;
    MockCTF ctf;
    MockPrices prices;
    TallyAdapter adapter;

    bytes32 constant Q = keccak256("rare-earth");
    bytes32 constant R = keccak256("dvm-request-827");

    function setUp() public {
        reader = new MockMargins();
        fxChild = new FxChildRelay();
        fxRoot = new MockFxRoot(address(fxChild));
        root = new TallyRootTunnel(IMarginSource(address(reader)), fxRoot);
        child = new TallyChildTunnel(address(fxChild), address(root));
        root.setChildTunnel(address(child));
        ctf = new MockCTF();
        prices = new MockPrices();
        adapter = new TallyAdapter(ctf, prices, child, 2_000);
        adapter.registerQuestion(Q, R);
    }

    // Ethereum to Polygon to settlement: the March tallies arrive through the bridge and settle by the ramp
    function test_end_to_end() public {
        reader.set(R, 5853);
        root.relay(R);
        (bool known, uint16 bps) = child.marginBps(R);
        assertTrue(known);
        assertEq(bps, 5853);
        prices.set(Q, 1 ether);
        adapter.settle(Q);
        assertEq(ctf.payout(0), 6421);
        assertEq(ctf.payout(1), 3579);
    }

    // besides a fraction, a share can be zero (no Yes votes) or ASK_AGAIN ("too early" led): both cross intact
    function test_zero_and_ask_again_cross_the_bridge() public {
        bytes32 r2 = keccak256("no-request");
        reader.set(r2, 0);
        root.relay(r2);
        (bool known, uint16 bps) = child.marginBps(r2);
        assertTrue(known);
        assertEq(bps, 0);
        reader.set(R, adapter.ASK_AGAIN());
        root.relay(R);
        prices.set(Q, 1 ether);
        vm.expectRevert(TallyAdapter.AskAgain.selector);
        adapter.settle(Q);
    }

    // the child end on its own, as the state-sync bridge calls it (measured by the gas report)
    function test_child_receives_from_the_bridge() public {
        vm.prank(address(fxChild));
        child.processMessageFromRoot(1, address(root), abi.encode(R, uint16(5853)));
        (bool known, uint16 bps) = child.marginBps(R);
        assertTrue(known);
        assertEq(bps, 5853);
    }

    function test_unknown_share_is_not_relayed() public {
        vm.expectRevert(TallyRootTunnel.Unknown.selector);
        root.relay(R);
    }

    function test_child_rejects_other_senders() public {
        vm.expectRevert(TallyChildTunnel.NotBridge.selector);
        child.processMessageFromRoot(1, address(root), abi.encode(R, uint16(9000)));
        vm.prank(address(fxChild));
        vm.expectRevert(TallyChildTunnel.NotRoot.selector);
        child.processMessageFromRoot(1, address(0xBEEF), abi.encode(R, uint16(9000)));
    }

    function test_child_tunnel_is_wired_once() public {
        vm.expectRevert(TallyRootTunnel.AlreadySet.selector);
        root.setChildTunnel(address(0xBEEF));
    }
}
