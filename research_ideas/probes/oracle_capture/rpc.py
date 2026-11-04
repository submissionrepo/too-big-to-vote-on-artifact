"""Tiny JSON-RPC client over public Ethereum endpoints with rotation and retries.

Tested 2026-10-06: publicnode serves latest-state calls and block headers but refuses historical eth_getLogs
("Archive requests require a personal token"); drpc (free) and mevblocker serve historical eth_getLogs for
ranges up to 10,000 blocks. 1rpc / blastapi / nodies cap ranges at 10-50 blocks and are not used for logs.
"""
import time

import requests

STATE_ENDPOINTS = [
    "https://ethereum-rpc.publicnode.com",
    "https://eth.drpc.org",
    "https://rpc.mevblocker.io",
]
import os

# drpc's free tier answers every eth_getLogs with "ranges over 10000 blocks are not supported" regardless of the
# actual span (tested 50..9000 blocks, recent and historical). The four below returned identical log sets for a
# 9,000-block historical window on 2026-10-06. LOG_ENDPOINT=<url> pins one endpoint (used to run parallel fetchers).
LOG_ENDPOINTS = [os.environ["LOG_ENDPOINT"]] if os.environ.get("LOG_ENDPOINT") else [
    "https://rpc.mevblocker.io",
    "https://mainnet.gateway.tenderly.co",
    "https://eth-mainnet.g.alchemy.com/v2/demo",
]
MAX_LOG_RANGE = 9_000

VOTING_V2 = "0x004395edb43EFca9885CEdad51EC9fAf93Bd34ac"

RANGE_ERROR_KEYS = ("range", "limit", "too many", "exceed", "10000", "10,000", "response size", "archive",
                    "too large")


class RangeError(RuntimeError):
    pass


class Rpc:
    def __init__(self, timeout=90):
        self.timeout = timeout
        self.calls = 0
        self.i_state = 0
        self.i_log = 0

    def _call(self, endpoints, idx_attr, method, params, retries=8):
        last = None
        for attempt in range(retries):
            i = getattr(self, idx_attr)
            url = endpoints[i % len(endpoints)]
            try:
                r = requests.post(url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
                                  timeout=self.timeout)
                self.calls += 1
                j = r.json()
                if "error" in j:
                    msg = str(j["error"])
                    last = RuntimeError(f"{url}: {msg[:160]}")
                    if any(k in msg.lower() for k in RANGE_ERROR_KEYS):
                        raise RangeError(str(last))
                    setattr(self, idx_attr, i + 1)
                    time.sleep(0.5 * (attempt + 1))
                    continue
                return j["result"]
            except RangeError:
                raise
            except (requests.RequestException, ValueError) as e:
                last = e
                setattr(self, idx_attr, i + 1)
                time.sleep(0.5 * (attempt + 1))
        raise RuntimeError(f"rpc failed after retries: {last}")

    def call(self, method, params):
        return self._call(STATE_ENDPOINTS, "i_state", method, params)

    def block_number(self):
        return int(self.call("eth_blockNumber", []), 16)

    def get_logs(self, address, topics, from_block, to_block):
        """eth_getLogs over the log endpoints; the caller keeps ranges <= MAX_LOG_RANGE."""
        return self._call(LOG_ENDPOINTS, "i_log", "eth_getLogs", [{
            "address": address,
            "topics": topics,
            "fromBlock": hex(from_block),
            "toBlock": hex(to_block),
        }])

    def get_logs_range(self, address, topics, from_block, to_block, step=MAX_LOG_RANGE):
        """Fetch a long range in chunks, halving a chunk when an endpoint complains about size."""
        out = []
        b = from_block
        while b <= to_block:
            cur = min(step, to_block - b + 1)
            while True:
                try:
                    out += self.get_logs(address, topics, b, b + cur - 1)
                    break
                except RangeError:
                    if cur <= 200:
                        raise
                    cur //= 2
            b += cur
        return out

    def eth_call(self, to, data, block="latest"):
        return self.call("eth_call", [{"to": to, "data": data}, block])

    def get_block(self, number):
        return self.call("eth_getBlockByNumber", [hex(number) if isinstance(number, int) else number, False])
