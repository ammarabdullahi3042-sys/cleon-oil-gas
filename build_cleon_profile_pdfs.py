from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, PageBreak,
                                Image, Table, TableStyle, NextPageTemplate, KeepTogether)
from reportlab.pdfbase.pdfmetrics import stringWidth

ROOT=Path(__file__).parent/'CLEON_Company_Profile'
ASSET=ROOT/'assets'
themes={
 'Dark':dict(bg='#131B26',panel='#1B2734',panel2='#18232F',ink='#F3F5F7',muted='#B7C0CA',accent='#DDAE67',orange='#F47A20',line='#405164',white='#FFFFFF'),
 'White':dict(bg='#FFFFFF',panel='#F6F8FA',panel2='#EDF1F5',ink='#131B26',muted='#586676',accent='#995416',orange='#B65612',line='#D6DEE6',white='#FFFFFF')
}
W,H=letter
LM=0.85*inch; RM=.85*inch; TM=.83*inch; BM=.62*inch
CONTENT=W-LM-RM

def make_styles(t):
 return {
  'kicker':ParagraphStyle('kicker',fontName='Helvetica-Bold',fontSize=8.5,leading=11,textColor=colors.HexColor(t['orange']),spaceAfter=4),
  'h1':ParagraphStyle('h1',fontName='Helvetica-Bold',fontSize=24,leading=28,textColor=colors.HexColor(t['accent']),spaceAfter=10),
  'h2':ParagraphStyle('h2',fontName='Helvetica-Bold',fontSize=14,leading=18,textColor=colors.HexColor(t['accent']),spaceBefore=9,spaceAfter=5,keepWithNext=True),
  'body':ParagraphStyle('body',fontName='Helvetica',fontSize=10.8,leading=15,textColor=colors.HexColor(t['ink']),spaceAfter=9),
  'body2':ParagraphStyle('body2',fontName='Helvetica',fontSize=10,leading=13.4,textColor=colors.HexColor(t['muted']),spaceAfter=8),
  'bullet':ParagraphStyle('bullet',fontName='Helvetica',fontSize=10.3,leading=14,textColor=colors.HexColor(t['ink']),leftIndent=14,firstLineIndent=-10,spaceAfter=6),
  'factkey':ParagraphStyle('factkey',fontName='Helvetica-Bold',fontSize=9.2,leading=12,textColor=colors.HexColor(t['accent'])),
  'factval':ParagraphStyle('factval',fontName='Helvetica',fontSize=9.5,leading=12.5,textColor=colors.HexColor(t['ink'])),
  'coverTitle':ParagraphStyle('coverTitle',fontName='Helvetica-Bold',fontSize=28,leading=32,textColor=colors.HexColor(t['ink']),spaceAfter=7),
  'coverTag':ParagraphStyle('coverTag',fontName='Helvetica-Bold',fontSize=16,leading=20,textColor=colors.HexColor(t['accent']),spaceAfter=8),
  'coverDesc':ParagraphStyle('coverDesc',fontName='Helvetica',fontSize=14,leading=20,textColor=colors.HexColor(t['ink'])),
  'small':ParagraphStyle('small',fontName='Helvetica',fontSize=8.5,leading=11,textColor=colors.HexColor(t['muted'])),
 }

class ProfileDoc(BaseDocTemplate):
 def __init__(self,path,t,**kwargs):
  self.theme=t
  super().__init__(str(path),pagesize=letter,leftMargin=LM,rightMargin=RM,topMargin=TM,bottomMargin=BM,**kwargs)
  frame=Frame(LM,BM,CONTENT,H-TM-BM,id='main',leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0)
  self.addPageTemplates([
   PageTemplate(id='Cover',frames=[frame],onPage=self.cover_page),
   PageTemplate(id='Body',frames=[frame],onPage=self.body_page),
  ])
 def background(self,c):
  c.saveState(); c.setFillColor(colors.HexColor(self.theme['bg'])); c.rect(0,0,W,H,fill=1,stroke=0); c.restoreState()
 def cover_page(self,c,doc):
  self.background(c)
 def body_page(self,c,doc):
  self.background(c); t=self.theme
  c.saveState()
  c.setStrokeColor(colors.HexColor(t['line'])); c.setLineWidth(.6)
  c.line(LM,H-.48*inch,W-RM,H-.48*inch)
  c.setFont('Helvetica-Bold',8); c.setFillColor(colors.HexColor(t['muted']))
  c.drawRightString(W-RM,H-.37*inch,'CLEON  /  COMPANY PROFILE')
  c.line(LM,.43*inch,W-RM,.43*inch)
  c.setFont('Helvetica-Bold',7.7); c.setFillColor(colors.HexColor(t['muted']))
  c.drawString(LM,.25*inch,'CLEON OIL & GAS LTD    •    NIGERIA')
  c.setFont('Helvetica',7.7); c.drawRightString(W-RM,.25*inch,str(doc.page))
  c.restoreState()

def section(story,n,title,s):
 story.append(Paragraph(f'{n}  /  COMPANY PROFILE',s['kicker']))
 story.append(Paragraph(title,s['h1']))
 # underline rule
 line=Table([['']],colWidths=[CONTENT],rowHeights=[1.5])
 line.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#F47A20'))]))
 story.extend([line,Spacer(1,10)])

def facts(rows,s,t):
 data=[]
 for k,v in rows:
  data.append([Paragraph(k,s['factkey']),Paragraph(v,s['factval'])])
 tab=Table(data,colWidths=[1.55*inch,CONTENT-1.55*inch],hAlign='LEFT')
 cmds=[('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),10),('RIGHTPADDING',(0,0),(-1,-1),10),
       ('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8),
       ('LINEBELOW',(0,0),(-1,-1),.45,colors.HexColor(t['line']))]
 for i in range(len(data)):
  cmds.append(('BACKGROUND',(0,i),(-1,i),colors.HexColor(t['panel'] if i%2==0 else t['panel2'])))
 tab.setStyle(TableStyle(cmds)); return tab

def bullet(lead,body,s,t):
 return Paragraph(f'<font color="{t["accent"]}"><b>{lead}</b></font> {body}',s['bullet'])

def make_story(flavor):
 t=themes[flavor]; s=make_styles(t); story=[]
 from PIL import Image as PILImage
 logo_path=ASSET/'cleon-logo-dark-background.png'
 logo_w,logo_h=PILImage.open(logo_path).size
 logo=Image(str(logo_path),width=2.45*inch,height=2.45*inch*logo_h/logo_w)
 logo.hAlign='LEFT'
 if flavor=='White':
  plaque=Table([[logo]],colWidths=[2.62*inch])
  plaque.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#131B26')),
                              ('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),
                              ('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),
                              ('BOX',(0,0),(-1,-1),0,colors.HexColor('#131B26'))]))
  logo=plaque
 hero_path=ASSET/f'oil-and-gas-hero-{flavor.lower()}-blend.png'
 hero_w,hero_h=PILImage.open(hero_path).size
 hero=Image(str(hero_path),width=6.0*inch,height=6.0*inch*hero_h/hero_w)
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
  NextPageTemplate('Body'),PageBreak()]
 section(story,'01','A focused downstream operator',s)
 story.append(Paragraph('CLEON Oil &amp; Gas Ltd is a Nigerian downstream energy company focused on fuel retail, station management, non-fuel retail development and technology-enabled forecourt services.',s['body']))
 story.append(Paragraph('The business plan identifies a pilot station in Kafanchan, Kaduna State, with operations beginning in October 2025. CLEON’s operating approach pairs day-to-day station controls with measured site and service expansion.',s['body2']))
 story.append(Paragraph('Company at a glance',s['h2']))
 story.append(facts([
  ('Legal name','CLEON Oil &amp; Gas Ltd'),('Registration','RC 8817624, Nigeria'),
  ('Sector','Downstream oil and gas retail'),('Pilot location','Kafanchan, Kaduna State'),
  ('Operating scope','PMS and AGO retail, station management and non-fuel retail')
 ],s,t))
 story += [Spacer(1,9),Paragraph('Vision',s['h2']),
  Paragraph('To set the standard for accurate, safe and transparent fuel retail across Nigeria.',ParagraphStyle('vision',parent=s['body'],fontName='Helvetica-Bold',fontSize=13.2,leading=17,textColor=colors.HexColor(t['accent']),spaceAfter=6)),
  Paragraph('Mission',s['h2']),
  Paragraph('To deliver high-quality white products (PMS and AGO) and clean-energy solutions (LPG and CNG) through an optimized network of leased and managed retail forecourts.',s['body'])]
 story.append(PageBreak())
 section(story,'02','Forecourt services built around control',s)
 story.append(Paragraph('CLEON’s business model combines fuel retail with station operating services and adjacent forecourt opportunities. The mix is designed to fit the needs and readiness of each site.',s['body']))
 story += [
  bullet('PMS &amp; AGO retail.','Retail operations supported by receipt, pump-sales and tank-dip records.',s,t),
  bullet('Station management.','Operating support for CLEON-operated and third-party forecourts, with clear reconciliation and reporting processes.',s,t),
  bullet('Non-fuel retail.','Development of complementary retail services and commercial opportunities around the forecourt.',s,t),
  bullet('LPG &amp; CNG.','Clean-energy options identified for phased evaluation and future expansion.',s,t),
  Paragraph('A flexible operating structure',s['h2']),
  Paragraph('CLEON’s plan is based on leased and managed retail sites. This allows the company to evaluate each location, supply route, operating partner and investment requirement before committing to an expansion step.',s['body2']),
  facts([
   ('Site readiness','Review equipment, utilities, access, local competition and safety needs.'),
   ('Operating controls','Set product, cash, stock, reconciliation and reporting routines.'),
   ('Partner model','Define operating responsibilities and information flow for managed sites.'),
   ('Expansion','Assess non-fuel retail and clean-energy opportunities as site conditions allow.')
  ],s,t),PageBreak()]
 section(story,'03','Operational visibility from the forecourt',s)
 story.append(Paragraph('CLEON has developed a station operations application for key forecourt records. It brings daily operating information into a more consistent view for station teams and management.',s['body']))
 story += [
  bullet('Stock and sales.','Records receipts, pump sales, tank dips and stock positions to support variance review.',s,t),
  bullet('Commercial control.','Tracks selling prices and product costs to support gross-profit and net-profit reporting.',s,t),
  bullet('Payment visibility.','Records cash, POS, deposits, transfers and account balances for reconciliation.',s,t),
  bullet('Management reports.','Supports Excel, PDF and CSV exports for internal and owner reporting.',s,t),
  Paragraph('Website and investor information',s['h2']),
  Paragraph('CLEON’s website is already created and provides the company’s online presence. CLEON intends to use it to give authorized investors a clear view of contributions, deployment milestones and available reports, with timely progress updates.',s['body']),
  Paragraph('The current station application stores desktop data locally. Live investor balances, automated alerts and connected reporting should be enabled only after secure hosting, access controls, data synchronization, audit history and backups are in place.',s['body2']),
  Paragraph('Technology roadmap',s['h2']),
  facts([
   ('In use','Local desktop application for pilot station records and report exports.'),
   ('Next','Regular backups, user roles and an audit trail for edits and approvals.'),
   ('Later','Secure shared service with remote multi-site access and investor views.')
  ],s,t),PageBreak()]
 section(story,'04','Scale in stages, report with clarity',s)
 story.append(Paragraph('CLEON’s expansion path is intended to follow operating readiness: stabilize controls at the pilot, review opportunities with site-level evidence, and expand services when supply, safety, people and funding requirements are understood.',s['body']))
 story.append(Paragraph('Priority workstreams',s['h2']))
 story += [
  bullet('Strengthen the pilot.','Build reliable stock, sales, payment and maintenance records and close routine reconciliations.',s,t),
  bullet('Prepare for replication.','Confirm backup procedures, user permissions, audit history and consistent reporting before remote multi-site operation.',s,t),
  bullet('Evaluate growth opportunities.','Assess additional managed or leased sites, non-fuel retail and future LPG/CNG opportunities against local conditions.',s,t),
  Paragraph('Investor visibility',s['h2']),
  Paragraph('The planned investor information area is intended to make the use and progress of investment easier to follow. Subject to secure implementation and verified records, it can present:',s['body2']),
  bullet('Capital activity.','Contributions received and their recorded deployment.',s,t),
  bullet('Milestone progress.','Status of agreed site, equipment and operating milestones.',s,t),
  bullet('Business updates.','Available operating and management reports, with timely notices of material progress.',s,t),
  Paragraph('CLEON should distinguish actual results from targets and estimates in investor communications. The content of each update should be based on reconciled business records.',s['body2']),
  Paragraph('Company details',s['h2']),
  facts([
   ('Company','CLEON Oil &amp; Gas Ltd'),('Registration','RC 8817624'),('Country','Nigeria'),
   ('Head office and contact','Details to be confirmed by company management.')
  ],s,t)]
 return story

for flavor,t in themes.items():
 out=ROOT/f'CLEON_Company_Profile_{flavor}.pdf'
 doc=ProfileDoc(out,t,title='CLEON Company Profile',author='CLEON Oil & Gas Ltd')
 doc.build(make_story(flavor))
 print(out)

