from xml.etree import ElementTree as ET
import zipfile
for f in ['Dark','White']:
 z=zipfile.ZipFile(f'cover_revision/CLEON_Business_Plan_{f}.idml'); x=z.read('Stories/Story_u20c.xml'); root=ET.fromstring(x); s=root.find('Story')
 for p in list(s.findall('ParagraphStyleRange'))[:13]: print(f,''.join(i.text or '' for i in p.findall('.//Content')))
