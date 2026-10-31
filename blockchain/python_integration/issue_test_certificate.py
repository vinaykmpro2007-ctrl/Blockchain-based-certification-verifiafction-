
import json
from pathlib import Path
from web3 import Web3

# Connect to the local blockchain
w3 = Web3(Web3.HTTPProvider("http://127.0.0.1:8545"))

if not w3.is_connected():
    raise ConnectionError("Could not connect to the local blockchain.")

# Locate the deployed contract files
blockchain_folder = Path(__file__).resolve().parent.parent

deployment_file = (
    blockchain_folder / "local-chain" / "scripts" / "deployment.json"
)
artifact_file = (
    blockchain_folder
    / "local-chain"
    / "artifacts"
    / "contracts"
    / "Certificate.sol"
    / "Certificate.json"
)

with deployment_file.open("r", encoding="utf-8") as file:
    deployment = json.load(file)

with artifact_file.open("r", encoding="utf-8") as file:
    artifact = json.load(file)

contract = w3.eth.contract(
    address=Web3.to_checksum_address(deployment["address"]),
    abi=artifact["abi"],
)

# Create a demo certificate and its SHA-256-style 32-byte identifier
certificate_id = "DEMO-LOCAL-001"
certificate_hash = Web3.keccak(text=certificate_id)

# Use Hardhat's first local test account (not a real wallet)
issuer = w3.eth.accounts[0]

print("Issuing test certificate...")

tx_hash = contract.functions.issueCertificate(
    certificate_id,
    certificate_hash,
).transact({"from": issuer})

receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

print("Certificate ID:", certificate_id)
print("Issuer:", issuer)
print("Transaction hash:", tx_hash.hex())
print("Transaction status:", receipt.status)
