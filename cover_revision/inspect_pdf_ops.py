from pypdf import PdfReader
from pypdf.generic import ContentStream
p=PdfReader('cover_revision/inspect-source.pdf').pages[0]
cs=ContentStream(p.get_contents(),p.pdf)
print('ops',len(cs.operations))
for i,(oper,op) in enumerate(cs.operations): print(i,repr(oper),repr(op)[:160])
