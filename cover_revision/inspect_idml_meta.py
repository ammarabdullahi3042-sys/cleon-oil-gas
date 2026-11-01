import zipfile
z=zipfile.ZipFile('cover_revision/CLEON_Business_Plan_Dark.idml')
for n in z.namelist():
 if n.startswith('Spreads/'):
  x=z.read(n).decode(errors='ignore')
  if 'ParentStory="u20c"' in x:
   print(n)
   i=x.index('ParentStory="u20c"')
   print(x[max(0,i-1400):i+1400])
   break
