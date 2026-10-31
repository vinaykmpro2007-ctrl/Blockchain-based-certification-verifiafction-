
import os
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.pdfgen import canvas

from qr_certificates.generate_qr import generate_qr


def generate_certificate(data, output_path):

    # Create output directory if needed
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    certificate_id = data["certificate_id"]

    # Generate QR code
    qr_path = os.path.join(
        os.path.dirname(output_path) or ".",
        f"{certificate_id}_qr.png"
    )

    verification_url = generate_qr(certificate_id, qr_path)

    # Set certificate page size
    width, height = landscape(A4)

    pdf = canvas.Canvas(output_path, pagesize=(width, height))

    # Background
    pdf.setFillColor(colors.white)
    pdf.rect(0, 0, width, height, fill=1, stroke=0)

    # Outer border
    pdf.setStrokeColor(colors.HexColor("#173B67"))
    pdf.setLineWidth(5)
    pdf.rect(25, 25, width - 50, height - 50)

    # Inner border
    pdf.setStrokeColor(colors.HexColor("#C9A227"))
    pdf.setLineWidth(2)
    pdf.rect(35, 35, width - 70, height - 70)

    # Heading
    pdf.setFillColor(colors.HexColor("#173B67"))
    pdf.setFont("Helvetica-Bold", 30)
    pdf.drawCentredString(
        width / 2, height - 110,
        "CERTIFICATE OF ACHIEVEMENT"
    )

    pdf.setFont("Helvetica", 15)
    pdf.setFillColor(colors.black)
    pdf.drawCentredString(
        width / 2, height - 150,
        "This certificate is proudly presented to"
    )

    # Student name
    pdf.setFont("Helvetica-Bold", 27)
    pdf.setFillColor(colors.HexColor("#9B7417"))
    pdf.drawCentredString(
        width / 2, height - 205,
        data["student_name"]
    )

    # Course details
    pdf.setFillColor(colors.black)
    pdf.setFont("Helvetica", 15)
    pdf.drawCentredString(
        width / 2, height - 245,
        f"For successfully completing {data['course']}"
    )

    pdf.drawCentredString(
        width / 2, height - 275,
        f"Institution: {data['institution']}"
    )

    pdf.drawCentredString(
        width / 2, height - 305,
        f"Student ID: {data['student_id']}"
    )

    pdf.drawCentredString(
        width / 2, height - 335,
        f"Issue Date: {data['issue_date']}"
    )

    # Certificate ID
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(65, 65, f"Certificate ID: {certificate_id}")

    # QR code
    pdf.drawImage(
        qr_path,
        width - 145,
        55,
        width=85,
        height=85
    )

    pdf.setFont("Helvetica", 9)
    pdf.drawString(
        width - 155, 42,
        "Scan to verify"
    )

    # Finish PDF
    pdf.save()

    print("Certificate PDF generated successfully!")
    print("Saved at:", output_path)
    print("Verification URL:", verification_url)

    return output_path


if __name__ == "__main__":

    sample_data = {
        "student_name": "Demo Student",
        "student_id": "STU001",
        "course": "Bachelor of Computer Applications",
        "institution": "Demo University",
        "issue_date": "2026-10-30",
        "certificate_id": "CERT-DEMO-001"
    }

    generate_certificate(
        sample_data,
        "qr_certificates/generated/sample_certificate.pdf"
    )
