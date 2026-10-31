
 // SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

contract Certificate {
    address public owner;

    struct CertificateRecord {
        bytes32 certificateHash;
        address issuer;
        uint256 issuedAt;
        bool revoked;
        bool exists;
    }

    mapping(string => CertificateRecord) private certificates;
    mapping(address => bool) public authorizedIssuers;

    event IssuerAuthorized(address indexed issuer);
    event IssuerRemoved(address indexed issuer);

    event CertificateIssued(
        string certificateId,
        bytes32 certificateHash,
        address indexed issuer,
        uint256 issuedAt
    );

    event CertificateRevoked(
        string certificateId,
        address indexed issuer
    );

    modifier onlyOwner() {
        require(msg.sender == owner, "Only owner");
        _;
    }

    modifier onlyAuthorizedIssuer() {
        require(authorizedIssuers[msg.sender], "Not an authorized issuer");
        _;
    }

    constructor() {
        owner = msg.sender;
        authorizedIssuers[msg.sender] = true;
        emit IssuerAuthorized(msg.sender);
    }

    function authorizeIssuer(address issuer) external onlyOwner {
        require(issuer != address(0), "Invalid issuer address");
        require(!authorizedIssuers[issuer], "Already authorized");

        authorizedIssuers[issuer] = true;
        emit IssuerAuthorized(issuer);
    }

    function removeIssuer(address issuer) external onlyOwner {
        require(issuer != address(0), "Invalid issuer address");
        require(authorizedIssuers[issuer], "Issuer not authorized");

        authorizedIssuers[issuer] = false;
        emit IssuerRemoved(issuer);
    }

    function issueCertificate(
        string calldata certificateId,
        bytes32 certificateHash
    ) external onlyAuthorizedIssuer {
        require(bytes(certificateId).length > 0, "Empty certificate ID");
        require(certificateHash != bytes32(0), "Empty certificate hash");
        require(!certificates[certificateId].exists, "Certificate already exists");

        certificates[certificateId] = CertificateRecord({
            certificateHash: certificateHash,
            issuer: msg.sender,
            issuedAt: block.timestamp,
            revoked: false,
            exists: true
        });

        emit CertificateIssued(
            certificateId,
            certificateHash,
            msg.sender,
            block.timestamp
        );
    }

    function revokeCertificate(
        string calldata certificateId
    ) external onlyAuthorizedIssuer {
        CertificateRecord storage record = certificates[certificateId];

        require(record.exists, "Certificate not found");
        require(record.issuer == msg.sender, "Not the original issuer");
        require(!record.revoked, "Already revoked");

        record.revoked = true;
        emit CertificateRevoked(certificateId, msg.sender);
    }

    function verifyCertificate(string calldata certificateId)
        external
        view
        returns (
            bool exists,
            bytes32 certificateHash,
            address issuer,
            uint256 issuedAt,
            bool revoked
        )
    {
        CertificateRecord storage record = certificates[certificateId];

        return (
            record.exists,
            record.certificateHash,
            record.issuer,
            record.issuedAt,
            record.revoked
        );
    }
}
