from pathlib import Path
from io import BytesIO
from PIL import Image
import numpy as np
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor, white
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pypdf import PdfReader, PdfWriter
ROOT=Path('cover_revision')
pdfmetrics.registerFont(TTFont('Arial-Bold','C:/Windows/Fonts/arialbd.ttf'))
pdfmetrics.registerFont(TTFont('Arial-Italic','C:/Windows/Fonts/ariali.ttf'))
NAVY=HexColor('#060E18'); GOLD=HexColor('#E3C68C'); ORANGE=HexColor('#EA1D25'); WHITE=white
VISION='To set the standard for accurate, safe and transparent fuel retail across Nigeria.'
TAG='Flexible Energy. Reliable Service.'
a=np.asarray(Image.open(ROOT/'extracted0.png').convert('RGB')).astype(np.float32)
h,w=a.shape[:2]
y=np.arange(h,dtype=np.float32)[:,None]
# Softly suppress the old mission/model copy while retaining the photographic artwork.
top=np.where(y<=260,255,np.clip((340-y)/(340-260),0,1)*255)
top_shade=np.empty_like(a); top_shade[:]=[6,14,24]
a=a*(1-top[:,:,None]/255)+top_shade*(top[:,:,None]/255)
bottom=np.clip((y-1325)/(1410-1325),0,1); bottom=(bottom*bottom*(3-2*bottom))*255
bottom_shade=np.empty_like(a); bottom_shade[:]=[6,14,24]
a=a*(1-bottom[:,:,None]/255)+bottom_shade*(bottom[:,:,None]/255)
Image.fromarray(np.uint8(np.clip(a,0,255))).save(ROOT/'cover-base-final.png')
for kind in ('Dark','White'):
 src=ROOT/f'CLEON_Business_Plan_{kind}.pdf'; reader=PdfReader(str(src)); old=reader.pages[0]
 width=float(old.mediabox.width); height=float(old.mediabox.height)
 data=BytesIO(); c=canvas.Canvas(data,pagesize=(width,height))
 c.drawImage(str(ROOT/'cover-base-final.png'),0,0,width=width,height=height)
 c.drawImage(str(ROOT/'extracted1.png'),570.0,16.28571,width=34.0,height=53.42857)
 # Slim one-line vision panel, inset from the top so more cover art remains visible.
 c.setFillColor(NAVY); c.setStrokeColor(GOLD); c.setLineWidth(0.8); c.roundRect(36,724,540,34,7,fill=1,stroke=1)
 c.setFillColor(ORANGE); c.setFont('Arial-Bold',8.5); c.drawString(50,737,'VISION')
 vx=50+pdfmetrics.stringWidth('VISION','Arial-Bold',8.5)+10
 c.setFillColor(WHITE); c.setFont('Arial-Italic',10.5); c.drawString(vx,736,VISION)
 c.setFont('Arial-Italic',16); c.drawCentredString(width/2,190,TAG)
 c.save(); data.seek(0); cover=PdfReader(data).pages[0]
 writer=PdfWriter(); writer.add_page(cover)
 for rest in reader.pages[1:]: writer.add_page(rest)
 writer.add_metadata(reader.metadata or {})
 out=src.with_suffix('.pdf.new')
 with open(out,'wb') as f: writer.write(f)
 out.replace(src)
print('Recomposed both covers.')
print('Vision string width',round(pdfmetrics.stringWidth(VISION,'Arial-Italic',10.5),2),'pt')




