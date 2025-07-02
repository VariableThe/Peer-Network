from web3 import Web3, Account
import sqlite3
import json
import time

# Connect to Ganache
w3 = Web3(Web3.HTTPProvider("http://127.0.0.1:8545"))
assert w3.is_connected()  # Corrected from isConnected()
# Load account
private_key = "0x02e2e370fb72b1bc75628b39e26a69a3a9bfd106325bd73e1d4fb37fdb7c68b5"  # Replace with Peer 3's private key from Ganache
account = Account.from_key(private_key)

# Load smart contract
contract_address = "0xcA732F0246E97a3D6A5fC7EAd7a4342fA01cDa26"  # Replace with the deployed contract address
with open("ethereum-project/build/contracts/DataTransfer.json") as f:
    abi = json.load(f)["abi"]
contract = w3.eth.contract(address=contract_address, abi=abi)

# Connect to SQLite database
db = sqlite3.connect("peer3.db")
cursor = db.cursor()

# Function to handle data requests
def handle_request(request_id, data_key):
    cursor.execute("SELECT value, model_number FROM data WHERE key=?", (data_key,))
    result = cursor.fetchone()
    if result:
        sensor_value, sensor_model = result
        print(f"Fulfilling request {request_id} with data {sensor_value}, model {sensor_model}")
        tx = contract.functions.fulfillRequest(
            request_id, sensor_value, sensor_model
        ).buildTransaction({
            "from": account.address,
            "nonce": w3.eth.getTransactionCount(account.address),
            "gas": 100000,
            "gasPrice": w3.toWei("10", "gwei"),
        })
        signed_tx = w3.eth.account.signTransaction(tx, private_key)
        tx_hash = w3.eth.sendRawTransaction(signed_tx.rawTransaction)
        print(f"Transaction sent: {tx_hash.hex()}")

# Simulate a peer requesting data
def request_data():
    data_key = "sensor7"  # Key of the data being requested
    tx = contract.functions.requestData(data_key).buildTransaction({
        "from": account.address,
        "nonce": w3.eth.getTransactionCount(account.address),
        "gas": 100000,
        "gasPrice": w3.toWei("10", "gwei"),
    })
    signed_tx = w3.eth.account.signTransaction(tx, private_key)
    tx_hash = w3.eth.sendRawTransaction(signed_tx.rawTransaction)
    print(f"Data request sent: {tx_hash.hex()}")

# Continuously check for new requests
def monitor_requests():
    last_request_count = 0
    while True:
        request_count = contract.functions.requestCount().call()
        for request_id in range(last_request_count, request_count):
            request = contract.functions.requests(request_id).call()
            if not request[3] and request[0] != account.address:  # If not fulfilled and not our own request
                print(f"Found new request ID {request_id} for data key {request[2]}")
                handle_request(request_id, request[2])
        last_request_count = request_count
        time.sleep(5)  # Poll every 5 seconds

# Example usage
if __name__ == "__main__":
    # Start monitoring for requests
    monitor_requests()
