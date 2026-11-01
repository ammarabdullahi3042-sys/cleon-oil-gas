from pypdf import PdfReader
from pathlib import Path
for x in ['Dark','White']:
 p=PdfReader(f'cover_revision/CLEON_Business_Plan_{x}.pdf')
 print(x,len(p.pages),p.pages[0].mediabox, 'vision text found', 'accurate, safe and transparent fuel retail across Nigeria.' in p.pages[0].extract_text(), 'tagline found', 'Flexible by Design' in p.pages[0].extract_text())
import zipfile,re
for x in ['Dark','White']:
 z=zipfile.ZipFile(f'cover_revision/CLEON_Business_Plan_{x}.idml')
 s=z.read('Stories/Story_u20c.xml').decode('utf8')
 print('IDML',x,'vision', 'FontStyle="Italic" PointSize="12.5"' in s,'motto marker', '<Content>MOTTO</Content>' in s, 'Flexible count',s.count('<Content>Flexible by Design</Content>'))
