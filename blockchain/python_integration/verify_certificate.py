
import json
from pathlib import Path
from web3 import Web3

# Connect Python to the local blockchain
w3 = Web3(Web3.HTTPProvider("http://127.0.0.1:8545"))

if not w3.is_connected():
    raise ConnectionError("Could not connect to the local blockchain.")

# Load the deployed contract address
blockchain_folder = Path(__file__).resolve().parent.parent
deployment_file = (
    blockchain_folder
    / "local-chain"
    / "scripts"
    / "deployment.json"
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

contract_address = Web3.to_checksum_address(deployment["address"])

contract = w3.eth.contract(
    address=contract_address,
    abi=artifact["abi"],
)

print("Connected to blockchain:", w3.is_connected())
print("Contract address:", contract_address)
print("Contract owner:", contract.functions.owner().call())

# Try verifying a certificate ID
certificate_id = input("Enter certificate ID to verify: ").strip()

result = contract.functions.verifyCertificate(certificate_id).call()
exists, certificate_hash, issuer, issued_at, revoked = result

if not exists:
    print("Result: Certificate not found.")
else:
    print("Result:", "REVOKED" if revoked else "CERTIFICATE EXISTS")
    print("Certificate hash:", Web3.to_hex(certificate_hash))
    print("Issuer:", issuer)
    print("Issued at (Unix timestamp):", issued_at)
