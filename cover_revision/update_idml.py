from zipfile import ZipFile, ZIP_DEFLATED
from pathlib import Path
from xml.etree import ElementTree as ET
VISION='To set the standard for accurate, safe and transparent fuel retail across Nigeria.'
TAG='Flexible Energy. Reliable Service.'
for flavor in ('Dark','White'):
 path=Path(f'cover_revision/CLEON_Business_Plan_{flavor}.idml'); tmp=path.with_suffix('.idml.new')
 with ZipFile(path) as zin, ZipFile(tmp,'w',ZIP_DEFLATED) as zout:
  for item in zin.infolist():
   data=zin.read(item.filename)
   if item.filename=='Stories/Story_u20c.xml':
    root=ET.fromstring(data); story=root.find('Story'); ps=story.findall('ParagraphStyleRange')
    def txt(p): return ''.join(c.text or '' for c in p.findall('.//Content'))
    cover_end='CONFIDENTIAL. This document is intended for the named recipient only. It is a business framework and does not state site-specific revenue forecasts or funding amounts, which will be provided once site, contract, supplier, capacity and sales inputs are confirmed.'
    remove=[]; found=False
    for p in ps:
     t=txt(p)
     if t=='BUSINESS PLAN' or found:
      remove.append(p)
      if t==cover_end: found=False; break
      found=True
    for p in remove: story.remove(p)
    execp=next((p for p in story.findall('ParagraphStyleRange') if txt(p)=='1. Executive Summary'),None)
    if execp is None: raise RuntimeError('Executive Summary paragraph not found')
    execp.set('PageBreakBefore','true')
    data=ET.tostring(root,encoding='UTF-8',xml_declaration=True)
   zout.writestr(item,data)
 tmp.replace(path)
print('Updated IDML story to use the rasterized cover artwork and start body copy on the next page.')
