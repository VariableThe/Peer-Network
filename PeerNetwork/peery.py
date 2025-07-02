import os
import sys
import json
import sqlite3
import time
import threading
import getpass
from web3 import Web3
from web3.middleware.proof_of_authority import ExtraDataToPOAMiddleware
from eth_utils import event_abi_to_log_topic, abi

# Directly embedded ABI from your contract
CONTRACT_ABI = [
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "uint256", "name": "requestId", "type": "uint256"},
            {"indexed": True, "internalType": "address", "name": "requester", "type": "address"},
            {"indexed": False, "internalType": "string", "name": "dbQuery", "type": "string"}
        ],
        "name": "RequestCreated",
        "type": "event"
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "uint256", "name": "requestId", "type": "uint256"},
            {"indexed": True, "internalType": "address", "name": "responder", "type": "address"},
            {"indexed": False, "internalType": "string", "name": "response", "type": "string"}
        ],
        "name": "ResponseSent",
        "type": "event"
    },
    {
        "inputs": [{"internalType": "string", "name": "_dbQuery", "type": "string"}],
        "name": "createRequest",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "uint256", "name": "_requestId", "type": "uint256"}],
        "name": "getRequest",
        "outputs": [
            {"internalType": "address", "name": "requester", "type": "address"},
            {"internalType": "string", "name": "dbQuery", "type": "string"},
            {"internalType": "bool", "name": "fulfilled", "type": "bool"},
            {"internalType": "string", "name": "response", "type": "string"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "nextRequestId",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "name": "requests",
        "outputs": [
            {"internalType": "address", "name": "requester", "type": "address"},
            {"internalType": "string", "name": "dbQuery", "type": "string"},
            {"internalType": "bool", "name": "fulfilled", "type": "bool"},
            {"internalType": "string", "name": "response", "type": "string"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "_requestId", "type": "uint256"},
            {"internalType": "string", "name": "_response", "type": "string"}
        ],
        "name": "submitResponse",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]

def get_input(prompt, password=False):
    if password:
        return getpass.getpass(prompt)
    return input(prompt).strip()

# --- Setup ---
print("\n" + "="*50)
print("PEER NODE SETUP")
print("="*50)

ganache_url = get_input("Enter Ganache URL [default: http://127.0.0.1:8545]: ") or "http://127.0.0.1:8545"
contract_address = get_input("Enter contract address: ")
private_key = get_input("Enter your private key: ", password=True)
db_path = get_input("Enter database path (e.g., peer1.db): ")

# Web3 Setup
w3 = Web3(Web3.HTTPProvider(ganache_url))
if not w3.is_connected():
    print("\n❌ Error: Could not connect to Ganache at", ganache_url)
    sys.exit(1)

w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

try:
    acct = w3.eth.account.from_key(private_key)
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(contract_address),
        abi=CONTRACT_ABI
    )
    print("\n✅ Connection successful! Account:", acct.address)
    print("   Contract address:", contract_address)
    print("   Database path:", db_path)
    print("   Account balance:", w3.from_wei(w3.eth.get_balance(acct.address), 'ether'), "ETH")
except Exception as e:
    print(f"\n❌ Error: {str(e)}")
    sys.exit(1)

# --- Helper Functions ---
def handle_query(db_path, query):
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(query)
        result = cur.fetchall()
        conn.close()
        return json.dumps(result)
    except Exception as e:
        return f"Error: {str(e)}"

def listen_for_requests():
    print("\n🔊 Listening for new requests...")
    event_abi = contract.events.RequestCreated._get_event_abi()
    request_created_topic = event_abi_to_log_topic(event_abi)
    last_block = w3.eth.block_number
    
    while True:
        try:
            current_block = w3.eth.block_number
            if current_block > last_block:
                for block_num in range(last_block + 1, current_block + 1):
                    block = w3.eth.get_block(block_num, full_transactions=True)
                    for tx in block.transactions:
                        if tx.to and tx.to.lower() == contract.address.lower():
                            receipt = w3.eth.get_transaction_receipt(tx.hash)
                            for log in receipt['logs']:
                                if log['topics'] and log['topics'][0] == request_created_topic:
                                    try:
                                        event_data = contract.events.RequestCreated().process_log(log)
                                        req_id = event_data.args.requestId
                                        db_query = event_data.args.dbQuery
                                        print(f"\n📩 New request {req_id}: {db_query}")
                                        response = handle_query(db_path, db_query)
                                        send_response(req_id, response)
                                    except Exception as e:
                                        print(f"⚠️ Event processing error: {str(e)}")
                last_block = current_block
            time.sleep(2)
        except Exception as e:
            print(f"⚠️ Event listening error: {str(e)}")
            time.sleep(5)

def send_response(req_id, response):
    try:
        # Estimate gas dynamically
        gas_estimate = contract.functions.submitResponse(req_id, response).estimate_gas({
            'from': acct.address
        })
        
        tx = contract.functions.submitResponse(req_id, response).build_transaction({
            'from': acct.address,
            'nonce': w3.eth.get_transaction_count(acct.address),
            'gas': gas_estimate + 50000,  # Add 50k buffer
            'gasPrice': w3.to_wei('10', 'gwei')
        })
        
        signed = w3.eth.account.sign_transaction(tx, private_key)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        print(f"⏳ Response submitted for request {req_id}, tx: {tx_hash.hex()}")
        
        # Wait for confirmation
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        if receipt.status == 1:
            print(f"✅ Response confirmed in block {receipt.blockNumber}")
        else:
            print("❌ Transaction failed")
    except Exception as e:
        print(f"❌ Failed to send response: {str(e)}")

def make_request():
    query = input("\nEnter SQL query: ").strip()
    if not query:
        print("❌ Query cannot be empty!")
        return
        
    try:
        # Estimate gas dynamically
        gas_estimate = contract.functions.createRequest(query).estimate_gas({
            'from': acct.address
        })
        
        tx = contract.functions.createRequest(query).build_transaction({
            'from': acct.address,
            'nonce': w3.eth.get_transaction_count(acct.address),
            'gas': gas_estimate + 50000,  # Add 50k buffer
            'gasPrice': w3.to_wei('10', 'gwei')
        })
        
        signed = w3.eth.account.sign_transaction(tx, private_key)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        print(f"📨 Request sent, tx: {tx_hash.hex()}")
        print("   Use 'response <id>' to check later")
        
        # Wait for confirmation
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        if receipt.status == 1:
            print(f"✅ Request confirmed in block {receipt.blockNumber}")
        else:
            print("❌ Transaction failed")
    except Exception as e:
        print(f"❌ Failed to send request: {str(e)}")

def get_response():
    try:
        req_id = int(input("Enter request ID: "))
        req = contract.functions.getRequest(req_id).call()
        print(f"\n🔍 Request {req_id} details:")
        print(f"   Requester: {req[0]}")
        print(f"   Query: {req[1]}")
        print(f"   Status: {'✅ Fulfilled' if req[2] else '⌛ Pending'}")
        if req[2] and req[3]:
            try:
                parsed = json.loads(req[3])
                print("   Response (parsed):")
                for row in parsed:
                    print("   ", row)
            except:
                print(f"   Response: {req[3]}")
    except Exception as e:
        print(f"❌ Error: {str(e)}")

# --- Main Loop ---
if __name__ == "__main__":
    threading.Thread(target=listen_for_requests, daemon=True).start()
    
    print("\n" + "="*50)
    print("PEER NODE COMMANDS")
    print("="*50)
    print("request   - Make new data request")
    print("response  - Check request status")
    print("balance   - Show account balance")
    print("exit      - Shutdown node")
    print("="*50)
    
    while True:
        try:
            cmd = input("\n> ").strip().lower()
            
            if cmd == "request":
                make_request()
            elif cmd == "response":
                get_response()
            elif cmd == "balance":
                balance = w3.eth.get_balance(acct.address)
                print(f"💰 Balance: {w3.from_wei(balance, 'ether')} ETH")
            elif cmd == "exit":
                print("Shutting down...")
                break
            else:
                print("❌ Invalid command. Options: request, response, balance, exit")
        except KeyboardInterrupt:
            print("\nShutting down...")
            break
        except Exception as e:
            print(f"⚠️ Unexpected error: {str(e)}")

