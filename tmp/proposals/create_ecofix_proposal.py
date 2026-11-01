from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from pathlib import Path

OUT=Path('output/proposals/Ecofix_Small_Scale_Recycling_Business_Proposal.docx')
GREEN='276749'; DARK='263238'; PALE='E8F2EC'; WHITE='FFFFFF'; GREY='58656B'
d=Document(); sec=d.sections[0]
sec.top_margin=Inches(.68); sec.bottom_margin=Inches(.65); sec.left_margin=Inches(.72); sec.right_margin=Inches(.72)
normal=d.styles['Normal']; normal.font.name='Aptos'; normal.font.size=Pt(10.5); normal.font.color.rgb=RGBColor(38,50,56)
normal.paragraph_format.space_after=Pt(6); normal.paragraph_format.line_spacing=1.08
for stylename,size in [('Heading 1',15),('Heading 2',11.5)]:
    st=d.styles[stylename]; st.font.name='Aptos Display'; st.font.size=Pt(size); st.font.bold=True; st.font.color.rgb=RGBColor.from_string(GREEN)
    st.paragraph_format.space_before=Pt(10); st.paragraph_format.space_after=Pt(4); st.paragraph_format.keep_with_next=True

def set_cell_shading(cell,fill):
    pr=cell._tc.get_or_add_tcPr(); shd=OxmlElement('w:shd'); shd.set(qn('w:fill'),fill); pr.append(shd)
def set_cell_margins(cell,top=65,start=85,bottom=65,end=85):
    tc=cell._tc; tcPr=tc.get_or_add_tcPr(); mar=OxmlElement('w:tcMar')
    for side,val in [('top',top),('start',start),('bottom',bottom),('end',end)]:
        el=OxmlElement('w:'+side); el.set(qn('w:w'),str(val)); el.set(qn('w:type'),'dxa'); mar.append(el)
    tcPr.append(mar)
def add_table(headers,rows,widths=None):
    t=d.add_table(rows=1,cols=len(headers)); t.alignment=WD_TABLE_ALIGNMENT.CENTER; t.style='Table Grid'; t.autofit=False
    if widths:
        for i,w in enumerate(widths): t.columns[i].width=Inches(w)
    for i,h in enumerate(headers):
        c=t.rows[0].cells[i]; c.text=h; set_cell_shading(c,GREEN); set_cell_margins(c)
        for p in c.paragraphs:
            for r in p.runs: r.font.name='Aptos'; r.font.size=Pt(9); r.font.bold=True; r.font.color.rgb=RGBColor(255,255,255)
    for ri,row in enumerate(rows):
        cells=t.add_row().cells
        for i,val in enumerate(row):
            cells[i].text=str(val); cells[i].vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER; set_cell_margins(cells[i])
            if ri%2==1: set_cell_shading(cells[i],'F5F8F6')
            for p in cells[i].paragraphs:
                p.paragraph_format.space_after=Pt(0); p.paragraph_format.line_spacing=1.0
                for r in p.runs: r.font.name='Aptos'; r.font.size=Pt(9)
    d.add_paragraph().paragraph_format.space_after=Pt(1)
    return t
def para(text,bold_prefix=None):
    p=d.add_paragraph()
    if bold_prefix and text.startswith(bold_prefix):
        p.add_run(bold_prefix).bold=True; p.add_run(text[len(bold_prefix):])
    else: p.add_run(text)
    return p
def bullet(text):
    p=d.add_paragraph(style='List Bullet'); p.paragraph_format.space_after=Pt(3); p.add_run(text); return p
def numbered(text):
    p=d.add_paragraph(style='List Number'); p.paragraph_format.space_after=Pt(3); p.add_run(text); return p
def add_hyperlink(p,text,url):
    rid=p.part.relate_to(url,'http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink',is_external=True)
    h=OxmlElement('w:hyperlink'); h.set(qn('r:id'),rid); run=OxmlElement('w:r'); rpr=OxmlElement('w:rPr')
    col=OxmlElement('w:color'); col.set(qn('w:val'),'0563C1'); rpr.append(col); under=OxmlElement('w:u'); under.set(qn('w:val'),'single'); rpr.append(under)
    txt=OxmlElement('w:t'); txt.text=text; run.append(rpr); run.append(txt); h.append(run); p._p.append(h)

# Header and title
p=d.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER; p.paragraph_format.space_before=Pt(28); p.paragraph_format.space_after=Pt(4)
r=p.add_run('ECOFIX'); r.font.name='Aptos Display'; r.font.size=Pt(29); r.font.bold=True; r.font.color.rgb=RGBColor.from_string(GREEN)
p=d.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER; p.paragraph_format.space_after=Pt(4)
r=p.add_run('SMALL-SCALE RECYCLING AGGREGATION HUB'); r.font.name='Aptos Display'; r.font.size=Pt(18); r.font.bold=True; r.font.color.rgb=RGBColor.from_string(DARK)
p=d.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER; p.paragraph_format.space_after=Pt(18)
r=p.add_run('Business Proposal | Masaka, Nasarawa State'); r.font.name='Aptos'; r.font.size=Pt(12); r.font.color.rgb=RGBColor.from_string(GREY)
p=d.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER; p.paragraph_format.space_after=Pt(18)
r=p.add_run('A phased, capital-conscious launch focused on collection, sorting and bulk sales'); r.italic=True; r.font.size=Pt(11); r.font.color.rgb=RGBColor.from_string(GREEN)
add_table(['Funding Request','Phase 1 Target','Proposed Location'],[['₦23.2 million','20–35 tonnes/month by month 6','Masaka, Nasarawa State']], [2.25,2.25,2.25])
p=d.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER; p.paragraph_format.space_before=Pt(5)
r=p.add_run('Prepared for prospective funding and operating partners | 30 October 2026'); r.font.size=Pt(9); r.font.color.rgb=RGBColor.from_string(GREY)
d.add_page_break()

d.add_heading('1. Executive Summary',level=1)
para('Ecofix Recycling & Resource Recovery Project proposes a lean recycling aggregation hub in Masaka, Nasarawa State, serving the Abuja–Nasarawa corridor. The first phase will buy, sort, weigh, store and sell clean, separated PET bottles, HDPE containers and selected scrap metals to established downstream recyclers. It will not begin as a full processing factory.')
para('The supplied feasibility study sets out an integrated plant handling agricultural residues, plastics and metals, with washing, shredding, pelletizing, composting and briquetting. Its small-scale scenario estimates ₦210 million in capital expenditure and 20–30 tonnes per day. This proposal replaces that industrial scope for the initial launch: lease a modest yard, hire transport as needed, outsource baling where required and target 20–35 tonnes per month. This keeps the initial funding requirement near ₦23.2 million and allows Ecofix to confirm supply and offtake before buying heavy machinery.')
para('The base financial case uses planning assumptions of ₦220/kg average sale price, ₦150/kg average purchase price and ₦15/kg for handling and transport. At 35 tonnes per month, the model estimates ₦7.7 million in sales and approximately ₦725,000 monthly operating surplus before tax, finance costs, depreciation and exceptional losses. The implied break-even volume is about 22 tonnes per month. These are decision assumptions, not guaranteed Masaka prices; launch should proceed only after written local buyer quotations and supplier checks confirm the spread.')

d.add_heading('2. Business Opportunity and Rationale',level=1)
para('The project will create a reliable local route from households, markets, institutions and informal collectors to recycling companies. Its initial value comes from aggregation, dependable weighing, clean sorting and predictable bulk delivery, rather than from installing a complex production line.')
for x in [
'Start with materials that can be sorted and stored safely without washing or chemical treatment: PET bottles, HDPE containers, aluminium and ferrous scrap.',
'Build a network of community collectors and small businesses, with clear grades, visible scales and prompt payment.',
'Sell only to pre-qualified buyers whose specifications, minimum load sizes, prices and payment terms are documented.',
'Defer agricultural residue processing until a separate buyer, seasonal supply plan and suitable product economics are established.'
]: bullet(x)

d.add_heading('3. Phase 1 Scope and Operating Model',level=1)
add_table(['Included at launch','Deferred until proven'],[
('Leased, fenced yard with a covered sorting and storage area','Land purchase or large factory construction'),
('Manual inspection, weighing, sorting and stock records','Plastic washing, shredding, extrusion or pelletizing'),
('PET, HDPE and separately graded aluminium/ferrous scrap','Composting or briquetting agricultural residues'),
('Sacks, cages and basic hand tools; outsourced baling if needed','Owned truck fleet and 24-hour production shifts'),
('Contracted haulage and scheduled buyer collection','Carbon-credit income or export revenue in the base case')], [3.45,3.3])
para('Operating flow: source material → inspect and reject contaminated loads → weigh in front of supplier → sort by material, colour and grade → record supplier, weight and price → store dry and separately → consolidate a buyer-approved load → dispatch against a weighbridge ticket and delivery receipt.')
para('Target capacity is 0.75–1.0 tonnes per operating day during the first three months, rising toward 1.5 tonnes per day as routes stabilize. The annual plan below ramps to 45 tonnes in month 12; it assumes 22 working days per month and should be reset after the first 60-day supply audit.')

d.add_heading('4. Comparative Assessment: Integrated Plant and Phase 1 Hub',level=1)
para('The two options serve the same long-term Ecofix vision but are different business models and investment stages. The original feasibility study describes an industrial, multi-stream processing facility. The current proposal starts with a leased aggregation hub that proves supply, pricing and buyer relationships before Ecofix commits to a factory.')
comparison=[
('Investment purpose','Integrated collection and processing plant','Low-capital market-entry and aggregation pilot'),
('Headline capital estimate','₦210M small scale; ₦820M medium scale','₦23.2M Phase 1 funding request'),
('Indicative throughput','20–30 tonnes/day small; 60–100 tonnes/day medium','20–35 tonnes/month by month 6'),
('Approximate monthly throughput','440–660 tonnes/month small; 1,320–2,200 tonnes/month medium at 22 operating days','20–35 tonnes/month; about 0.9–1.6 tonnes/day over 22 days'),
('Initial materials','Agricultural residues, plastics and metals','PET, HDPE, aluminium and ferrous scrap; agricultural residues deferred'),
('Activities','Collection, sorting, shredding, washing, pelletizing, composting, briquetting and metal recovery','Buy, inspect, weigh, grade, sort, store and bulk-sell; outsource haulage and baling as needed'),
('Site and assets','Land, buildings, processing equipment and vehicles included in original cost summary','Leased yard, basic fit-out and scales; contracted transport; no processing line'),
('Operating pattern','24-hour capability with staged shifts','One daytime shift, lean team and controlled operating hours'),
('Indicative development period','12–18 months in the supplied study','About 90 days to launch, subject to site and permit checks'),
('Commercial readiness required','Multiple product markets and large, steady feedstock volumes','Written buyer specifications and tested collection routes before full launch'),
('Role in Ecofix strategy','Long-term industrial destination','Proof-of-market stage that reduces early capital exposure')]
add_table(['Comparison point','Original integrated plant','Small-scale Phase 1 hub'],comparison,[1.55,2.55,2.6])
para('At 22 operating days per month, the original small-scale plant would process roughly 440–660 tonnes monthly. The proposed hub targets 20–35 tonnes monthly, or about 3%–8% of that throughput. The ₦210 million plant estimate is about nine times the Phase 1 request, while the ₦820 million medium-scale estimate is about 35 times the request. The pilot is therefore a lower-volume entry model, not the same plant built at a proportional discount.')

d.add_heading('Original Cost Summary Reconciliation',level=2)
cost_compare=[
('Land','15','40'),('Buildings','18','80'),('Equipment','73','400'),('Vehicles','30','90'),('Working capital','25','70'),('Contingency','16','55'),('Sum of listed cost items','177','735'),('Original headline CAPEX','210','820'),('Unreconciled difference','33','85')]
add_table(['Original cost item (₦M)','Small scale','Medium scale'],cost_compare,[4.1,1.25,1.35])
para('The supplied cost summary lists ₦177 million for the small-scale case and ₦735 million for the medium-scale case, while the headline estimates are ₦210 million and ₦820 million. The respective differences of ₦33 million and ₦85 million are not allocated in the summary. Before using either integrated-plant estimate for financing, Ecofix should reconcile these gaps and confirm whether they cover engineering, installation, import duties, utilities, permits, site works, taxes, commissioning or additional contingency.')

d.add_heading('What Each Option Requires to Succeed',level=2)
para('The integrated plant can capture more value per tonne by processing raw feedstock into flakes, pellets, compost or briquettes, but it also brings higher equipment, power, water, maintenance, technical-staffing, environmental-compliance and market-offtake requirements. It should proceed only with a detailed engineering design, verified feedstock catchment, equipment quotations, operating-cost model and buyer commitments for each product stream.')
para('The Phase 1 hub earns a narrower aggregation margin and remains exposed to market-price and transport risk. Its advantage is that Ecofix can start with manageable equipment, test actual local prices and document dependable monthly supply. It does not prove that a 20–30-tonne-per-day processing plant will be viable; it generates evidence needed to size that plant responsibly.')

d.add_heading('Recommended Staged Decision',level=2)
for x in [
'Launch the aggregation hub only after written offtake terms and a 30-day supply test confirm a viable spread at the proposed Masaka site.',
'Review actual tonnage, rejection rates, delivered selling price, collection cost, payment delays and operating surplus every month during the first six months.',
'Add a baler or other small pre-processing equipment only when measured freight savings or buyer requirements justify the cost.',
'Commission a fresh feasibility and engineering study for the integrated plant after the pilot has established recurring feedstock and buyers. Reconcile the original CAPEX gaps before seeking large-scale finance.',
'Develop agricultural-waste processing as a separate workstream once seasonal supply, product specification, permits and buyers for compost or briquettes are verified.'
]: bullet(x)

d.add_heading('5. Customers, Suppliers and Route to Market',level=1)
para('Suppliers will include waste pickers, market associations, beverage outlets, schools, offices, event centres and community collection points. Ecofix should begin with two or three collection routes and add neighbourhoods only when the depot can move stock promptly.')
para('Target customers are PET and HDPE recyclers, plastic flake or fibre processors, established aggregators, metal dealers and manufacturers that buy segregated feedstock. Before committing capital, management should obtain at least two written offtake indications for PET/HDPE and one for metals. Each indication should state grade, moisture/contamination limits, accepted packaging, minimum quantity, delivered or ex-yard pricing, transport responsibility and payment timing.')
para('Public Nigerian rate cards vary by location and material: current published PET collection/buy-back rates surfaced in the ₦120–₦200/kg range, while a reported Ibadan aggregation transaction described procurement near ₦150/kg and resale around ₦220–₦230/kg. These are reference points from other markets, not Masaka quotations [1–3].')

d.add_heading('6. Start-Up Budget',level=1)
para('The budget below is an initial planning allowance in naira, not a supplier quotation. It excludes land purchase, a dedicated truck and industrial processing machinery. Confirm each line with local quotations before drawdown.')
startup=[
('Lease advance/deposit for a modest yard','2.00'),
('Fencing, covered sorting bay, basic slab and drainage','3.50'),
('Platform scales, small scales and calibration weights','0.60'),
('Sorting benches, cages, sacks, hand trolley and basic tools','1.20'),
('Generator, wiring, lighting and essential electrical work','2.50'),
('PPE, fire extinguishers, first aid and site safety','0.55'),
('CAC, environmental compliance, bookkeeping and professional setup allowance','0.75'),
('Buyer sampling, route setup and initial contracted transport','0.40'),
('Opening feedstock purchasing float','6.00'),
('Three-month fixed operating reserve','3.60'),
('Contingency allowance','2.01'),
('Estimated Phase 1 funding requirement','23.11')]
add_table(['Use of funds','₦ million'],startup,[5.7,1.0])
para('Rounded funding request: ₦23.2 million. The working-capital float is essential: a yard can be equipped and still fail if it cannot pay suppliers promptly or hold a load until a buyer’s minimum quantity is reached. Transport will be contracted at the start; buying a truck would materially increase capital at risk. Advertised used mini-truck prices vary widely, so vehicle purchase should be considered only after route economics are measured [4].')

d.add_heading('7. Monthly Operating Cost and Unit Economics',level=1)
fixed=[('Yard rent provision','0.18'),('Site supervisor','0.18'),('Three sorters/handlers','0.30'),('Purchase/admin records officer','0.14'),('Security and cleaning','0.12'),('Utilities and communications','0.08'),('Maintenance, insurance and routine incidentals','0.20'),('Estimated fixed monthly operating cost','1.20')]
add_table(['Fixed cost allowance','₦ million/month'],fixed,[5.7,1.0])
para('Base case at 35 tonnes per month: average realized selling price ₦220/kg; average purchase price ₦150/kg; variable handling, packing and contracted transport allowance ₦15/kg. This leaves ₦55/kg contribution toward fixed costs. The selling and purchase assumptions are provisional and must be replaced with actual written Masaka/Abuja corridor quotations [1–3].')
add_table(['35-tonne monthly base case','₦ million'],[
('Sales: 35,000 kg × ₦220/kg','7.700'),
('Feedstock purchases: 35,000 kg × ₦150/kg','(5.250)'),
('Variable handling/haulage: 35,000 kg × ₦15/kg','(0.525)'),
('Contribution after feedstock and variable costs','1.925'),
('Fixed operating cost allowance','(1.200)'),
('Indicative operating surplus before finance, tax and depreciation','0.725')], [5.7,1.0])
para('Estimated break-even volume is about 22 tonnes per month under the base assumptions: ₦1.2 million fixed costs divided by ₦55 contribution per kilogram. The business should not rely on this average until it has measured real contamination, rejected loads, collection distances, price changes and payment delays.')
add_table(['Scenario','Sale / purchase / variable cost per kg','Break-even volume','Monthly result at 35 tonnes'],[
('Downside','₦180 / ₦150 / ₦15','About 80 t','Loss of about ₦675,000'),
('Base','₦220 / ₦150 / ₦15','About 22 t','Surplus of about ₦725,000'),
('Upside','₦230 / ₦140 / ₦15','About 16 t','Surplus of about ₦1,425,000')], [1.1,2.55,1.35,1.7])
para('The downside case shows why an offtake agreement and a price spread matter more than headline waste volumes. If the verified sale price is near ₦180/kg while suppliers require around ₦150/kg, the proposed operating scale is not viable without lower costs, a higher-value material mix or substantially more volume.')

d.add_heading('8. First-Year Ramp Plan',level=1)
vols=[10,15,20,25,30,30,35,35,35,40,40,45]
rows=[]
for i,v in enumerate(vols,1):
    result=v*0.055-1.2
    rows.append((f'Month {i}',str(v),f'{result:,.3f}'))
rows.append(('Year 1 total','360','5.400'))
add_table(['Period','Tonnes sold','Indicative operating surplus/(loss), ₦M'],rows,[1.7,1.5,3.5])
para('The Year 1 estimate implies ₦79.2 million sales at the assumed ₦220/kg average, ₦54.0 million feedstock purchases at ₦150/kg, ₦5.4 million variable handling/haulage and ₦14.4 million fixed costs, leaving about ₦5.4 million operating surplus before financing, tax, depreciation and extraordinary losses. The ramp assumes growing sales, not guaranteed demand; monthly cash requirements will be higher where buyers pay slowly.')

d.add_heading('9. Team and Controls',level=1)
para('The pilot can operate on one daytime shift with a lean team: one site supervisor, three sorters/handlers and one purchase/admin records officer. Security and occasional loading support can be contracted. The owner/manager will oversee buyer relationships, cash controls and weekly reporting.')
for x in [
'Issue a numbered receipt for every incoming load; record supplier, material grade, gross/tare/net weight, price and payment evidence.',
'Use calibrated scales and display the weight to suppliers; reconcile purchase records against dispatch and buyer weighbridge tickets.',
'Separate cash collection and stock recording where possible; authorize payments and discounts through a second person.',
'Track daily opening stock, receipts, dispatches, rejects, closing stock and price per kilogram by grade.',
'Refuse medical, hazardous, battery and e-waste materials; do not burn or wash plastics in Phase 1.'
]: bullet(x)

d.add_heading('10. Site, Environmental and Regulatory Readiness',level=1)
para('Lease a secure yard in or near Masaka with all-weather vehicle access, space for covered sorting and dry storage, adequate drainage and distance from homes, watercourses and sensitive uses. Confirm zoning, landlord consent and local authority requirements before signing a long lease.')
para('Before operation, confirm applicable environmental permits and registration requirements with NESREA and the Nasarawa State environmental authorities. NESREA identifies environmental permits for regulated operations and lists an Environmental Management Plan, CAC documents, tax clearance, EPR form and a ₦50,000 registration fee for EPR registration applications by producers, recyclers, collectors and PROs [5–6]. The proposal includes a compliance allowance, but the applicable permit category and total cost must be confirmed for the chosen site and activity.')
para('The site plan should include fire extinguishers, clear access lanes, no-smoking controls, PPE, a first-aid kit, covered storage for light plastics, and a spill/housekeeping routine. No process water or wastewater is planned in Phase 1 because the project will not wash or process the plastics.')

d.add_heading('11. Implementation Schedule',level=1)
add_table(['Timing from approval','Milestone'],[
('Weeks 1–2','Confirm buyer specifications and written prices; test three supply routes; inspect two or more yards; obtain equipment and site-work quotations.'),
('Weeks 3–4','Sign conditional lease; complete CAC and compliance checks; establish bank and stock-control records; agree haulage terms.'),
('Weeks 5–8','Secure and prepare yard; install scales, sorting area and safety equipment; train staff; run sample loads and verify buyer deductions.'),
('Weeks 9–12','Begin controlled commercial intake; target 10–20 tonnes/month; review margins weekly; increase volume only after positive load-level economics.'),
('Months 4–6','Target 25–35 tonnes/month if supply, quality, payment and offtake targets are met; prepare a phase-two investment decision.')], [1.5,5.2])

d.add_heading('12. Key Risks and Mitigation',level=1)
risks=[
('Price volatility','Use weekly buyer price checks, short inventory holding periods and a minimum gross spread rule before buying.'),
('Insufficient or inconsistent supply','Start with several supply channels, not a single community or collector; expand routes after measuring yields.'),
('Contamination and weight disputes','Publish acceptance grades, inspect before purchase, use visible calibrated scales and photograph dispatch weights.'),
('Transport cost and low density','Consolidate loads, compare contracted haulage rates, encourage buyer pickup, and outsource baling only when it lowers delivered cost.'),
('Delayed buyer payments','Set credit limits, prefer prompt payment for early transactions and reserve sufficient cash to continue supplier payments.'),
('Community and environmental concerns','Engage local leaders before site opening, maintain orderly storage and drainage, prevent litter and prohibit open burning.'),
('Regulatory delay','Confirm permit classification and inspection requirements before committing to site works.')]
add_table(['Risk','Control'],risks,[1.8,4.9])

d.add_heading('13. Funding Request and Conditions for Proceeding',level=1)
para('Ecofix seeks ₦23.2 million for a leased-site, small-scale aggregation pilot. Funding can be released in stages: (1) site lease and compliance readiness; (2) yard preparation, scales and handling equipment; and (3) working capital after buyer specifications and supply routes have been verified.')
para('Before the first full deployment, the project should secure:')
for x in [
'At least two written offtake quotations with grade, price, quantity, delivery and payment terms.',
'A 30-day supply test demonstrating a credible path to at least 22 tonnes per month at the required purchase price and quality.',
'Three local quotations for yard lease/site work and core equipment, with clear delivery and installation costs.',
'Written confirmation of the environmental permits and registrations applicable to the selected Masaka site.',
'A cash-control and inventory reporting system that the funder can review monthly.'
]: bullet(x)
para('If these checks do not confirm a positive unit margin, Ecofix should remain at a low-cost collection-and-brokerage pilot and defer the yard investment until prices and buyers improve.')

d.add_heading('14. Growth Path',level=1)
para('Phase 1 establishes local collection, sorting and reliable sales. Phase 2 may add a small baler only after the team measures monthly tonnage, freight savings and buyer requirements. A wash-and-flake line or agricultural residue operation should be considered only after Ecofix secures dependable feedstock, operating permits, utilities, technical support and signed offtake interest. Carbon-credit revenue is excluded from the forecast and should not be used to justify the initial investment.')

d.add_heading('References and Costing Basis',level=1)
para('Market rates below are public indicators from other Nigerian locations, not fixed Masaka prices or vendor offers. All proposal costs are planning allowances as at 30 October 2026 and should be validated with local quotations before funds are committed.')
refs=[
('1. Westman Recycle, published buy rates (updated 30 October 2026): PET ₦200/kg; hard plastics ₦120/kg; metals listed separately.','https://westmanrecycle.com/'),
('2. WasteAway Nigeria, live recyclable buy-back rate card: PET ₦180/kg and mixed plastic ₦110/kg at time of review.','https://wasteaway.ng/pricing'),
('3. Nairametrics, reporting on Nigerian plastic collectors and aggregators: collector purchase and resale examples, with prices varying by material and location.','https://nairametrics.com/2025/07/11/from-trash-to-millions-how-plastic-waste-collectors-in-nigeria-are-cashing-in/'),
('4. Jiji Nigeria used Toyota Dyna listings: asking prices vary widely by year, condition and configuration; listings are not completed sale prices.','https://jiji.ng/lagos/trucks-commercial-agricultiral/toyota-dyna-150'),
('5. NESREA FAQ, EPR registration documents and application fee information.','https://nesrea.gov.ng/faq/'),
('6. NESREA environmental permits overview.','https://nesrea.gov.ng/permits/')]
for label,url in refs:
    p=d.add_paragraph(style='List Number'); p.paragraph_format.space_after=Pt(2); add_hyperlink(p,label,url)

# Footer with page number field
for section_obj in d.sections:
    footer=section_obj.footer.paragraphs[0]; footer.alignment=WD_ALIGN_PARAGRAPH.CENTER
    r=footer.add_run('ECOFIX | Small-Scale Recycling Aggregation Proposal | '); r.font.name='Aptos'; r.font.size=Pt(8); r.font.color.rgb=RGBColor.from_string(GREY)
    fld=OxmlElement('w:fldSimple'); fld.set(qn('w:instr'),'PAGE'); footer._p.append(fld)

d.core_properties.title='Ecofix Small-Scale Recycling Aggregation Business Proposal'
d.core_properties.subject='Phase 1 business proposal for a small recycling aggregation hub in Masaka, Nasarawa State'
d.save(OUT)
print(OUT)
