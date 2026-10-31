
const fs = require("fs");
const path = require("path");
const { ethers } = require("ethers");

async function main() {
  const artifactPath = path.join(
    __dirname,
    "..",
    "artifacts",
    "contracts",
    "Certificate.sol",
    "Certificate.json"
  );

  const artifact = JSON.parse(
    fs.readFileSync(artifactPath, "utf8")
  );

  const provider = new ethers.JsonRpcProvider(
    "http://127.0.0.1:8545"
  );

  // Hardhat's first account is for local testing only.
  const signer = await provider.getSigner(0);

  const factory = new ethers.ContractFactory(
    artifact.abi,
    artifact.bytecode,
    signer
  );

  console.log("Deploying Certificate contract...");

  const contract = await factory.deploy();
  await contract.waitForDeployment();

  const address = await contract.getAddress();

  console.log("Contract deployed successfully!");
  console.log("Contract address:", address);
  console.log("Owner:", await contract.owner());

  fs.writeFileSync(
    path.join(__dirname, "deployment.json"),
    JSON.stringify({ address }, null, 2)
  );

  console.log("Deployment address saved to scripts/deployment.json");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
