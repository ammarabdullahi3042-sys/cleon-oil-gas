from pathlib import Path
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor, white
from pypdf import PdfReader, PdfWriter

ROOT = Path(__file__).parent
pdfmetrics.registerFont(TTFont('Arial-Bold', 'C:/Windows/Fonts/arialbd.ttf'))
pdfmetrics.registerFont(TTFont('Arial-Italic', 'C:/Windows/Fonts/ariali.ttf'))
VISION = 'To set the standard for accurate, safe and transparent fuel retail across Nigeria.'
TAGLINE = 'Flexible Energy. Reliable Service.'

for flavor in ('Dark', 'White'):
    path = ROOT / f'CLEON_Business_Plan_{flavor}.pdf'
    source = PdfReader(str(path))
    width, height = float(source.pages[0].mediabox.width), float(source.pages[0].mediabox.height)
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=(width, height))
    c.drawImage(str(ROOT / 'cover-art-restored-preview.png'), 0, 0, width, height, mask='auto')
    c.drawImage(str(ROOT / 'cleon_bulb_small.png'), 570, 16.2857, width=34, height=53.4286, preserveAspectRatio=True, anchor='c', mask='auto')

    # A single, slim Vision line at the top; no panel is added at the foot of the page.
    x, y, w, h = 35.5, 724, 541, 34
    c.saveState()
    c.setFillAlpha(0.90)
    c.setFillColor(HexColor('#060E18'))
    c.setStrokeAlpha(1)
    c.setStrokeColor(HexColor('#E3C68C'))
    c.setLineWidth(0.8)
    c.roundRect(x, y, w, h, 7, fill=1, stroke=1)
    c.restoreState()
    c.setFillColor(HexColor('#EA1D25'))
    c.setFont('Arial-Bold', 8.5)
    c.drawString(x + 14, y + 12.7, 'VISION')
    vision_x = x + 14 + pdfmetrics.stringWidth('VISION', 'Arial-Bold', 8.5) + 10
    c.setFillColor(white)
    c.setFont('Arial-Italic', 10.5)
    c.drawString(vision_x, y + 12.7, VISION)

    # Preserve DISCOVER CLEON from the original artwork, and set only this italic tagline beneath it.
    c.setFillColor(white)
    c.setFont('Arial-Italic', 16)
    c.drawCentredString(width / 2, 190, TAGLINE)
    c.showPage(); c.save(); buffer.seek(0)
    cover = PdfReader(buffer).pages[0]
    writer = PdfWriter()
    writer.add_page(cover)
    for page in source.pages[1:]:
        writer.add_page(page)
    writer.add_metadata(source.metadata or {})
    temp = path.with_suffix('.pdf.new')
    with temp.open('wb') as output:
        writer.write(output)
    temp.replace(path)
print('Rebuilt both cover pages with the untouched source artwork and the requested copy.')
