
import unittest
import tempfile
import os

from qr_certificates.hash_certificate import generate_hash, verify_hash


class TestCertificateHash(unittest.TestCase):

    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(delete=False)
        self.temp_file.write(b"Sample Certificate")
        self.temp_file.close()

        self.original_hash = generate_hash(self.temp_file.name)

    def test_hash_generation(self):
        self.assertEqual(len(self.original_hash), 64)

    def test_same_file_verification(self):
        self.assertTrue(
            verify_hash(self.temp_file.name, self.original_hash)
        )

    def test_modified_file_detection(self):
        with open(self.temp_file.name, "ab") as file:
            file.write(b" Modified")

        self.assertFalse(
            verify_hash(self.temp_file.name, self.original_hash)
        )

    def tearDown(self):
        if os.path.exists(self.temp_file.name):
            os.remove(self.temp_file.name)


if __name__ == "__main__":
    unittest.main()

