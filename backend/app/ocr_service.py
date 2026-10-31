
import io
import os

import pytesseract
from PIL import Image
from pdf2image import convert_from_bytes


# Tesseract OCR installation path
pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)

# Poppler installation path
POPPLER_PATH = (
    r"C:\Users\kiran\Downloads\Release-26.09.0-0"
    r"\poppler-26.09.0\Library\bin"
)

MAX_FILE_SIZE = 10 * 1024 * 1024


def extract_text(file_bytes: bytes, filename: str) -> str:
    """Extract text from an uploaded image or PDF."""

    extension = os.path.splitext(filename)[1].lower()

    if extension not in [".png", ".jpg", ".jpeg", ".pdf"]:
        raise ValueError(
            "Only PNG, JPG, JPEG and PDF files are supported."
        )

    if not file_bytes:
        raise ValueError("The uploaded file is empty.")

    if len(file_bytes) > MAX_FILE_SIZE:
        raise ValueError("File size must be below 10 MB.")

    if extension == ".pdf":
        if not file_bytes.startswith(b"%PDF"):
            raise ValueError("Invalid PDF file.")

        images = convert_from_bytes(
            file_bytes,
            dpi=200,
            first_page=1,
            last_page=5,
            poppler_path=POPPLER_PATH,
        )

    else:
        image = Image.open(io.BytesIO(file_bytes))
        image.verify()

        image = Image.open(
            io.BytesIO(file_bytes)
        ).convert("RGB")

        images = [image]

    extracted_text = []

    for image in images:
        text = pytesseract.image_to_string(
            image,
            lang="eng"
        )
        extracted_text.append(text)

    return "\n".join(extracted_text).strip()
