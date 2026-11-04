"""The key that identifies a DVM price request across the tables.

identifier, time and round do not identify a request: Polymarket requests settling markets of one event share
them and differ only in their ancillary data. ancKey is a short hash of the ancillary data (0x-prefixed hex as
decoded from the logs); joins use (roundId, requestTime, ancKey).
"""
import hashlib


def anc_key(ancillary_hex):
    return hashlib.sha1(ancillary_hex.lower().encode()).hexdigest()[:16]


def text_hash(text):
    """The ancillaryDataHash a bridged request's text carries (the key of polygon_dispute_map.csv), or None."""
    if text.startswith("ancillaryDataHash:"):
        return text[len("ancillaryDataHash:"):].split(",")[0]
    return None


def req_key(row):
    """Join key of a row of requests_summary.csv, contested_requests.csv, or any table that carries ancKey."""
    return (str(row["roundId"]), str(row["requestTime"]), row["ancKey"])
