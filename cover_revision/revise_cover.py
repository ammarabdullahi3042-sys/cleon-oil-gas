from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from xml.etree import ElementTree as ET
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor, white
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pypdf import PdfReader, PdfWriter

ROOT=Path('cover_revision')
FONT=Path(r'C:\Windows\Fonts')
pdfmetrics.registerFont(TTFont('Arial','C:/Windows/Fonts/arial.ttf'))
pdfmetrics.registerFont(TTFont('Arial-Bold','C:/Windows/Fonts/arialbd.ttf'))
pdfmetrics.registerFont(TTFont('Arial-Italic','C:/Windows/Fonts/ariali.ttf'))

VISION='To set the standard for accurate, safe and transparent fuel retail across Nigeria.'
OLD_MOTTO='Flexible by Design'
MOTTO='Flexible Energy. Reliable Service.'
NAVY=HexColor('#060E18')
GOLD=HexColor('#E3C68C')
ORANGE=HexColor('#EA1D25')
WHITE=white

# Build a cover overlay: one matching-height vision frame, with the motto directly beneath CLEON.
def overlay_pdf(source, target, bulb_path):
    reader=PdfReader(str(source))
    page=reader.pages[0]
    w=float(page.mediabox.width); h=float(page.mediabox.height)
    stream=BytesIO(); c=canvas.Canvas(stream,pagesize=(w,h))
    # Paint over the existing vision/motto cards and copy so they cannot ghost through.
    x=35.5; cardw=541.0; cardh=70.5
    top_y=650.0
    old_top=(35.5,649.0,541.0,119.0)
    old_bottom=(35.5,33.0,541.0,72.5)
    c.setFillColor(NAVY); c.setStrokeColor(NAVY)
    for rx,ry,rw,rh in (old_top,old_bottom): c.rect(rx,ry,rw,rh,fill=1,stroke=0)
    # Put back the transparent brand bulb where the previous lower card crossed its left edge.
    c.drawImage(str(bulb_path),570.0,34.5,width=34.0,height=54.0,preserveAspectRatio=True,anchor='c',mask='auto')
    # Single vision panel.
    c.setFillColor(NAVY); c.setStrokeColor(GOLD); c.setLineWidth(1.05)
    c.roundRect(x,top_y,cardw,cardh,8.0,fill=1,stroke=1)
    c.setFillColor(ORANGE); c.setFont('Arial-Bold',8.5)
    c.drawString(x+16,top_y+cardh-20,'VISION')
    c.setFillColor(WHITE); c.setFont('Arial-Italic',12.5)
    c.drawString(x+16,top_y+25.0,VISION)
    # Brand motto/tagline directly under the CLEON wordmark.
    c.setFillColor(WHITE); c.setFont('Arial-Italic',16)
    c.drawCentredString(w/2,190.0,MOTTO)
    c.save(); stream.seek(0)
    overlay=PdfReader(stream).pages[0]
    page.merge_page(overlay)
    writer=PdfWriter(); writer.append(reader)
    writer.add_metadata({'/Title':'CLEON Oil and Gas Business Plan'})
    with open(target,'wb') as f: writer.write(f)

for flavor in ('Dark','White'):
    overlay_pdf(ROOT/f'CLEON_Business_Plan_{flavor}.pdf',ROOT/f'CLEON_Business_Plan_{flavor}.pdf.new',ROOT/'cleon_bulb_small.png')
    (ROOT/f'CLEON_Business_Plan_{flavor}.pdf.new').replace(ROOT/f'CLEON_Business_Plan_{flavor}.pdf')

# Update the cover copy and styling in each editable IDML story.
ns={'pkg':'http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging'}
for flavor in ('Dark','White'):
    path=ROOT/f'CLEON_Business_Plan_{flavor}.idml'
    temp=path.with_suffix('.idml.new')
    with ZipFile(path,'r') as zin, ZipFile(temp,'w',ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data=zin.read(item.filename)
            if item.filename=='Stories/Story_u20c.xml':
                root=ET.fromstring(data)
                story=root.find('Story')
                paras=list(story.findall('ParagraphStyleRange'))
                def ptext(p): return ''.join(e.text or '' for e in p.findall('.//Content'))
                # Turn vision into a single italic line.
                for p in paras:
                    if ptext(p)==VISION:
                        cr=p.find('CharacterStyleRange')
                        cr.set('FontStyle','Italic'); cr.set('PointSize','12.5')
                        p.set('SpaceBefore','2'); p.set('SpaceAfter','3')
                        break
                # Remove the MOTTO label and relocate its wording immediately after the cover wordmark.
                motto_label=next((p for p in paras if ptext(p)=='MOTTO'),None)
                motto_p=next((p for p in paras if ptext(p) in (OLD_MOTTO,MOTTO)),None)
                if motto_label is not None: story.remove(motto_label)
                if motto_p is not None: story.remove(motto_p)
                if motto_p is None:
                    raise RuntimeError(f'Motto paragraph missing in {path.name}')
                cr=motto_p.find('CharacterStyleRange')
                cr.set('FontStyle','Italic'); cr.set('PointSize','12.5'); cr.set('FillColor','Color/Paper')
                motto_p.set('SpaceBefore','1'); motto_p.set('SpaceAfter','7'); motto_p.set('Justification','CenterAlign')
                cleon=next((p for p in story.findall('ParagraphStyleRange') if ptext(p)=='CLEON'),None)
                if cleon is None: raise RuntimeError(f'Cover CLEON paragraph missing in {path.name}')
                story.insert(list(story).index(cleon)+1,motto_p)
                data=ET.tostring(root,encoding='UTF-8',xml_declaration=True)
            zout.writestr(item,data)
    temp.replace(path)
print('Updated two PDFs and two IDMLs.')



