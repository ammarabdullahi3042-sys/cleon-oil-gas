from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from pathlib import Path

out=Path('output/reports/Jos_North_Ward_Chairmen_Follow_Up_Meeting_29_October_2026.docx')
d=Document(); sec=d.sections[0]
sec.top_margin=Inches(.48); sec.bottom_margin=Inches(.55); sec.left_margin=Inches(.55); sec.right_margin=Inches(.55)
normal=d.styles['Normal']; normal.font.name='Times New Roman'; normal.font.size=Pt(11); normal.font.color.rgb=RGBColor(0,0,0)
normal.paragraph_format.space_after=Pt(5); normal.paragraph_format.line_spacing=1.0

title=d.add_paragraph(style='Title'); title.alignment=WD_ALIGN_PARAGRAPH.CENTER
title.paragraph_format.space_before=Pt(12); title.paragraph_format.space_after=Pt(25)
r=title.add_run('JOS NORTH WARD CHAIRMEN FOLLOW-UP MEETING'); r.font.name='Times New Roman'; r.font.size=Pt(19); r.font.bold=True; r.font.color.rgb=RGBColor(255,0,0)
p=d.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER; p.paragraph_format.space_after=Pt(2)
r=p.add_run('HAUSA AND FULANI COMMUNITY CONSULTATION'); r.font.name='Times New Roman'; r.font.size=Pt(12); r.font.bold=True; r.font.color.rgb=RGBColor(0,128,0)
p=d.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER; p.paragraph_format.space_after=Pt(13)
r=p.add_run('OFFICIAL MINUTES'); r.font.name='Times New Roman'; r.font.size=Pt(11); r.font.bold=True; r.font.color.rgb=RGBColor(0,128,0)
p=d.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER; p.paragraph_format.space_after=Pt(35)
r=p.add_run('Date: 29 October 2026 | Venue: PDP Jos North Party Office'); r.font.name='Times New Roman'; r.font.size=Pt(11)

def heading(txt):
    p=d.add_paragraph(); p.paragraph_format.keep_with_next=True; p.paragraph_format.space_before=Pt(8); p.paragraph_format.space_after=Pt(3)
    r=p.add_run(txt); r.font.name='Arial'; r.font.size=Pt(12); r.font.bold=True; r.font.color.rgb=RGBColor(255,0,0)
    return p
def para(txt):
    p=d.add_paragraph(txt); p.alignment=WD_ALIGN_PARAGRAPH.JUSTIFY; return p
def add_table(headers, rows, widths):
    t=d.add_table(rows=1,cols=len(headers)); t.alignment=WD_TABLE_ALIGNMENT.CENTER; t.autofit=False
    for i,width in enumerate(widths): t.columns[i].width=Inches(width)
    for i,label in enumerate(headers):
        t.cell(0,i).text=label
        for r in t.cell(0,i).paragraphs[0].runs: r.font.name='Times New Roman'; r.font.size=Pt(10.5); r.font.bold=True
    for row in rows:
        cells=t.add_row().cells
        for i,value in enumerate(row):
            cells[i].text=value
            for p in cells[i].paragraphs:
                p.paragraph_format.space_after=Pt(0); p.paragraph_format.space_before=Pt(0)
                for r in p.runs: r.font.name='Times New Roman'; r.font.size=Pt(10.5)
    for row in t.rows:
        for c in row.cells: c.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
    borders=OxmlElement('w:tblBorders')
    for edge in ('top','left','bottom','right','insideH','insideV'):
        el=OxmlElement('w:'+edge); el.set(qn('w:val'),'single' if edge in ('top','bottom','insideH') else 'nil'); el.set(qn('w:sz'),'6'); el.set(qn('w:color'),'000000'); borders.append(el)
    t._tbl.tblPr.append(borders)
    return t

heading('Background and Purpose')
para('The meeting was convened at the PDP Jos North Party Office on 29 October as a follow-up to the urgent discussion held the previous day at the residence of Hajiya Khadijah Gambo Hawaja. The earlier meeting had been called to address concerns raised by the Director General (DG) for Kefiano Campaign about the proposed process for compiling data on 120 persons from each polling unit. The follow-up was arranged in line with the previous discussion and to continue consultation with ward chairmen, including leaders from the Christian community.')

heading('Proceedings and Matters Raised')
para('At the 28 October meeting, Hajiya Khadijah opened the discussion by explaining its purpose, after which the ward chairmen were invited to share their views on the proposed data-gathering process. The chairmen raised the following concerns:')
issues=[
'Insufficient logistics to carry out the exercise effectively.',
'A perception among ward leaders that they were not trusted or adequately included in the process.',
'Limited consultation with key stakeholders about whether the proposed approach was suitable for their communities.',
'Outstanding payment of the amount agreed to support the data collation exercise.',
'Resistance within communities, which participants linked to past experiences of perceived deception by the PDP, particularly during and after the 2023 elections.'
]
for item in issues:
    p=d.add_paragraph(style='List Number'); p.paragraph_format.space_after=Pt(3); p.alignment=WD_ALIGN_PARAGRAPH.JUSTIFY; p.add_run(item)

heading('Follow-Up and Way Forward')
para('Hajiya Khadijah proposed that the next consultation include the other ward chairmen from the Christian community. The aim was to develop a fuller account of the issues through a consolidated report of findings, observations and recommendations, and to identify a constructive way forward ahead of the elections. The 29 October meeting at the PDP Jos North Party Office was convened to carry this agreed follow-up forward.')
para('The attendance update for 29 October indicates that nearly all the chairmen attended, with three absent. The names of those absent were not provided.')

heading('Attendance at the 29 October Follow-Up')
att=[
('Barr. Aminu Sani','Coordinator, Jos North','Present'),
('Jos North PDP Chairman','Chairman','Present'),
('Jos North PDP Secretary','Secretary','Present'),
('Ward chairmen','Hausa and Fulani communities','Nearly all present; three absent')]
add_table(['Attendee / Group','Position / Representation','Attendance'],att,[2.5,2.55,2.0])

heading('Ward Chairmen Named at the 28 October Meeting')
para('The following seven Hausa and Fulani community ward chairmen were listed as attendees at the 28 October consultation:')
names=[
('Musa Lawal Ahmad','Gangare Ward','08035015762'),
('Alh. Yawale Falke','Garba Daho Ward','08033342449'),
('Kawu Babanjoda','Naraguta A Ward','07035586406'),
('Ado Garba Jibiya','Abba na Shehu Ward','07038746261'),
('Musa Yunusa Ubale Ibrahim','Katsina Ward','07067985449'),
('Alkasim Musa Wetka','Sarkin Arab Ward','08063970491'),
('Alhassan Umar Aliyu Ali Kazaure','Kazaure Ward','07060905093')]
add_table(['Name','Ward','Phone No.'],names,[3.0,2.0,2.0])

heading('Conclusion')
para('The 29 October follow-up continued the consultation initiated the previous day and brought together party officials and ward leadership to address concerns about the proposed polling-unit data exercise. The central issues for further consideration were adequate logistical support, stakeholder confidence and consultation, agreed facilitation, and community trust. A broader discussion with Christian community ward chairmen was proposed to inform a comprehensive report and recommendations ahead of the elections.')

d.add_paragraph()
p=d.add_paragraph(); p.paragraph_format.space_before=Pt(8); p.paragraph_format.space_after=Pt(4)
r=p.add_run('________________________________'); r.font.name='Times New Roman'; r.font.size=Pt(10)
p=d.add_paragraph(); r=p.add_run('Hajiya Khadijah Gambo Hawaja\nCoordinator, Jos North'); r.font.name='Times New Roman'; r.font.size=Pt(10)
d.core_properties.title='Jos North Ward Chairmen Follow-Up Meeting'; d.core_properties.subject='Official meeting minutes'
d.save(out)
print(out)
