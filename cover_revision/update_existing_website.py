from pathlib import Path
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase.pdfmetrics import stringWidth
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED, ZIP_STORED
from io import BytesIO
import re, shutil, tempfile

root = Path(__file__).parent
old = ("The application supports oversight alongside staff, physical checks and compliance; its current desktop data is stored locally. Website "
       "development will introduce CLEON online and provide an authorized investor area to track contributions and deployment milestones, "
       "view reports and receive timely updates. Enable live data and alerts only after secure hosting, access controls, audit history and "
       "backups are in place.")
new = ("CLEON's website gives investors a clear online view of their investment, including contributions, deployment milestones and available "
       "reports, with timely updates. Live balances and alerts should be supported by verified data, secure accounts and an audit trail.")
style = ParagraphStyle('website', fontName='Helvetica', fontSize=9, leading=11.5, textColor=HexColor('#111111'))
for flavor in ('Dark','White'):
    path=root/f'CLEON_Business_Plan_{flavor}_Final.pdf'
    reader=PdfReader(str(path))
    page=reader.pages[5]
    dark=flavor=='Dark'
    # Mask the previous website paragraph without disturbing the surrounding section or table.
    buf=BytesIO()
    c=canvas.Canvas(buf, pagesize=(float(page.mediabox.width),float(page.mediabox.height)))
    c.setFillColor(HexColor('#0F141C') if dark else HexColor('#FFFFFF'))
    c.rect(39,199,534,55,fill=1,stroke=0)
    style=ParagraphStyle('website', fontName='Helvetica', fontSize=9, leading=11.5, textColor=HexColor('#F1F4F7') if dark else HexColor('#111111'))
    p=Paragraph(new, style)
    _, h=p.wrap(534,100)
    p.drawOn(c,40,249-h)
    c.save()
    buf.seek(0)
    page.merge_page(PdfReader(buf).pages[0])
    tmp=path.with_suffix('.tmp.pdf')
    w=PdfWriter()
    for pg in reader.pages: w.add_page(pg)
    with tmp.open('wb') as f: w.write(f)
    tmp.replace(path)
    # Update the editable IDML story copy of the Technology paragraph.
    zpath=root/f'CLEON_Business_Plan_{flavor}.idml'
    temp=zpath.with_suffix('.idml.tmp')
    with ZipFile(zpath,'r') as zin, ZipFile(temp,'w') as zout:
        found=False
        for info in zin.infolist():
            data=zin.read(info.filename)
            if info.filename=='Stories/Story_u20c.xml':
                text=data.decode('utf-8')
                escaped_old=(old.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;'))
                escaped_new=(new.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;'))
                if escaped_old in text:
                    text=text.replace(escaped_old,escaped_new,1)
                elif escaped_new not in text:
                    raise ValueError(f'Website paragraph not found in {zpath.name}')
                data=text.encode('utf-8')
                found=True
            ni=ZipInfo(info.filename,info.date_time)
            ni.compress_type=ZIP_STORED if info.filename=='mimetype' else ZIP_DEFLATED
            ni.external_attr=info.external_attr
            ni.create_system=info.create_system
            zout.writestr(ni,data)
        if not found: raise ValueError('Technology story missing')
    temp.replace(zpath)
    print(flavor, 'updated')



