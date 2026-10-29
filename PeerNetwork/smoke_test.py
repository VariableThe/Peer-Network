#!/usr/bin/env python3
"""Non-interactive round-trip smoke test for the deployed DataTransfer contract.

Exercises the same code path the peer nodes use: sign a createRequest tx,
then read it back with nextRequestId/getRequest, then have a second account
submit a response and confirm the RequestCreated log decodes.

Usage:
    python smoke_test.py --address 0x<deployed contract>
"""

import argparse
import json
import pathlib
import sys

from eth_utils import event_abi_to_log_topic
from web3 import Web3
from web3.middleware.proof_of_authority import ExtraDataToPOAMiddleware

ARTIFACT = pathlib.Path(__file__).parent / "Project" / "build" / "contracts" / "DataTransfer.json"

# Ganache --wallet.deterministic accounts 0 and 1.
REQUESTER_KEY = "0x4f3edf983ac636a65a842ce7c78d9aa706d3b113bce9c46f30d7d21715b23b1d"
RESPONDER_KEY = "0x6cbed15c793ce57650b9877cf6fa156fbef513c4e6134f022a85b1ffdd59b2a1"

QUERY = "SELECT value, model_number FROM data WHERE key='sensor8'"


def send(w3, contract, fn, key, gas=200_000):
    acct = w3.eth.account.from_key(key)
    tx = fn.build_transaction(
        {
            "from": acct.address,
            "nonce": w3.eth.get_transaction_count(acct.address),
            "gas": gas,
            "gasPrice": w3.eth.gas_price,
            "chainId": w3.eth.chain_id,
        }
    )
    signed = w3.eth.account.sign_transaction(tx, key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    return tx_hash, w3.eth.wait_for_transaction_receipt(tx_hash)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rpc", default="http://127.0.0.1:8545")
    parser.add_argument("--address", required=True, help="deployed DataTransfer address")
    parser.add_argument("--requester-key", default=REQUESTER_KEY)
    parser.add_argument("--responder-key", default=RESPONDER_KEY)
    args = parser.parse_args()

    abi = json.loads(ARTIFACT.read_text())["abi"]
    w3 = Web3(Web3.HTTPProvider(args.rpc))
    if not w3.is_connected():
        print(f"error: cannot connect to {args.rpc}", file=sys.stderr)
        return 1
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

    contract = w3.eth.contract(address=Web3.to_checksum_address(args.address), abi=abi)
    requester = w3.eth.account.from_key(args.requester_key).address
    responder = w3.eth.account.from_key(args.responder_key).address
    print(f"rpc:       {args.rpc} (chain {w3.eth.chain_id})")
    print(f"contract:  {contract.address}")
    print(f"requester: {requester}")
    print(f"responder: {responder}")

    before = contract.functions.nextRequestId().call()
    print(f"\nnextRequestId before: {before}")

    tx_hash, receipt = send(w3, contract, contract.functions.createRequest(responder, QUERY), args.requester_key)
    print(f"createRequest tx: {tx_hash.hex()} status={receipt.status} gasUsed={receipt.gasUsed}")
    if receipt.status != 1:
        print("FAIL: createRequest reverted", file=sys.stderr)
        return 1

    # Decode the RequestCreated event exactly like peer.py's listener does.
    topic = event_abi_to_log_topic(contract.events.RequestCreated._get_event_abi())
    created = [
        contract.events.RequestCreated().process_log(log)
        for log in receipt["logs"]
        if log["topics"] and log["topics"][0] == topic
    ]
    if not created:
        print("FAIL: no RequestCreated event in receipt", file=sys.stderr)
        return 1
    request_id = created[0].args.requestId
    print(f"event:     RequestCreated(id={request_id}, target={created[0].args.target}, query={created[0].args.dbQuery!r})")

    after = contract.functions.nextRequestId().call()
    print(f"nextRequestId after:  {after}")
    if after != before + 1:
        print("FAIL: nextRequestId did not advance by exactly 1", file=sys.stderr)
        return 1

    req = contract.functions.getRequest(request_id).call()
    if len(req) != 5:
        print(f"FAIL: getRequest returned {len(req)} values, expected 5", file=sys.stderr)
        return 1
    got_requester, got_target, got_query, fulfilled, response = req
    print(
        f"getRequest({request_id}): requester={got_requester} target={got_target} "
        f"fulfilled={fulfilled} dbQuery={got_query!r} response={response!r}"
    )
    if (got_requester, got_target, got_query, fulfilled, response) != (requester, responder, QUERY, False, ""):
        print("FAIL: stored request does not match what was sent", file=sys.stderr)
        return 1

    response = json.dumps([["42.5", "DHT22"]])
    tx_hash, receipt = send(w3, contract, contract.functions.submitResponse(request_id, response), args.responder_key)
    print(f"submitResponse tx: {tx_hash.hex()} status={receipt.status}")
    if receipt.status != 1:
        print("FAIL: submitResponse reverted", file=sys.stderr)
        return 1

    req = contract.functions.getRequest(request_id).call()
    print(f"getRequest({request_id}) after response: fulfilled={req[3]} response={req[4]}")
    if not req[3] or req[4] != response:
        print("FAIL: response was not stored", file=sys.stderr)
        return 1

    print("\nPASS: createRequest -> getRequest -> submitResponse round-trip OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
