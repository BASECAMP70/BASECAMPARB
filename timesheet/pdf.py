from io import BytesIO
from pathlib import Path

from flask import render_template
from xhtml2pdf import pisa
from pypdf import PdfWriter, PdfReader


def generate_invoice_pdf(app, invoice, settings, expense_pdf_dir=None):
    """Render invoice HTML to PDF and optionally append expense receipt PDFs."""
    with app.app_context():
        html_content = render_template("invoice_pdf.html", invoice=invoice, settings=settings)
    buf = BytesIO()
    result = pisa.CreatePDF(html_content, dest=buf)
    if result.err:
        raise RuntimeError(f"PDF rendering failed with {result.err} error(s)")
    invoice_bytes = buf.getvalue()

    receipt_paths = []
    if expense_pdf_dir is not None:
        for item in invoice.get("line_items", []):
            if item.get("type") == "expense" and item.get("pdf_filename"):
                path = Path(expense_pdf_dir) / item["pdf_filename"]
                if path.exists():
                    receipt_paths.append(path)

    if not receipt_paths:
        return invoice_bytes

    writer = PdfWriter()
    for reader in [PdfReader(BytesIO(invoice_bytes))] + [PdfReader(str(p)) for p in receipt_paths]:
        for page in reader.pages:
            writer.add_page(page)
    out = BytesIO()
    writer.write(out)
    return out.getvalue()
