
import unittest
import tempfile
import os
import shutil

from qr_certificates.generate_pdf import generate_certificate
from qr_certificates.hash_certificate import generate_hash, verify_hash


class TestCertificateIntegration(unittest.TestCase):

    def test_complete_certificate_workflow(self):

        with tempfile.TemporaryDirectory() as folder:

            pdf_path = os.path.join(folder, "certificate.pdf")

            certificate_data = {
                "student_name": "Integration Test Student",
                "student_id": "STU100",
                "course": "Computer Science",
                "institution": "CertiChain University",
                "issue_date": "2026-10-30",
                "certificate_id": "CERT-INT-001"
            }

            # Step 1: Generate PDF and QR code
            generate_certificate(certificate_data, pdf_path)

            qr_path = os.path.join(
                folder, "CERT-INT-001_qr.png"
            )

            self.assertTrue(os.path.exists(pdf_path))
            self.assertTrue(os.path.exists(qr_path))

            # Step 2: Generate SHA-256 hash
            original_hash = generate_hash(pdf_path)

            self.assertEqual(len(original_hash), 64)

            # Step 3: Verify original certificate
            self.assertTrue(verify_hash(pdf_path, original_hash))

            # Step 4: Create a tampered copy
            tampered_path = os.path.join(
                folder, "tampered_certificate.pdf"
            )

            shutil.copyfile(pdf_path, tampered_path)

            with open(tampered_path, "ab") as file:
                file.write(b"TAMPERED")

            # Step 5: Detect tampering
            self.assertFalse(
                verify_hash(tampered_path, original_hash)
            )


if __name__ == "__main__":
    unittest.main()
