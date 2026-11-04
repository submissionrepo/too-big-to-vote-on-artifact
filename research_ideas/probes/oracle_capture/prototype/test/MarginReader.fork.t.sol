// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";
import {MarginReader} from "../src/MarginReader.sol";
import {IVotingV2} from "../src/Interfaces.sol";

/// Fork test against mainnet VotingV2: the two requests of the 2025-03 rare-earth market, indices 828 and 827 in
/// resolvedPriceRequestIds, resolved in round 10085. Expected margins: 11,465,793 / 22,845,748.88 = 50.18% and
/// 12,292,521 / 22,845,748.88 = 53.80% of the staked supply. Run with FORK_URL set; skipped otherwise.
contract MarginReaderForkTest is Test {
    IVotingV2 constant VOTING = IVotingV2(0x004395edb43EFca9885CEdad51EC9fAf93Bd34ac);

    function test_margin_of_march_2025_requests() public {
        string memory url = vm.envOr("FORK_URL", string(""));
        if (bytes(url).length == 0) {
            emit log("FORK_URL not set; skipping");
            return;
        }
        vm.createSelectFork(url);
        MarginReader reader = new MarginReader(VOTING);

        bytes32 id828 = VOTING.resolvedPriceRequestIds(828);
        bytes32 id827 = VOTING.resolvedPriceRequestIds(827);
        uint256 g0 = gasleft();
        uint16 m828 = reader.register(id828, 828);
        uint256 gasRegister = g0 - gasleft();
        uint16 m827 = reader.register(id827, 827);

        emit log_named_uint("margin bps 828", m828);
        emit log_named_uint("margin bps 827", m827);
        emit log_named_uint("gas register", gasRegister);
        assertEq(m828, 5018);
        assertEq(m827, 5380);
        assertEq(reader.roundOf(id828), 10085);

        (bool known, uint16 bps) = reader.marginBps(id828);
        assertTrue(known);
        assertEq(bps, 5018);

        vm.expectRevert();
        reader.register(id828, 827); // wrong index
    }
}
