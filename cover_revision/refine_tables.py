from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from xml.etree import ElementTree as ET
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, FloatObject

ROOT = Path(__file__).parent
NS = 'http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging'
ET.register_namespace('', NS)

PDF_FILLS = {
    'White': {
        (0.905882, 0.929412, 0.94902): (0.82, 0.87, 0.91),       # header
        (0.952941, 0.964706, 0.972549): (0.89, 0.92, 0.95),      # pale stripe
    }
}
PDF_STROKES = {
    'Dark': ((0.4, 0.49, 0.6), (0.46, 0.56, 0.67)),
    'White': ((0.803922, 0.839216, 0.862745), (0.54, 0.62, 0.70)),
}

def update_pdf(flavor):
    path = ROOT / f'CLEON_Business_Plan_{flavor}.pdf'
    writer = PdfWriter(clone_from=str(path))
    for page in writer.pages[1:]:
        contents = page.get_contents()
        if contents is None:
            continue
        ops = contents.operations
        if flavor in PDF_FILLS:
            replacements = PDF_FILLS[flavor]
            for idx, (args, op) in enumerate(ops[:-3]):
                if (op == b'rg' and tuple(args) in replacements
                        and ops[idx + 1][1] == b'n'
                        and ops[idx + 2][1] == b're'
                        and ops[idx + 3][1] in (b'f', b'f*')):
                    ops[idx] = (ArrayObject([FloatObject(v) for v in replacements[tuple(args)]]), op)
        old, new = PDF_STROKES[flavor]
        for idx, (args, op) in enumerate(ops):
            if op == b'RG' and tuple(args) == old:
                ops[idx] = (ArrayObject([FloatObject(v) for v in new]), op)
        contents.operations = ops
        page.replace_contents(contents)
    temp = path.with_suffix('.pdf.new')
    with temp.open('wb') as out:
        writer.write(out)
    temp.replace(path)

def add_swatch(root, name, rgb):
    self_name = f'Color/{name}'
    if any(el.get('Self') == self_name for el in root):
        return self_name
    el = ET.SubElement(root, f'{{{NS}}}Color')
    values = {
        'Self': self_name, 'Model': 'Process', 'Space': 'RGB',
        'ColorValue': ' '.join(map(str, rgb)), 'ColorOverride': 'Normal',
        'ConvertToHsb': 'false', 'AlternateSpace': 'NoAlternateColor',
        'AlternateColorValue': '', 'Name': name, 'ColorEditable': 'true',
        'ColorRemovable': 'true', 'Visible': 'true', 'SwatchCreatorID': '7937',
        'SwatchColorGroupReference': 'u12ColorGroupSwatch12',
    }
    el.attrib.update(values)
    return self_name

def update_idml(flavor):
    path = ROOT / f'CLEON_Business_Plan_{flavor}.idml'
    temp = path.with_suffix('.idml.new')
    if flavor == 'Dark':
        colors = {
            'header': (61, 82, 110), 'base': (26, 36, 51),
            'stripe': (43, 60, 79), 'line': (118, 140, 164),
        }
    else:
        colors = {
            'header': (209, 220, 230), 'base': (255, 255, 255),
            'stripe': (227, 234, 240), 'line': (137, 157, 177),
        }
    swatches = {key: f'CLEON_Table_{key}_{flavor}' for key in colors}
    with ZipFile(path, 'r') as zin, ZipFile(temp, 'w', ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename == 'Resources/Graphic.xml':
                root = ET.fromstring(data)
                for key, rgb in colors.items():
                    add_swatch(root, swatches[key], rgb)
                data = ET.tostring(root, encoding='UTF-8', xml_declaration=True)
            elif info.filename == 'Resources/Styles.xml':
                root = ET.fromstring(data)
                for table_style in root.iter(f'{{{NS}}}TableStyle'):
                    for key, value in list(table_style.attrib.items()):
                        if key.endswith('BorderStrokeColor') or key in (
                            'StartRowStrokeColor', 'EndRowStrokeColor',
                            'StartColumnStrokeColor', 'EndColumnStrokeColor',
                        ):
                            table_style.set(key, f'Color/{swatches["line"]}')
                        if key.endswith('BorderStrokeWeight'):
                            table_style.set(key, '0.6')
                data = ET.tostring(root, encoding='UTF-8', xml_declaration=True)
            elif info.filename == 'Stories/Story_u20c.xml':
                root = ET.fromstring(data)
                for table in root.iter(f'{{{NS}}}Table'):
                    for row_index, row in enumerate(table.findall(f'{{{NS}}}Row')):
                        role = 'header' if row_index == 0 else ('stripe' if row_index % 2 == 0 else 'base')
                        fill = f'Color/{swatches[role]}'
                        for cell in row.findall(f'{{{NS}}}Cell'):
                            cell.set('FillColor', fill)
                data = ET.tostring(root, encoding='UTF-8', xml_declaration=True)
            zout.writestr(info, data)
    temp.replace(path)

for flavor in ('Dark', 'White'):
    update_pdf(flavor)
    update_idml(flavor)
print('Updated readable table fills and borders in both PDFs and IDMLs.')
