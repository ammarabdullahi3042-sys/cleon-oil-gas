from pathlib import Path
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor, white
from pypdf import PdfReader, PdfWriter
ROOT=Path(__file__).parent
pdfmetrics.registerFont(TTFont('Arial-Bold','C:/Windows/Fonts/arialbd.ttf'))
pdfmetrics.registerFont(TTFont('Arial-Italic','C:/Windows/Fonts/ariali.ttf'))
VISION='To set the standard for accurate, safe and transparent fuel retail across Nigeria.'
MOTTO='Flexible Energy. Reliable Service.'
ART=ROOT/'cover-art-clean-v3.png'
for flavor in ('Dark','White'):
    path=ROOT/f'CLEON_Business_Plan_{flavor}.pdf'
    source=PdfReader(str(path))
    page=source.pages[0]
    width,height=float(page.mediabox.width),float(page.mediabox.height)
    overlay=BytesIO()
    c=canvas.Canvas(overlay,pagesize=(width,height))
    c.drawImage(str(ART),0,0,width=width,height=height)
    x,y,w,h=35.5,724,541,34
    c.saveState(); c.setFillAlpha(.90); c.setFillColor(HexColor('#060E18')); c.setStrokeColor(HexColor('#E3C68C')); c.setLineWidth(.8); c.roundRect(x,y,w,h,7,fill=1,stroke=1); c.restoreState()
    c.setFillColor(HexColor('#EA1D25')); c.setFont('Arial-Bold',8.5); c.drawString(x+14,y+12.7,'VISION')
    tx=x+14+pdfmetrics.stringWidth('VISION','Arial-Bold',8.5)+10
    c.setFillColor(white); c.setFont('Arial-Italic',10.5); c.drawString(tx,y+12.7,VISION)
    c.setFillColor(white); c.setFont('Arial-Italic',16); c.drawCentredString(width/2,190,MOTTO)
    c.showPage(); c.save(); overlay.seek(0)
    cover=PdfReader(overlay).pages[0]
    out=PdfWriter(); out.add_page(cover)
    for rest in source.pages[1:]: out.add_page(rest)
    out.add_metadata(source.metadata or {})
    temp=path.with_suffix('.pdf.new')
    with temp.open('wb') as stream: out.write(stream)
    temp.replace(path)
print('Recomposed Dark and White covers from the supplied original artwork without resizing its aspect ratio.')

