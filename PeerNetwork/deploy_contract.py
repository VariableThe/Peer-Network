#!/usr/bin/env python3
"""Deploy DataTransfer.sol to a running Ganache node.

Uses the Truffle artifact (ABI + bytecode) produced by the last solc 0.8.21
build, so no solc/Truffle install is required.

Usage:
    python deploy_contract.py [--rpc http://127.0.0.1:8545] [--from 0x...]
"""

import argparse
import json
import pathlib
import sys

from web3 import Web3
from web3.middleware.proof_of_authority import ExtraDataToPOAMiddleware

ARTIFACT = pathlib.Path(__file__).parent / "Project" / "build" / "contracts" / "DataTransfer.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rpc", default="http://127.0.0.1:8545", help="JSON-RPC endpoint")
    parser.add_argument("--from", dest="sender", default=None, help="deployer address (default: first Ganache account)")
    args = parser.parse_args()

    artifact = json.loads(ARTIFACT.read_text())
    abi = artifact["abi"]
    bytecode = artifact["bytecode"]
    if not bytecode or bytecode == "0x":
        print(f"error: no bytecode in {ARTIFACT}", file=sys.stderr)
        return 1

    w3 = Web3(Web3.HTTPProvider(args.rpc))
    if not w3.is_connected():
        print(f"error: cannot connect to {args.rpc}", file=sys.stderr)
        return 1
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

    sender = Web3.to_checksum_address(args.sender) if args.sender else w3.eth.accounts[0]
    factory = w3.eth.contract(abi=abi, bytecode=bytecode)

    tx_hash = factory.constructor().transact({"from": sender, "gas": 3_000_000})
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    if receipt.status != 1:
        print(f"error: deployment reverted (tx {tx_hash.hex()})", file=sys.stderr)
        return 1

    print(f"deployer: {sender}")
    print(f"tx:       {tx_hash.hex()}")
    print(f"block:    {receipt.blockNumber}")
    print(f"contract: {receipt.contractAddress}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
