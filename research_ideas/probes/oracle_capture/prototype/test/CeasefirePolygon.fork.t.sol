// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";

interface IFxChildP {
    function onStateReceive(uint256 stateId, bytes calldata data) external;
}

interface IAdapterP {
    function resolve(bytes32 questionID) external;

    function ready(bytes32 questionID) external view returns (bool);
}

interface ICTFP {
    function payoutNumerators(bytes32 conditionId, uint256 index) external view returns (uint256);

    function balanceOf(address owner, uint256 id) external view returns (uint256);

    function redeemPositions(address collateralToken, bytes32 parentCollectionId, bytes32 conditionId, uint256[] calldata indexSets)
        external;
}

interface IERC20P {
    function balanceOf(address who) external view returns (uint256);
}

interface IManagedOO {
    function settle(address requester, bytes32 identifier, uint256 timestamp, bytes memory ancillaryData)
        external
        returns (uint256);
}

/// The Polygon half of the ceasefire capture, on its own: the state-sync message that the live OracleRootTunnel emits
/// for the DVM's answer is abi.encode(rootTunnel, childTunnel, abi.encode(identifier, time, ancillaryData, price))
/// (FxRoot.sendMessageToChild), built here for either answer; CeasefireCapture.fork.t.sol checks on the Ethereum fork that
/// the root tunnel emits exactly this message. Fixture: fixtures/ceasefire_polygon.json. Run with POLYGON_URL.
contract CeasefirePolygonForkTest is Test {
    IFxChildP constant FX_CHILD = IFxChildP(0x8397259c983751DAf40400790063935a11afa28a);
    address constant SYSTEM = 0x0000000000000000000000000000000000001001;
    IAdapterP constant ADAPTER = IAdapterP(0x65070BE91477460D8A7AeEb94ef92fe056C2f2A7);
    ICTFP constant CTF = ICTFP(0x4D97DCd97eC945f40cF65F87097ACe5EA0476045);
    IERC20P constant USDCE = IERC20P(0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174);
    IManagedOO constant OO = IManagedOO(0x2C0367a9DB231dDeBd88a94b4f6461a6e47C58B1);
    bytes32 constant YES_OR_NO = "YES_OR_NO_QUERY";
    // settle() on the managed oracle is restricted to RESOLVER_ROLE; this holder settled the request on chain
    address constant RESOLVER = 0x9725e8172A108f2BaD87ef31eA4Ea729e939d869;

    function _run(string memory key) internal returns (uint256 y, uint256 n, uint256 held, uint256 paid) {
        string memory json = vm.readFile("fixtures/ceasefire_polygon.json");
        vm.createSelectFork(vm.envString("POLYGON_URL"), vm.parseJsonUint(json, ".polygonForkBlock"));
        bytes32 questionID = vm.parseJsonBytes32(json, ".questionID");
        bytes32 conditionId = vm.parseJsonBytes32(json, ".conditionId");
        assertFalse(ADAPTER.ready(questionID));
        vm.prank(SYSTEM);
        FX_CHILD.onStateReceive(1, vm.parseJsonBytes(json, key));
        emit log_named_string("ready after delivery", ADAPTER.ready(questionID) ? "yes" : "no");
        // as on the chain: the resolver settles the oracle's request (block 85,805,624, through a multicall), passing no
        // price, then the adapter resolves the market
        vm.prank(RESOLVER);
        OO.settle(address(ADAPTER), YES_OR_NO, vm.parseJsonUint(json, ".ooTimestamp"), vm.parseJsonBytes(json, ".ooAncillary"));
        ADAPTER.resolve(questionID);
        y = CTF.payoutNumerators(conditionId, 0);
        n = CTF.payoutNumerators(conditionId, 1);
        uint256 noPosition = vm.parseJsonUint(json, ".noPosition");
        address[] memory holders = vm.parseJsonAddressArray(json, ".noHolders");
        uint256[] memory sets = new uint256[](2);
        sets[0] = 1;
        sets[1] = 2;
        for (uint256 i = 0; i < holders.length; i++) {
            uint256 bal = CTF.balanceOf(holders[i], noPosition);
            if (bal == 0) continue;
            held += bal;
            uint256 before = USDCE.balanceOf(holders[i]);
            vm.prank(holders[i]);
            CTF.redeemPositions(address(USDCE), bytes32(0), conditionId, sets);
            paid += USDCE.balanceOf(holders[i]) - before;
        }
        emit log_named_uint("payout numerator Yes", y);
        emit log_named_uint("payout numerator No", n);
        emit log_named_decimal_uint("No shares held by the listed holders", held, 6);
        emit log_named_decimal_uint("USDC.e paid to them", paid, 6);
    }

    function test_polygon_pays_no() public {
        if (bytes(vm.envOr("POLYGON_URL", string(""))).length == 0) return;
        (uint256 y, uint256 n, uint256 held, uint256 paid) = _run(".messageNo");
        assertEq(y, 0);
        assertEq(n, 1);
        assertEq(paid, held);
    }

    function test_polygon_pays_yes() public {
        if (bytes(vm.envOr("POLYGON_URL", string(""))).length == 0) return;
        (uint256 y, uint256 n, , uint256 paid) = _run(".messageYes");
        assertEq(y, 1);
        assertEq(n, 0);
        assertEq(paid, 0);
    }
}
