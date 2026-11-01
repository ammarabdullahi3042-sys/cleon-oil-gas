from pathlib import Path
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, FloatObject
p = Path(r'C:\Users\ammar\FuelStationERP_V2\Version3\cover_revision\CLEON_Business_Plan_Dark.pdf')
writer = PdfWriter(clone_from=str(p))
old_fills = {
    (0.24, 0.32, 0.43): (27/255, 39/255, 46/255),
    (0.1, 0.14, 0.2): (38/255, 54/255, 63/255),
    (0.17, 0.235, 0.31): (45/255, 61/255, 69/255),
}
old_line, new_line = (0.46, 0.56, 0.67), (64/255, 81/255, 90/255)
fill_count = line_count = 0
for page in writer.pages[1:]:
    contents = page.get_contents()
    if contents is None:
        continue
    ops = contents.operations
    for i, (args, op) in enumerate(ops):
        if op not in (b'rg', b'RG'):
            continue
        vals = tuple(round(float(v), 6) for v in args)
        if op == b'rg' and vals in old_fills:
            ops[i] = (ArrayObject([FloatObject(v) for v in old_fills[vals]]), op)
            fill_count += 1
        elif op == b'RG' and vals == old_line:
            ops[i] = (ArrayObject([FloatObject(v) for v in new_line]), op)
            line_count += 1
    contents.operations = ops
    page.replace_contents(contents)
out = p.with_suffix('.pdf.new')
with out.open('wb') as stream:
    writer.write(stream)
out.replace(p)
print(f'Updated dark table fills ({fill_count} operations) and borders ({line_count} operations).')
