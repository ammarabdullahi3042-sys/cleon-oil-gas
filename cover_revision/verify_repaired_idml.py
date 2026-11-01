from zipfile import ZipFile
from pathlib import Path
import xml.etree.ElementTree as ET
for p in Path(r'C:\Users\ammar\FuelStationERP_V2\Version3\cover_revision').glob('CLEON_Business_Plan_*.idml'):
    with ZipFile(p) as z:
        assert z.namelist()[0] == 'mimetype'
        assert z.getinfo('mimetype').compress_type == 0
        bad=[]
        for n in z.namelist():
            if n.endswith('.xml'):
                try: ET.fromstring(z.read(n))
                except Exception as e: bad.append((n,str(e)))
        dm=z.read('designmap.xml').decode('utf-8')
        print(p.name, 'entries',len(z.namelist()), 'bad_xml',bad, 'aid_pi', '<?aid style=' in dm)
        if 'Dark' in p.name:
            root=ET.fromstring(z.read('Resources/Graphic.xml'))
            print({e.attrib.get('Self'):e.attrib.get('ColorValue') for e in root if e.attrib.get('Self','').startswith('Color/CLEON_Table_')})
