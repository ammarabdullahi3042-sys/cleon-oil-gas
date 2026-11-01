from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from pathlib import Path

OUT = Path('output/reports')
OUT.mkdir(parents=True, exist_ok=True)

reports = [
{
'file':'Jenta_Apata_Ward_Meeting_Report_23_October_2026.docx',
'title':'Jos North Women Forum for Kefiano', 'subtitle':'Meeting with the Ward Women of Jenta Apata',
'date':'23 October 2026','venue':'','time':'1:44 p.m.; prayer at 2:40 p.m.',
'sections':[
('Opening and Welcome', 'The meeting brought together women from Jenta Apata Ward. Mrs Maureen Agusido, the ward women leader, welcomed the participants and made the introductions. The meeting was listed for 1:44 p.m., and prayer was said at 2:40 p.m.'),
('Purpose of the Meeting', 'The Plateau North Senatorial District coordinator of the Jos North Women Forum for Kefiano explained that the gathering was intended to brief the women on Chief Kefas Wungak Ropshik, popularly known as Kefiano, and his stated intention to seek the governorship of Plateau State in 2027. She encouraged participants to work through their party and ward leadership and to share information about the aspirant within their communities.'),
('Discussion', 'The coordinator presented the aspirant’s candidacy as an opportunity for younger leadership and urged the women to remain active in the political process. She expressed confidence that his leadership could help address challenges facing Plateau State. The discussion also underscored the importance of including persons with disabilities in community affairs and electoral participation, including voting and grassroots mobilization.'),
('Key Observations', 'The meeting highlighted the value of sustained ward-level communication, women’s participation in the 2027 election cycle, and the inclusion of persons with disabilities. The coordinator emphasized sharing information through established ward structures.'),
('Action Points', 'Participants were encouraged to share information about the aspirant through their community networks. The discussion also called for deliberate inclusion of persons with disabilities in civic engagement and grassroots mobilization.'),
('Conclusion', 'The gathering introduced the aspirant’s 2027 gubernatorial ambition and gave participants an opportunity to discuss women’s grassroots participation and the inclusion of persons with disabilities.')],
'attendees':['Laitu Joseph','Rifkatu Kancy','Sabina R. Kim','Chundung Ali Gyang','Esther C. Nyam','Augustina Nweke','Victoria Okonkwo','Benedeth Okeke','Christiana Peter','Laraba Bawa','Habiba Yakubu','Aisha Yusuf Adam','Hannah Augu','Dadung Margaret','Kaneng Jah','Nancy Peters','Echeazu Margaret','Esther Nwakasi','Mary Suleman','Aishatu Musa','Blessing Ngozi Emmanuel','Amina Abubaka','Ichadija Mahmud','Lilian Mancha Davou','Martha Audu','Zinatu Sale Yakubu','Yosi Masoyi','Martha A. Sabo','Hafsat Abdul Karim Ibrahim','Aisha Aliyu','Rabi Maazu','Bridgs Nwadike','Christiana Young Treasures','Martha John','Selya Gideon Pam','Lami Umar Lawal','Paulina A. GJ','Maimuna Akumbo Saleh','Baraatu Iliasac','Anwilika Joy Ufere','Sarah Ali Auta','Hannatu Daniel','Nenle Kida'],
'phones':['08036108992','07035586372','08936232229','080699658170','08965791896','07935215190','09135604416','07055580195','07965981311','','08061689672','07043559349','07036176552','07038506445','07089348314','07089348314','08101019123','07065579556','07037950078','08139375021','08036127123','09060891026','07035308910','09027343475','','07035055597','08065441466','08096070078','08932887520','08039119853','08144096656','09137972662','08959068867','09060757705','08036196547','09034822851','08033103175','08062678833','07069606299','08935956879','07035191379','09020500047','08037806128']
},
{
'file':'Garba_Daho_Ward_Meeting_Report_21_October_2026.docx',
'title':'Jos North Women Forum for Kefiano', 'subtitle':'Ward Women Meeting in Garba Daho',
'date':'21 October 2026','venue':'Usman Katsina Ward (meeting for Garba Daho Ward)','time':'',
'sections':[
('Opening and Welcome', 'Hajiya Zinatu Sale Yakubu, Women Leader of Garba Daho Ward, welcomed the participants and expressed appreciation for the strong turnout.'),
('Purpose of the Meeting', 'Hajiya Khadija Gambo Hawaja, Coordinator of the Jos North Women Forum for Kefiano, thanked the women for attending and outlined the purpose of the gathering: to introduce Chief Kefas Ropshik, popularly known as Kefiano, whose stated ambition was to contest for Governor of Plateau State in 2027 on the platform of the Peoples Democratic Party (PDP).'),
('Coordinator’s Remarks', 'The coordinator urged participants to attend future meetings and to communicate information about the aspirant within their communities. She proposed a grassroots outreach chain in which each woman would inform others, broadening awareness through personal and ward networks. She also encouraged women to participate in politics and prepare to vote in the 2027 election.'),
('Contributions', 'Former ward women leader Hajiya Usman Zakari affirmed her support for Chief Kefas Ropshik. Hajiya Aisha Aliyu expressed confidence in the coordinator and endorsed the initiative. Nana Kida of Naraguta B Ward reflected on her experience during the 2023 election and urged continued attention to the needs of women in Jos North. Kachollom Dazong, Women Leader in Jos North, thanked participants for their confidence and called for unity, cautioning against segregation and religious division.'),
('Key Observations', 'Participants welcomed the coordinator’s direct engagement with ward women. The discussion underscored sustained grassroots communication, women’s participation in party affairs, unity across religious and community lines, and the importance of learning from the 2023 election experience.'),
('Action Points', 'Participants were encouraged to attend future meetings, share information through their networks, and prepare to participate in the 2027 election.'),
('Conclusion', 'The gathering brought ward women together to discuss political participation, grassroots outreach, leadership and community unity. Participants emphasized the value of continued engagement across the ward structure.')],
'attendees':['Maureen Agusiobo','Selya Gideon Pam','Paulina Afe George','Maimuna Akumbo Saleh','Nene Kida','Martha John','Joy Ufere','Hannatu Azi','Yosi Masoyi','Aisha Aliyu','Hafsat Abdul Karim Ibrahim','Ramatu A’dam','A’shatu Salisu','Zinatu Sale Yakubu','Rukayya Lawal','Aishatu Ismail','Baraato Iilysc','Bridget Nwadus','Rabi Muazu'],
'phones':['08036176266','08030196547','08033103175','08062678833','08037806128','09060757705','08035956879','08928899448','08965441466','08939119853','08032887520','09068729495','08136598714','07935055597','','08032631906','09069606299','091379772662','08144096656']
},
{
'file':'Jenta_Adamu_Ward_Meeting_Report_22_October_2026.docx',
'title':'Jos North Women Forum for Kefiano', 'subtitle':'Stakeholders’ Meeting in Jenta Adamu Ward',
'date':'22 October 2026','venue':'Bishop’s Court, Jenta Adamu','time':'11:00 a.m.',
'sections':[
('Opening and Welcome', 'The meeting opened at 11:00 a.m. with a prayer. The Jenta Adamu Ward Women Leader introduced the ward women leaders and thanked the Jos North coordinator, Hajiya Khadija Gambo Hawaja, for the opportunity to convene the ward stakeholders.'),
('Purpose of the Meeting', 'The coordinator thanked the participants and outlined two objectives: to introduce Chief Kefas Ropshik (Kefiano), whose stated ambition was to seek the Plateau State governorship in 2027, and to recognize the contribution of women in Jenta Adamu and across Jos North to political participation.'),
('Coordinator’s Remarks', 'The coordinator acknowledged women’s contributions to previous general elections and criticized the incumbent administration for what she characterized as unfulfilled commitments to women. She expressed confidence that the situation could improve under Chief Kefas and urged participants to contribute to the 2027 campaign. She also announced her intention to introduce a distinctive uniform for women in Jos North.'),
('Participants’ Contributions', 'Selbong Nandal of Jenta Makeri said the coordinator’s remarks had renewed her willingness to vote. Comfort Bala of Jenta welcomed the direct outreach and the opportunity to discuss women’s concerns. Udale Joseph of West of Mind reflected on the previous general election. Yossy Maxwell of Tudun Wada expressed gratitude for the coordinator’s appointment, called for trusted party agents at vote collection centres, and appealed for support for women’s empowerment.'),
('Key Observations', 'The discussion centred on women’s electoral participation, representation and empowerment. Participants highlighted the need for dependable party agents, sustained engagement with ward women, and practical support for women and young people.'),
('Action Points', 'The Jenta Adamu ward group presented a list of 25 women. The coordinator encouraged continued engagement in the 2027 election process and proposed a uniform for women in Jos North. A participant called for trusted agents at collection centres and support for women’s empowerment.'),
('Conclusion', 'The stakeholders’ meeting gave participants an opportunity to discuss women’s political participation and concerns in Jenta Adamu. Their contributions addressed election engagement, representation and empowerment.')],
'attendees':['Lame S. Kuwa','Helen Kefas','Helen Gado','Nandak Selbol','Rose Joseph','Bernadette Ikedishi','Esther Ramadan','Fibi Samuel','Udale Joseph','Mrs Mary','Esther Sati','Mary Stephen','Sarah Chunwang','Lydia Auta','Martina Aleje','Hauwa Ibrahim','Sarah Sunday','Veronica Chollom','Theresa Tarfa','Angela Okeke','Helen John','Julians Ishaku','Tina Jebedo Vonke','Sarah Goltok','Ayo Danjuma'],
'phones':['08100775761','07060776717','08061279850','08064708242','07035013998','08065329472','0806348985','08025610701','08068132108','07033413507','08068097633','07037994530','09028328468','08069622838','08106000820','08054968689','07045018878','08067789040','07034371184','08038919395','08035815314','08031105776','07037786812','07079373115','08036175513']
}
]

def shade(cell, color):
    tcPr = cell._tc.get_or_add_tcPr(); shd = OxmlElement('w:shd'); shd.set(qn('w:fill'), color); tcPr.append(shd)

def set_horizontal_table_rules(table):
    tblPr = table._tbl.tblPr
    borders = OxmlElement('w:tblBorders')
    for edge in ('top','left','bottom','right','insideH','insideV'):
        el=OxmlElement('w:'+edge)
        el.set(qn('w:val'), 'single' if edge in ('top','bottom','insideH') else 'nil')
        el.set(qn('w:sz'), '6'); el.set(qn('w:color'), '000000'); borders.append(el)
    tblPr.append(borders)

for data in reports:
    d=Document(); sec=d.sections[0]
    sec.top_margin=Inches(.48); sec.bottom_margin=Inches(.48); sec.left_margin=Inches(.55); sec.right_margin=Inches(.55)
    normal=d.styles['Normal']; normal.font.name='Times New Roman'; normal.font.size=Pt(11); normal.font.color.rgb=RGBColor(0,0,0)
    normal.paragraph_format.space_after=Pt(5); normal.paragraph_format.line_spacing=1.0
    title=d.add_paragraph(style='Title'); title.alignment=WD_ALIGN_PARAGRAPH.CENTER
    title.paragraph_format.space_before=Pt(12); title.paragraph_format.space_after=Pt(28); tr=title.add_run(data['title'].upper()); tr.font.name='Times New Roman'; tr.font.size=Pt(20); tr.font.bold=True; tr.font.color.rgb=RGBColor(255,0,0)
    p=d.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER; p.paragraph_format.space_after=Pt(3)
    r=p.add_run(data['subtitle'].upper()); r.font.name='Times New Roman'; r.bold=True; r.font.size=Pt(12); r.font.color.rgb=RGBColor(0,128,0)
    p=d.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER; p.paragraph_format.space_after=Pt(10)
    r=p.add_run('OFFICIAL MINUTES'); r.font.name='Times New Roman'; r.bold=True; r.font.size=Pt(11); r.font.color.rgb=RGBColor(0,128,0)
    meta=[('Date',data['date'])]
    if data['venue']: meta.append(('Venue',data['venue']))
    if data['time']: meta.append(('Time',data['time']))
    p=d.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER; p.paragraph_format.space_after=Pt(42)
    r=p.add_run(' | '.join(f'{label}: {value}' for label,value in meta)); r.font.name='Times New Roman'; r.font.size=Pt(11)
    def add_section(heading,body):
        h=d.add_paragraph(); h.paragraph_format.keep_with_next=True; h.paragraph_format.space_before=Pt(7); h.paragraph_format.space_after=Pt(2)
        rr=h.add_run(heading); rr.bold=True; rr.font.name='Arial'; rr.font.size=Pt(12); rr.font.color.rgb=RGBColor(255,0,0)
        p=d.add_paragraph(body); p.alignment=WD_ALIGN_PARAGRAPH.JUSTIFY
    add_section(*data['sections'][0])
    h=d.add_paragraph(); h.paragraph_format.space_before=Pt(8); h.paragraph_format.space_after=Pt(4); h.paragraph_format.keep_with_next=True
    rr=h.add_run('Full Attendance List'); rr.bold=True; rr.font.name='Arial'; rr.font.size=Pt(12); rr.font.color.rgb=RGBColor(255,0,0)
    t=d.add_table(rows=1, cols=3); t.style='Table Grid'; t.alignment=WD_TABLE_ALIGNMENT.CENTER
    t.autofit=False; t.columns[0].width=Inches(.6); t.columns[1].width=Inches(3.8); t.columns[2].width=Inches(2.3); set_horizontal_table_rules(t)
    for i,txt in enumerate(['S/No.','Name','Phone No.']):
        t.cell(0,i).text=txt
        for r in t.cell(0,i).paragraphs[0].runs: r.font.name='Times New Roman'; r.bold=True; r.font.size=Pt(10.5)
    for idx,(name,phone) in enumerate(zip(data['attendees'],data['phones']),1):
        cells=t.add_row().cells; cells[0].text=str(idx); cells[1].text=name; cells[2].text=phone
        for c in cells:
            for p in c.paragraphs:
                p.paragraph_format.space_after=Pt(0); p.paragraph_format.space_before=Pt(0)
                for r in p.runs: r.font.name='Times New Roman'; r.font.size=Pt(10.5)
    for heading,body in data['sections'][1:]: add_section(heading,body)
    d.add_paragraph()
    p=d.add_paragraph(); p.paragraph_format.space_before=Pt(8); p.paragraph_format.space_after=Pt(4)
    r=p.add_run('________________________________'); r.font.name='Times New Roman'; r.font.size=Pt(10)
    p=d.add_paragraph(); r=p.add_run('Hajiya Khadija Gambo Hawaja\nCoordinator'); r.font.name='Times New Roman'; r.font.size=Pt(10)
    d.core_properties.title=data['subtitle']; d.core_properties.subject='Official meeting minutes'
    d.save(OUT/data['file'])
print('\n'.join(str(OUT/x['file']) for x in reports))
