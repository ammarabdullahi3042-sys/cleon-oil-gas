from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED, ZIP_STORED
import re
ROOT = Path(__file__).parent
PI = '<?aid style="50" type="document" readerVersion="6.0" featureSet="257" product="18.1(51)" ?>'
DARK = {
    'header': '27 39 46',
    'base': '38 54 63',
    'stripe': '45 61 69',
    'line': '64 81 90',
}
for flavor in ('Dark', 'White'):
    src = ROOT / f'CLEON_Business_Plan_{flavor}.idml'
    tmp = src.with_suffix('.idml.new')
    with ZipFile(src, 'r') as zin, ZipFile(tmp, 'w') as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename == 'designmap.xml':
                text = data.decode('utf-8')
                if '<?aid style=' not in text:
                    end = text.find('?>')
                    if end < 0:
                        raise ValueError('designmap.xml has no XML declaration')
                    text = text[:end + 2] + '\n' + PI + '\n' + text[end + 2:]
                data = text.encode('utf-8')
            elif flavor == 'Dark' and info.filename == 'Resources/Graphic.xml':
                text = data.decode('utf-8')
                for key, value in DARK.items():
                    self_id = f'Color/CLEON_Table_{key}_Dark'
                    pattern = re.compile(r'(<Color Self="' + re.escape(self_id) + r'"[^>]*?ColorValue=")[^"]+("[^>]*?/>)')
                    text, count = pattern.subn(lambda m: m.group(1) + value + m.group(2), text, count=1)
                    if count != 1:
                        raise ValueError(f'Expected one swatch for {self_id}; found {count}')
                data = text.encode('utf-8')
            new_info = ZipInfo(info.filename, info.date_time)
            new_info.compress_type = ZIP_STORED if info.filename == 'mimetype' else ZIP_DEFLATED
            new_info.external_attr = info.external_attr
            new_info.create_system = info.create_system
            zout.writestr(new_info, data)
    tmp.replace(src)
    print(f'Repaired {flavor} IDML metadata' + (' and slate table swatches' if flavor == 'Dark' else ''))
