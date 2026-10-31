
import hashlib
import os


def generate_hash(file_path):
    """Generate SHA-256 hash of a certificate PDF."""

    sha256_hash = hashlib.sha256()

    with open(file_path, "rb") as file:
        for chunk in iter(lambda: file.read(4096), b""):
            sha256_hash.update(chunk)

    return sha256_hash.hexdigest()


def verify_hash(file_path, original_hash):
    """Check whether the certificate has been modified."""

    current_hash = generate_hash(file_path)

    return current_hash == original_hash


if __name__ == "__main__":

    certificate_path = "qr_certificates/generated/sample_certificate.pdf"

    if os.path.exists(certificate_path):

        # Generate original hash
        original_hash = generate_hash(certificate_path)

        print("Original SHA-256 Hash:")
        print(original_hash)

        # Test original certificate
        print("\nOriginal certificate verification:")
        print("Valid:", verify_hash(certificate_path, original_hash))

        # Create a temporary modified copy
        tampered_path = "qr_certificates/generated/tampered_copy.pdf"

        with open(certificate_path, "rb") as original:
            with open(tampered_path, "wb") as copy:
                copy.write(original.read())
                copy.write(b"\nTAMPERED")

        # Test modified certificate
        print("\nModified certificate verification:")
        print("Valid:", verify_hash(tampered_path, original_hash))

        # Delete temporary copy
        os.remove(tampered_path)

        print("\nSHA-256 tampering test completed!")

    else:
        print("Certificate PDF not found!")


