"""Minimal ABI helpers for decoding UMA VotingV2 / Staker events and eth_call results.

No web3 dependency: keccak from pycryptodome, decoding by hand. Only the types used by the
UMA contracts are supported (address, bool, uintN, intN, bytes32, bytes, string).
"""
from Crypto.Hash import keccak


def keccak256(data: bytes) -> bytes:
    h = keccak.new(digest_bits=256)
    h.update(data)
    return h.digest()


def event_topic(signature: str) -> str:
    return "0x" + keccak256(signature.encode()).hex()


def selector(signature: str) -> str:
    return "0x" + keccak256(signature.encode()).hex()[:8]


def _word(data: bytes, i: int) -> bytes:
    return data[32 * i:32 * (i + 1)]


def decode_uint(word: bytes) -> int:
    return int.from_bytes(word, "big")


def decode_int(word: bytes) -> int:
    v = int.from_bytes(word, "big")
    return v - (1 << 256) if v >> 255 else v


def decode_address(word: bytes) -> str:
    return "0x" + word[-20:].hex()


def decode_topic_address(topic: str) -> str:
    return "0x" + topic[-40:]


def decode_data(types, data_hex: str):
    """Decode the non-indexed event parameters (or a function return) given a list of type strings."""
    data = bytes.fromhex(data_hex[2:] if data_hex.startswith("0x") else data_hex)
    out = []
    for i, t in enumerate(types):
        w = _word(data, i)
        if t == "address":
            out.append(decode_address(w))
        elif t == "bool":
            out.append(bool(decode_uint(w)))
        elif t.startswith("uint"):
            out.append(decode_uint(w))
        elif t.startswith("int"):
            out.append(decode_int(w))
        elif t == "bytes32":
            out.append("0x" + w.hex())
        elif t in ("bytes", "string"):
            off = decode_uint(w)
            ln = decode_uint(data[off:off + 32])
            raw = data[off + 32:off + 32 + ln]
            out.append(raw.decode("utf-8", "replace") if t == "string" else "0x" + raw.hex())
        else:
            raise ValueError(f"unsupported type {t}")
    return out


def encode_call(signature: str, args=()):
    """ABI-encode a call with only static arguments (address / uint)."""
    data = selector(signature)
    for a in args:
        if isinstance(a, str) and a.startswith("0x") and len(a) == 42:
            data += a[2:].lower().rjust(64, "0")
        elif isinstance(a, int):
            data += format(a % (1 << 256), "064x")
        else:
            raise ValueError(f"unsupported arg {a!r}")
    return data


def ancillary_to_text(hex_bytes: str) -> str:
    raw = bytes.fromhex(hex_bytes[2:])
    return raw.decode("utf-8", "replace")


# Event definitions: name -> (signature, indexed types in topic order, non-indexed types in data order, field names)
EVENTS = {
    "VoteRevealed": (
        "VoteRevealed(address,address,uint32,bytes32,uint256,bytes,int256,uint128)",
        ["address", "address", "bytes32"],
        ["uint32", "uint256", "bytes", "int256", "uint128"],
        ["voter", "caller", "roundId", "identifier", "time", "ancillaryData", "price", "numTokens"],
    ),
    "RequestAdded": (
        "RequestAdded(address,uint32,bytes32,uint256,bytes,bool)",
        ["address", "uint32", "bytes32"],
        ["uint256", "bytes", "bool"],
        ["requester", "roundId", "identifier", "time", "ancillaryData", "isGovernance"],
    ),
    "RequestResolved": (
        "RequestResolved(uint32,uint256,bytes32,uint256,bytes,int256)",
        ["uint32", "uint256", "bytes32"],
        ["uint256", "bytes", "int256"],
        ["roundId", "resolvedPriceRequestIndex", "identifier", "time", "ancillaryData", "price"],
    ),
    "RequestRolled": (
        "RequestRolled(bytes32,uint256,bytes,uint32)",
        ["bytes32", "uint256"],
        ["bytes", "uint32"],
        ["identifier", "time", "ancillaryData", "rollCount"],
    ),
    "RequestDeleted": (
        "RequestDeleted(bytes32,uint256,bytes,uint32)",
        ["bytes32", "uint256"],
        ["bytes", "uint32"],
        ["identifier", "time", "ancillaryData", "rollCount"],
    ),
    "GatAndSpatChanged": (
        "GatAndSpatChanged(uint128,uint64)",
        [],
        ["uint128", "uint64"],
        ["newGat", "newSpat"],
    ),
    "SlashingLibraryChanged": (
        "SlashingLibraryChanged(address)",
        [],
        ["address"],
        ["newAddress"],
    ),
    "MaxRollsChanged": (
        "MaxRollsChanged(uint32)",
        [],
        ["uint32"],
        ["newMaxRolls"],
    ),
    "VoterSlashed": (
        "VoterSlashed(address,uint256,int128)",
        ["address", "uint256"],
        ["int128"],
        ["voter", "requestIndex", "slashedTokens"],
    ),
    "VoterSlashApplied": (
        "VoterSlashApplied(address,int128,uint128)",
        ["address"],
        ["int128", "uint128"],
        ["voter", "slashedTokens", "postStake"],
    ),
    "Staked": (
        "Staked(address,address,uint128,uint128,uint128,uint128)",
        ["address", "address"],
        ["uint128", "uint128", "uint128", "uint128"],
        ["voter", "from", "amount", "voterStake", "voterPendingUnstake", "cumulativeStake"],
    ),
    "RequestedUnstake": (
        "RequestedUnstake(address,uint128,uint64,uint128)",
        ["address"],
        ["uint128", "uint64", "uint128"],
        ["voter", "amount", "unstakeTime", "voterStake"],
    ),
    "ExecutedUnstake": (
        "ExecutedUnstake(address,uint128,uint128)",
        ["address"],
        ["uint128", "uint128"],
        ["voter", "tokensSent", "voterStake"],
    ),
    "DelegateSet": (
        "DelegateSet(address,address)",
        ["address", "address"],
        [],
        ["delegator", "delegate"],
    ),
    "DelegatorSet": (
        "DelegatorSet(address,address)",
        ["address", "address"],
        [],
        ["delegate", "delegator"],
    ),
    "SetNewEmissionRate": (
        "SetNewEmissionRate(uint128)",
        [],
        ["uint128"],
        ["newEmissionRate"],
    ),
    "SetNewUnstakeCoolDown": (
        "SetNewUnstakeCoolDown(uint64)",
        [],
        ["uint64"],
        ["newUnstakeCoolDown"],
    ),
}

TOPIC_TO_EVENT = {event_topic(sig): name for name, (sig, _, _, _) in EVENTS.items()}


def _decode_topic(t: str, typ: str):
    if typ == "address":
        return decode_topic_address(t)
    w = bytes.fromhex(t[2:])
    if typ.startswith("uint"):
        return decode_uint(w)
    if typ.startswith("int"):
        return decode_int(w)
    return t  # bytes32


def decode_log(log: dict):
    """Return (event name, dict of fields) or (None, None) for unknown topics."""
    name = TOPIC_TO_EVENT.get(log["topics"][0])
    if name is None:
        return None, None
    sig, itypes, dtypes, names = EVENTS[name]
    indexed_vals = [_decode_topic(t, typ) for t, typ in zip(log["topics"][1:], itypes)]
    data_vals = decode_data(dtypes, log["data"]) if dtypes else []
    # Field order in `names` follows the Solidity declaration; indexed fields were listed first in itypes
    # in declaration order, so merge by walking the declaration.
    fields = {}
    ii = di = 0
    # Reconstruct declaration order from the signature's parameter list and the indexed flags.
    params = sig[sig.index("(") + 1:-1].split(",")
    indexed_set = _indexed_positions(name)
    for pos, _ in enumerate(params):
        if pos in indexed_set:
            fields[names[pos]] = indexed_vals[ii]
            ii += 1
        else:
            fields[names[pos]] = data_vals[di]
            di += 1
    fields["blockNumber"] = int(log["blockNumber"], 16)
    fields["txHash"] = log["transactionHash"]
    fields["logIndex"] = int(log["logIndex"], 16)
    return name, fields


# Positions (0-based, in declaration order) of indexed parameters for each event, read off the Solidity source.
_INDEXED = {
    "VoteRevealed": {0, 1, 3},
    "RequestAdded": {0, 1, 2},
    "RequestResolved": {0, 1, 2},
    "RequestRolled": {0, 1},
    "RequestDeleted": {0, 1},
    "GatAndSpatChanged": set(),
    "SlashingLibraryChanged": set(),
    "MaxRollsChanged": set(),
    "VoterSlashed": {0, 1},
    "VoterSlashApplied": {0},
    "Staked": {0, 1},
    "RequestedUnstake": {0},
    "ExecutedUnstake": {0},
    "DelegateSet": {0, 1},
    "DelegatorSet": {0, 1},
    "SetNewEmissionRate": set(),
    "SetNewUnstakeCoolDown": set(),
}


def _indexed_positions(name):
    return _INDEXED[name]


if __name__ == "__main__":
    for name, (sig, _, _, _) in EVENTS.items():
        print(f"{name:24s} {event_topic(sig)}")
