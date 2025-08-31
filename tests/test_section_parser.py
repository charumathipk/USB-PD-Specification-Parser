import tempfile, os
from usb_pd_parser.parsers.section_parser import SectionParser
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter


def create_dummy_pdf(path):
    c = canvas.Canvas(path, pagesize=letter)
    # Add heading-like text to simulate real PDF sections
    c.drawString(100, 750, "1. Introduction")
    c.drawString(100, 730, "This is a dummy section for testing.")
    c.save()


def test_parse_minimal():
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
    tmp.close()
    create_dummy_pdf(tmp.name)
    sp = SectionParser(tmp.name)
    res = sp.parse()
    assert isinstance(res, list)
    assert len(res) >= 1   # should pass now
    os.remove(tmp.name)
