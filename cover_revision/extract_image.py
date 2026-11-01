from pypdf import PdfReader
p=PdfReader('cover_revision/inspect-source.pdf').pages[0]
for i,x in enumerate(p.images):
 print(i,x.name,x.image.size,x.image.mode)
 x.image.save(f'cover_revision/extracted{i}.png')
