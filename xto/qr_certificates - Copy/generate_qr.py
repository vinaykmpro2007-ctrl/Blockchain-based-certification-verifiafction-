
import qrcode
import os
from urllib.parse import urlencode


# Public certificate verification page
BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/") + "/user.html"


def generate_qr(certificate_id, output_path):
    """
    Generate a QR code for a certificate.

    Args:
        certificate_id: Unique certificate ID.
        output_path: Location to save the QR image.

    Returns:
        Verification URL.
    """

    if not certificate_id or not certificate_id.strip():
        raise ValueError("Certificate ID cannot be empty")

    # Create verification URL
    params = urlencode({
        "id": certificate_id.strip()
    })

    verification_url = f"{BASE_URL}?{params}"

    # Create QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4
    )

    qr.add_data(verification_url)
    qr.make(fit=True)

    # Generate QR image
    qr_image = qr.make_image(
        fill_color="black",
        back_color="white"
    )

    # Create output directory if necessary
    os.makedirs(
        os.path.dirname(output_path) or ".",
        exist_ok=True
    )

    # Save QR image
    qr_image.save(output_path)

    return verification_url


# Run independently for testing
if __name__ == "__main__":

    certificate_id = "CERT-DEMO-001"

    output_path = "qr_certificates/generated/demo_qr.png"

    url = generate_qr(
        certificate_id,
        output_path
    )

    print("QR code generated successfully!")
    print("Certificate ID:", certificate_id)
    print("Verification URL:", url)
    print("Saved at:", output_path)
    print("DEMO ONLY - NOT BLOCKCHAIN VERIFIED")
