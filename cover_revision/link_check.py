import zipfile
z=zipfile.ZipFile('cover_revision/CLEON_Business_Plan_Dark.idml')
print([x for x in z.namelist() if 'link' in x.lower() or 'manifest' in x.lower()])
for n in z.namelist():
 if n.lower().endswith('.xml') and ('link' in n.lower() or n.endswith('DesignMap.xml')):
  x=z.read(n).decode('utf8',errors='ignore')
  if 'cleon_cover' in x: print(n,x[x.index('cleon_cover')-250:x.index('cleon_cover')+250])
