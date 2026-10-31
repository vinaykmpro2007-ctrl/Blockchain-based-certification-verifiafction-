
import json
from pathlib import Path
from web3 import Web3

w3 = Web3(Web3.HTTPProvider("http://127.0.0.1:8545"))

if not w3.is_connected():
    raise ConnectionError("Could not connect to the local blockchain.")

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

certificate_id = "DEMO-LOCAL-001"
issuer = w3.eth.accounts[0]

print("Revoking certificate:", certificate_id)

tx_hash = contract.functions.revokeCertificate(
    certificate_id
).transact({"from": issuer})

receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

print("Transaction hash:", tx_hash.hex())
print("Transaction status:", receipt.status)

result = contract.functions.verifyCertificate(certificate_id).call()
exists, certificate_hash, issuer_address, issued_at, revoked = result

print("Certificate exists:", exists)
print("Certificate revoked:", revoked)
print("Result:", "REVOKED" if revoked else "NOT REVOKED")
