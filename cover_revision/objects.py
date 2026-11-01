import zipfile
from lxml import etree
z=zipfile.ZipFile('cover_revision/CLEON_Business_Plan_Dark.idml')
r=etree.fromstring(z.read('Spreads/Spread_u1ee.xml'))
for e in r:
 if e.tag.rsplit('}',1)[-1] in ('TextFrame','Rectangle','Graphic','Polygon','Oval'):
  print(e.tag.rsplit('}',1)[-1], e.get('Self'),e.get('ParentStory'),e.get('ItemTransform'))
  paths=e.xpath('.//*[local-name()="PathPointType"]/@Anchor')
  if paths: print(' points',paths[:4])
