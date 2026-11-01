from pypdf import PdfReader
from zipfile import ZipFile
from pathlib import Path
for flavor in ('Dark','White'):
 pdf=PdfReader(f'cover_revision/CLEON_Business_Plan_{flavor}.pdf')
 print(flavor,'pages=',len(pdf.pages),'cover text=',repr(pdf.pages[0].extract_text()))
 z=ZipFile(f'cover_revision/CLEON_Business_Plan_{flavor}.idml')
 print('idml integrity=',z.testzip())
