# CertiChain — Blockchain Component

## Overview
CertiChain is a blockchain-based certificate verification system designed to help verify the authenticity of certificates and identify revoked certificates.

This component uses a Solidity smart contract to record certificate hashes and manage authorized certificate issuers.

## Technology Used
- Solidity
- Remix IDE
- Ethereum Virtual Machine (EVM)

## Smart Contract
**File:** `Certificate.sol`

The `Certificate` smart contract supports the following features:

- **Issuer authorization:** The contract owner can authorize certificate issuers.
- **Issuer removal:** The owner can remove an authorized issuer.
- **Certificate issuance:** Authorized issuers can register certificates using a certificate ID and hash.
- **Certificate verification:** Anyone can check whether a certificate exists and retrieve its hash, issuer, issue timestamp, and revocation status.
- **Certificate revocation:** The original issuer can revoke a certificate, provided the issuer remains authorized.

## Contract Testing
The contract was compiled and tested in Remix IDE using the Remix VM.

Tests performed:
- Compiled and deployed the smart contract.
- Issued and verified a test certificate.
- Revoked a certificate and checked its status.
- Authorized a second issuer and tested certificate issuance.
- Removed the second issuer and confirmed that the authorization check returned `false`.

## Project Files
- `Certificate.sol` — Solidity smart contract source code.
- `Certificate.abi.json` — Application Binary Interface (ABI), used by applications to interact with the contract.
- `README.md` — Documentation for the blockchain component.

## Important Notes
The contract was tested using the Remix VM, which is a temporary development environment. The deployed contract address is not a permanent shared deployment address.

A shared test-network or local-network deployment and backend integration are still required.

Only certificate identifiers and hashes should be stored on-chain; avoid storing confidential certificate information directly on the blockchain.

## Status
Smart contract development and initial testing are complete. File organization, GitHub submission, backend integration, and shared deployment remain as next steps.
