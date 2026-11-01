from pathlib import Path
root=Path('.')
docx=root/'build_cleon_profile.py'
s=docx.read_text(encoding='utf-8')
s=s.replace("    sec.header_distance=Inches(.32); sec.footer_distance=Inches(.35)\n", "    sec.header_distance=Inches(.32); sec.footer_distance=Inches(.35)\n    sec.different_first_page_header_footer=True\n")
start=s.index('    # Cover\n',s.index('def build(dark):'))
end=s.index('    # Company\n',start)
cover="""    # Cover
    p=d.add_paragraph(); p.paragraph_format.space_before=Pt(10); p.paragraph_format.space_after=Pt(5)
    if dark:
        p.add_run().add_picture(str(dark_logo),width=Inches(2.45))
    else:
        plaque=d.add_table(rows=1,cols=1)
        plaque.alignment=WD_TABLE_ALIGNMENT.LEFT; plaque.autofit=False
        plaque.columns[0].width=Inches(2.62)
        cell=plaque.cell(0,0); cell.width=Inches(2.62); shade(cell,NAVY)
        cell_margins(cell,top=80,start=100,bottom=80,end=100)
        table_borders(plaque,NAVY)
        lp=cell.paragraphs[0]; lp.paragraph_format.space_after=Pt(0)
        lp.add_run().add_picture(str(dark_logo),width=Inches(2.45))
    add_kicker(d,'COMPANY PROFILE  /  INVESTOR OVERVIEW',dark)
    p=d.add_paragraph(); p.paragraph_format.space_before=Pt(2); p.paragraph_format.space_after=Pt(2); p.paragraph_format.line_spacing=1.0
    set_run(p.add_run('CLEON OIL & GAS LTD'),29,True,base,HEAD_FONT)
    p=d.add_paragraph(); p.paragraph_format.space_after=Pt(8)
    set_run(p.add_run('Flexible Energy. Reliable Service.'),16,True,accent,HEAD_FONT)
    add_rule(p,ORANGE if dark else 'D9A46A')
    ph=d.add_paragraph(); ph.alignment=WD_ALIGN_PARAGRAPH.CENTER
    ph.paragraph_format.space_before=Pt(5); ph.paragraph_format.space_after=Pt(5)
    ph.add_run().add_picture(str(ASSET/('oil-and-gas-hero-dark-blend.png' if dark else 'oil-and-gas-hero-white-blend.png')),width=Inches(6.0))
    p=d.add_paragraph(); p.paragraph_format.space_before=Pt(3); p.paragraph_format.space_after=Pt(6); p.paragraph_format.line_spacing=1.12
    set_run(p.add_run('A Nigerian downstream energy company focused on disciplined fuel retail, forecourt management and technology-supported operations.'),13,False,base)
    add_para(d,'PMS & AGO RETAIL   /   STATION MANAGEMENT   /   NON-FUEL RETAIL   /   CLEAN-ENERGY OPPORTUNITIES',8.5,secondary,True,space_after=12)
    add_para(d,'REGISTERED IN NIGERIA  •  RC 8817624',9.5,accent,True,space_after=1)
    add_para(d,'Investor and partner overview  |  2026',8.5,secondary,space_after=0)
"""
s=s[:start]+cover+s[end:]
s=s.replace("'cleon-logo-white-background.png: dark-letter derivative for light surfaces.\\n'\n    'The profile source documents", "'cleon-logo-white-background.png: retained optional light-surface derivative.\\n'\n    'oil-and-gas-hero-source.png: original user-supplied photograph.\\n'\n    'oil-and-gas-hero-dark-blend.png and oil-and-gas-hero-white-blend.png: soft-edge blends for profile covers.\\n'\n    'The profile source documents")
docx.write_text(s,encoding='utf-8')

pdf=root/'build_cleon_profile_pdfs.py'
s=pdf.read_text(encoding='utf-8')
old=""" def cover_page(self,c,doc):
  self.background(c)
  c.saveState()
  c.setFillColor(colors.HexColor(self.theme['orange']))
  c.rect(LM,H-1.18*inch,.7*inch,3,fill=1,stroke=0)
  c.restoreState()
"""
new=""" def cover_page(self,c,doc):
  self.background(c)
"""
if old not in s: raise ValueError('Cover line block not found')
s=s.replace(old,new)
start=s.index(' logo=Image(',s.index('def make_story(flavor):'))
end=s.index('  NextPageTemplate(\'Body\'),PageBreak()]',start)+len("  NextPageTemplate('Body'),PageBreak()]")
coverpdf=""" logo=Image(str(ASSET/'cleon-logo-dark-background.png'),width=2.45*inch)
 logo.hAlign='LEFT'
 if flavor=='White':
  plaque=Table([[logo]],colWidths=[2.62*inch])
  plaque.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#131B26')),
                              ('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),
                              ('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),
                              ('BOX',(0,0),(-1,-1),0,colors.HexColor('#131B26'))]))
  logo=plaque
 hero=Image(str(ASSET/f'oil-and-gas-hero-{flavor.lower()}-blend.png'),width=6.0*inch)
 hero.hAlign='CENTER'
 story += [Spacer(1,.15*inch),logo,Spacer(1,.17*inch),
  Paragraph('COMPANY PROFILE  /  INVESTOR OVERVIEW',s['kicker']),Spacer(1,4),
  Paragraph('CLEON OIL &amp; GAS LTD',s['coverTitle']),
  Paragraph('Flexible Energy. Reliable Service.',s['coverTag'])]
 rule=Table([['']],colWidths=[CONTENT],rowHeights=[2])
 rule.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),colors.HexColor(t['orange']))]))
 story += [rule,Spacer(1,7),hero,Spacer(1,6),
  Paragraph('A Nigerian downstream energy company focused on disciplined fuel retail, forecourt management and technology-supported operations.',s['coverDesc']),
  Spacer(1,8),
  Paragraph('PMS &amp; AGO RETAIL&nbsp;&nbsp; / &nbsp;&nbsp;STATION MANAGEMENT&nbsp;&nbsp; / &nbsp;&nbsp;NON-FUEL RETAIL&nbsp;&nbsp; / &nbsp;&nbsp;CLEAN-ENERGY OPPORTUNITIES',s['kicker']),
  Spacer(1,.26*inch),
  Paragraph('<b>REGISTERED IN NIGERIA&nbsp;&nbsp; • &nbsp;&nbsp;RC 8817624</b>',s['body2']),
  Paragraph('Investor and partner overview&nbsp;&nbsp; | &nbsp;&nbsp;2026',s['small']),
  NextPageTemplate('Body'),PageBreak()]"""
s=s[:start]+coverpdf+s[end:]
pdf.write_text(s,encoding='utf-8')
print('Updated builders')

