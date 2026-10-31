"""Build a certificate PDF in memory.

Uses only reportlab (including its built-in QR widget), so no extra
packages are needed. The QR code and the printed ID both point at the
public verification page, so the PDF can be checked by scanning it or by
uploading it to the verify page.
"""

from io import BytesIO
from urllib.parse import quote

from reportlab.graphics import renderPDF
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

NAVY = HexColor("#0b1f4d")
BLUE = HexColor("#1463ff")
INK = HexColor("#1b2742")
MUTED = HexColor("#5b6b8c")
RULE = HexColor("#c9d6f2")
RED = HexColor("#b3261e")


def fit_font_size(text: str, font: str, size: float, max_width: float, minimum: float = 11) -> float:
    """Shrink the font until the text fits, but never below `minimum`."""
    while size > minimum and stringWidth(text, font, size) > max_width:
        size -= 1
    return size


def wrap(text: str, font: str, size: float, max_width: float) -> list[str]:
    """Break text into lines that fit max_width. Very long words are split."""
    lines, current = [], ""

    for word in text.split():
        # A single word wider than the line is cut into pieces.
        while stringWidth(word, font, size) > max_width:
            cut = len(word)
            while cut > 1 and stringWidth(word[:cut], font, size) > max_width:
                cut -= 1
            if current:
                lines.append(current)
                current = ""
            lines.append(word[:cut])
            word = word[cut:]

        trial = f"{current} {word}".strip()
        if stringWidth(trial, font, size) <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word

    if current:
        lines.append(current)

    return lines or [""]


def verification_url(base_url: str, certificate_id: str) -> str:
    return f"{base_url.rstrip('/')}/user.html?id={quote(certificate_id)}"


def build_certificate_pdf(cert: dict, base_url: str) -> bytes:
    """cert: the dict from certificate_public()/certificate_admin()."""
    width, height = landscape(A4)
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(width, height))

    certificate_id = cert["certificate_id"]
    revoked = cert["status"] == "REVOKED"
    pdf.setTitle(f"Certificate {certificate_id}")
    pdf.setAuthor(cert["institution"])
    pdf.setSubject("CertiChain certificate")

    # Frame
    pdf.setStrokeColor(NAVY)
    pdf.setLineWidth(3)
    pdf.rect(24, 24, width - 48, height - 48)
    pdf.setStrokeColor(BLUE)
    pdf.setLineWidth(0.8)
    pdf.rect(32, 32, width - 64, height - 64)

    centre = width / 2
    usable = width - 160

    # Institution
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 12)
    pdf.drawCentredString(centre, height - 82, "THIS CERTIFICATE IS ISSUED BY")

    institution = cert["institution"]
    size = fit_font_size(institution, "Helvetica-Bold", 26, usable)
    pdf.setFillColor(NAVY)
    pdf.setFont("Helvetica-Bold", size)
    y = height - 118
    for line in wrap(institution, "Helvetica-Bold", size, usable)[:2]:
        pdf.drawCentredString(centre, y, line)
        y -= size + 4

    # Title
    y -= 14
    pdf.setFillColor(BLUE)
    pdf.setFont("Helvetica-Bold", 34)
    pdf.drawCentredString(centre, y, "Certificate of Completion")
    pdf.setStrokeColor(RULE)
    pdf.setLineWidth(1)
    pdf.line(centre - 120, y - 12, centre + 120, y - 12)

    # Recipient
    y -= 52
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 13)
    pdf.drawCentredString(centre, y, "This is to certify that")

    name = cert["student_name"]
    size = fit_font_size(name, "Helvetica-Bold", 30, usable)
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", size)
    y -= 38
    for line in wrap(name, "Helvetica-Bold", size, usable)[:2]:
        pdf.drawCentredString(centre, y, line)
        y -= size + 4

    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 13)
    y -= 4
    pdf.drawCentredString(centre, y, f"(Student ID: {cert['student_id']})  has successfully completed")

    course = cert["course"]
    size = fit_font_size(course, "Helvetica-Bold", 20, usable, minimum=13)
    pdf.setFillColor(NAVY)
    pdf.setFont("Helvetica-Bold", size)
    y -= 34
    for line in wrap(course, "Helvetica-Bold", size, usable)[:2]:
        pdf.drawCentredString(centre, y, line)
        y -= size + 4

    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 12)
    pdf.drawCentredString(centre, max(y - 6, 150), f"Issued on {cert['issue_date']}")

    # Footer: ID on the left, QR on the right
    pdf.setStrokeColor(RULE)
    pdf.line(60, 128, width - 60, 128)

    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 10)
    pdf.drawString(60, 106, "Certificate ID")
    pdf.setFillColor(INK)
    pdf.setFont("Courier-Bold", 14)
    pdf.drawString(60, 88, certificate_id)

    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 9)
    pdf.drawString(60, 64, "Verify this certificate by scanning the QR code, or enter the ID at")
    pdf.drawString(60, 52, verification_url(base_url, certificate_id).split("?")[0])

    qr_size = 84
    widget = QrCodeWidget(verification_url(base_url, certificate_id))
    x1, y1, x2, y2 = widget.getBounds()
    drawing = Drawing(
        qr_size, qr_size,
        transform=[qr_size / (x2 - x1), 0, 0, qr_size / (y2 - y1), 0, 0],
    )
    drawing.add(widget)
    renderPDF.draw(drawing, pdf, width - 60 - qr_size, 40)

    # Revoked: a diagonal stamp that cannot be missed.
    if revoked:
        pdf.saveState()
        pdf.translate(centre, height / 2)
        pdf.rotate(24)
        pdf.setFillColor(RED)
        pdf.setStrokeColor(RED)
        pdf.setFillAlpha(0.16)
        pdf.setFont("Helvetica-Bold", 110)
        pdf.drawCentredString(0, -30, "REVOKED")
        pdf.setFillAlpha(1)
        pdf.setLineWidth(5)
        pdf.setStrokeAlpha(0.35)
        pdf.roundRect(-250, -75, 500, 120, 14)
        pdf.restoreState()

        pdf.setFillColor(RED)
        pdf.setFont("Helvetica-Bold", 11)
        when = (cert.get("revoked_at") or "")[:10]
        pdf.drawCentredString(
            centre, 140,
            "This certificate has been revoked" + (f" on {when}" if when else "") + " and is no longer valid.",
        )

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()
