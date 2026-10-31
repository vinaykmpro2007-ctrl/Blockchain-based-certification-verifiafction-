
import unittest
import tempfile
import os

from qr_certificates.generate_qr import generate_qr
from qr_certificates.generate_pdf import generate_certificate


class TestQRAndPDF(unittest.TestCase):

    def test_qr_generation(self):
        with tempfile.TemporaryDirectory() as folder:
            qr_path = os.path.join(folder, "test_qr.png")

            url = generate_qr("CERT-TEST-001", qr_path)

            self.assertTrue(os.path.exists(qr_path))
            self.assertGreater(os.path.getsize(qr_path), 0)
            self.assertIn("CERT-TEST-001", url)

    def test_pdf_generation(self):
        with tempfile.TemporaryDirectory() as folder:
            pdf_path = os.path.join(folder, "test_certificate.pdf")

            data = {
                "student_name": "Test Student",
                "student_id": "STU002",
                "course": "Computer Science",
                "institution": "Test University",
                "issue_date": "2026-10-30",
                "certificate_id": "CERT-TEST-002"
            }

            generate_certificate(data, pdf_path)

            self.assertTrue(os.path.exists(pdf_path))

            with open(pdf_path, "rb") as file:
                self.assertEqual(file.read(5), b"%PDF-")

    def test_pdf_generation_creates_qr(self):
        with tempfile.TemporaryDirectory() as folder:
            pdf_path = os.path.join(folder, "test_certificate.pdf")

            data = {
                "student_name": "Test Student",
                "student_id": "STU003",
                "course": "Information Technology",
                "institution": "Test University",
                "issue_date": "2026-10-30",
                "certificate_id": "CERT-TEST-003"
            }

            generate_certificate(data, pdf_path)

            qr_path = os.path.join(folder, "CERT-TEST-003_qr.png")
            self.assertTrue(os.path.exists(qr_path))


if __name__ == "__main__":
    unittest.main()

