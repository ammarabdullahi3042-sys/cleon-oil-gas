from pypdf import PdfReader
p=PdfReader(r'C:\Users\ammar\FuelStationERP_V2\Version3\cover_revision\CLEON_Business_Plan_Dark.pdf').pages[10]
cs=p.get_contents()
ops=cs.operations
for i,(args,op) in enumerate(ops):
    if op in (b'rg',b'RG'):
        c=tuple(round(float(x),6) for x in args)
        if c in [(0.0,0.0,0.0),(0.1,0.1,0.1)] or True:
            print(i,op.decode(),c,[(ops[j][1].decode(),[str(x) for x in ops[j][0]]) for j in range(i+1,min(i+5,len(ops)))])
