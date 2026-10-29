# scripts/test_ocr_pages.py - OCR a few pages with the same OCR code the upload uses, and print the text.
# Run from the project folder:
#   python scripts\test_ocr_pages.py "D:\nexus-rag\data\raw2\279.pdf" eng+hin+san
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

pdf_path = Path(sys.argv[1])
langs = sys.argv[2] if len(sys.argv) > 2 else "eng+hin+san"
pages = [int(p) for p in (sys.argv[3].split(",") if len(sys.argv) > 3 else "14,15,16".split(","))]

# Settings for this test only (set before the app reads its config)
os.environ["OCR_LANGS"] = langs
os.environ["OCR_DPI"] = "300"

from app import ocr  # noqa: E402

print("languages:", langs, "| dpi: 300 | pages:", pages)
texts = ocr.ocr_pages(pdf_path, pages)
for p in pages:
    print(f"\n----- PDF page {p} -----")
    print(texts.get(p, "(no text)")[:1200])
