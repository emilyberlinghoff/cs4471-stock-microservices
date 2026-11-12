"""Generate Word/PDF packets, an editable slide deck and a workbook preview."""
from pathlib import Path
import re, subprocess, html
from docx import Document
from docx.shared import Pt
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape, A3
from reportlab.lib.units import inch
from pptx import Presentation
from pptx.util import Inches, Pt as PptPt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
import openpyxl

ROOT=Path(__file__).resolve().parents[1];DOC=ROOT/'docs/pr2';OUT=ROOT/'output/pr2'
OUT.mkdir(parents=True,exist_ok=True)
styles=getSampleStyleSheet()
styles.add(ParagraphStyle(name='Body12',fontName='Helvetica',fontSize=11.5,leading=15,spaceAfter=7))
styles.add(ParagraphStyle(name='Cell9',fontName='Helvetica',fontSize=9,leading=12))
styles['Heading1'].fontSize=18;styles['Heading1'].leading=23
styles['Heading2'].fontSize=13;styles['Heading2'].leading=17

def clean(text):
    text=re.sub(r'\[([^]]+)\]\(([^)]+)\)',r'\1 (\2)',text)
    return html.escape(text.replace('**','').replace('`',''))

def footer(canvas,doc):
    canvas.saveState();canvas.setFont('Helvetica',8)
    canvas.drawString(40,23,'Group 11 · PR2 · November 11, 2026 · Prepared by Emily Berlinghoff')
    canvas.drawRightString(letter[0]-40,23,str(doc.page));canvas.restoreState()

def pdf_from_md(source,target):
    lines=source.read_text().splitlines();story=[];paragraph=[];table=[];yaml=False
    def flush_para():
        if paragraph:story.append(Paragraph(clean(' '.join(paragraph)),styles['Body12']));paragraph.clear()
    def flush_table():
        if not table:return
        rows=[]
        for line in table:
            values=[v.strip() for v in line.strip().strip('|').split('|')]
            if all(re.fullmatch(r':?-+:?',v.replace(' ','')) for v in values):continue
            rows.append([Paragraph(clean(v),styles['Cell9']) for v in values])
        widths=[468/len(rows[0])]*len(rows[0])
        t=Table(rows,colWidths=widths,repeatRows=1,hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#dce7f3')),('VALIGN',(0,0),(-1,-1),'TOP'),('GRID',(0,0),(-1,-1),.4,colors.HexColor('#aab8c5')),('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
        story.extend([t,Spacer(1,10)]);table.clear()
    for i,line in enumerate(lines):
        if i==0 and line=='---':yaml=True;continue
        if yaml:
            if line=='---':yaml=False
            continue
        if line.startswith('|'):flush_para();table.append(line);continue
        flush_table()
        if line.startswith('!['):
            flush_para();m=re.match(r'!\[([^]]*)\]\(([^)]+)\)',line)
            if m:
                im=Image(str(source.parent/m[2]));im.drawHeight=im.imageHeight*468/im.imageWidth;im.drawWidth=468
                story.extend([im,Paragraph(clean(m[1]),styles['Caption'] if 'Caption' in styles else styles['BodyText']),Spacer(1,10)])
        elif line.startswith('#'):
            flush_para();level=len(line)-len(line.lstrip('#'))
            if level==1 and ('View ' in line or line.startswith('# References')):story.append(PageBreak())
            story.append(Paragraph(clean(line.lstrip('#').strip()),styles['Heading1' if level==1 else 'Heading2']))
        elif not line.strip():flush_para()
        elif line.startswith('```'):flush_para()
        else:paragraph.append(line)
    flush_para();flush_table()
    SimpleDocTemplate(str(target),pagesize=letter,leftMargin=72,rightMargin=72,topMargin=46,bottomMargin=40,title=source.stem,author='Emily Berlinghoff').build(story,onFirstPage=footer,onLaterPages=footer)

names=[('01_Architecture_and_Communication','01_Architecture_and_Communication'),('03_Demo_and_Acceptance','04_Demo_and_Acceptance'),('04_AI_Comparison_and_Lessons','05_AI_Comparison_and_Lessons')]
for source_name,target_name in names:
    source=DOC/(source_name+'.md');target=OUT/(target_name+'.docx')
    subprocess.run(['pandoc',str(source),'--from=gfm','--standalone','--resource-path='+str(DOC),'-o',str(target)],check=True)
    document=Document(target)
    document.styles['Normal'].font.name='Calibri';document.styles['Normal'].font.size=Pt(12)
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    for run in para.runs:run.font.size=Pt(9)
    document.save(target)
    pdf_from_md(source,OUT/(target_name+'.pdf'))

prs=Presentation();prs.slide_width=Inches(13.333);prs.slide_height=Inches(7.5)
def slide(title,bullets=None,figure=None):
    sl=prs.slides.add_slide(prs.slide_layouts[6])
    tb=sl.shapes.add_textbox(Inches(.5),Inches(.25),Inches(12.3),Inches(.8)).text_frame
    p=tb.paragraphs[0];p.text=title;p.font.size=PptPt(30);p.font.bold=True;p.font.color.rgb=RGBColor(23,54,93)
    if figure:
        # Native editable summary diagrams keep all slide text at least 20 pt.
        # Detailed sequence diagrams remain in the accompanying Word/PDF packet.
        def node(x,y,text,width=2.5):
            shape=sl.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,Inches(x),Inches(y),Inches(width),Inches(1.15))
            shape.fill.solid();shape.fill.fore_color.rgb=RGBColor(238,244,251)
            tf=shape.text_frame;tf.word_wrap=True
            tf.paragraphs[0].text=text;tf.paragraphs[0].font.size=PptPt(21)
            tf.paragraphs[0].font.color.rgb=RGBColor(23,54,93)
        def label(x,y,text,width=11.8,size=22):
            tf=sl.shapes.add_textbox(Inches(x),Inches(y),Inches(width),Inches(1.2)).text_frame
            tf.word_wrap=True;tf.paragraphs[0].text=text;tf.paragraphs[0].font.size=PptPt(size)
        if figure=='module':
            for y,sid,core in [(1.6,'S4','SMA core'),(3.4,'S5','Comparison core')]:
                for x,text in [(0.6,sid+' HTTP'),(3.7,'Validation'),(6.8,'Orchestration'),(9.9,core)]:node(x,y,text)
                for x in [3.2,6.3,9.4]:label(x,y+.2,'→',width=.5,size=24)
            label(.7,5.3,'Each service owns its provider and registry modules. No S4 ↔ S5 imports. Detailed module catalogue is in the architecture packet.')
        elif figure=='components':
            for x,y,text in [(.7,1.4,'Consumer GUI'),(5.3,1.4,'Primary / backup registry'),(.7,3.4,'S2 / S3 APIs'),(5.3,3.4,'S4 / S5 APIs'),(9.6,3.4,'Alpha Vantage')]:node(x,y,text,width=2.8)
            label(3.6,1.5,'↔',width=.8,size=24);label(8.3,3.5,'↔',width=.8,size=24)
            label(.7,5.2,'GUI discovery/integration: planned. S4/S5 leases: local tested. Provider calls: implemented; live entitlement unverified.')
        elif figure=='communication':
            for x,text in [(.45,'Request'),(3,'Validate'),(5.55,'Fetch'),(8.1,'Calculate'),(10.65,'JSON')]:node(x,1.8,text,width=2.2)
            label(.7,3.5,'Invalid input → 400 before provider access. Upstream failure → structured error. Valid data → dated means or ranking.')
            label(.7,5.2,'S5 requests run concurrently. Any failed stock produces no ranking. Full message sequence is in the architecture packet.')
        else:
            for x,text in [(.6,'Start'),(3.75,'Register both'),(6.9,'Renew every 3 s'),(10.05,'Stop renewals')]:node(x,1.8,text,width=2.6)
            label(.7,3.6,'Registry lease: 10 seconds, pruned every 2 seconds. Shutdown removal is expiry, not an immediate DELETE.')
            label(.7,5.2,'Local evidence: S4 removed after 11.41 seconds; S5 remained healthy. Recovery re-registers unknown nodes.')
    else:
        tf=sl.shapes.add_textbox(Inches(.75),Inches(1.3),Inches(11.8),Inches(5.55)).text_frame
        tf.word_wrap=True
        for i,text in enumerate(bullets or []):
            p=tf.paragraphs[0] if i==0 else tf.add_paragraph();p.text=text;p.font.size=PptPt(23);p.space_after=PptPt(20)
    footer_box=sl.shapes.add_textbox(Inches(.5),Inches(7.05),Inches(12.3),Inches(.3)).text_frame
    footer_box.paragraphs[0].text='Group 11 · PR2 draft · Team review pending'
    footer_box.paragraphs[0].font.size=PptPt(20)
    return sl

slide('Stock Analytics — Progress Report 2',[
 'CS4471 Software Architectures · Group 11 · November 12, 2026',
 'Aashka Patel · Emily Berlinghoff · Maxime Lavoie · Gordon Xu',
 'Architecture and service evidence prepared by Emily; integrate the team’s other quality views and latest deployment updates.'])
slide('Progress verified as of November 11',[
 'S2: 39 offline tests in the branch audit. S4: 56 tests. S5: 61 tests.',
 'S4/S5 now register and renew leases; local removal/isolation test passed.',
 'Main is not yet an integrated release. S1 and GUI integration remain pending.'])
slide('Module view — code responsibilities',figure='module')
slide('Runtime components and connectors',figure='components')
slide('Communication quality view — behavior',figure='communication')
slide('Registry lease lifecycle',figure='leases')
slide('S4 — Moving Averages',[
 'User selects one symbol, date range and exchange calendar.',
 '20/50-session trailing windows; up to 49 earlier sessions; no future prices.',
 'Invalid input returns JSON errors. Incomplete windows retain null/reason; no fabricated values.'])
slide('S5 — Stock Comparison',[
 'User selects 2–5 stocks, dates and exchange calendars.',
 'Concurrent retrieval; common endpoints; rank unrounded changes and break exact ties alphabetically.',
 'Any unusable stock aborts the ranking. Shared lookup wait budget: 12 seconds.'])
slide('Local registry integration evidence',[
 'Both services registered against the image’s extracted registry source over real local HTTP.',
 'S4 stopped gracefully and disappeared after 11.41 seconds; S5 stayed registered with health 200.',
 'Removal is lease expiry. No immediate delete route exists in the inspected registry.'])
slide('Data retrieval decision and limits',[
 'Request-driven retrieval; no fixed stock list and no mandatory shared database.',
 'Provider credentials are environment configuration. No API key has been configured yet.',
 'One-year live retrieval needs full-history entitlement. Mocked tests are not live market evidence.'])
slide('Remaining team work and honest scope',[
 'Add Gordon’s two quality views with their templates and explanations.',
 'Registry owner: returned descriptions, explicit deregistration if required, deployment URLs.',
 'Resolve S3 review blockers, connect real GUI discovery/service calls, and verify cloud behavior.'])
slide('Proposed presentation and demo handoffs',[
 'Gordon: scope and GUI. Max: S2 and returns. Emily: architecture, S4/S5. Aashka: registry/cloud/S3.',
 'Confirm assignments with the team; rehearse timing and transitions.',
 'Fallback: honest structured errors plus fixed-data test evidence, not fake live results.'])
slide('PR2 delivery checklist',[
 'Updated plan and task statuses; implemented versus planned links labelled.',
 'Module + C&C + three quality views with supporting documentation.',
 'Preliminary demo, slides, binder/TOC and verified OWL submission cutoff.'])
slide('Demo sequence — ready for rehearsal',[
 'Run tests → start S4/S5 → health/metadata → invalid-input examples.',
 'Show numerical fixed-data results; live examples only after a valid key is configured.',
 'Register both services → stop S4 → verify expiry and S5 isolation → hand back to GUI/cloud presenter.'])
total=len(prs.slides)
for i,sl in enumerate(prs.slides,1):
    tf=sl.shapes.add_textbox(Inches(11.9),Inches(7.05),Inches(1),Inches(.3)).text_frame
    tf.paragraphs[0].text=f'{i} of {total}';tf.paragraphs[0].font.size=PptPt(20)
prs.save(OUT/'03_PR2_Support_Presentation.pptx')

# Word-readable binder entry point with file-oriented TOC.
d=Document();d.add_heading('CS4471 — Group 11 PR2: Emily’s Deliverables',0)
d.add_paragraph('Prepared November 11, 2026 for PR2 due November 12. Review with the team before submission.')
d.add_heading('Table of contents / file order',1)
for item in ['01_Architecture_and_Communication.docx / .pdf — Module, C&C, communication packets',
 '02_Project_Plan_Emily_Update.xlsx — updated planning copy and evidence sheet',
 '03_PR2_Support_Presentation.pptx — editable team support draft',
 '04_Demo_and_Acceptance.docx / .pdf — runbook, presenter proposal and acceptance matrix',
 '05_AI_Comparison_and_Lessons.docx / .pdf — review draft with no invented manual baseline',
 '06_Plan_Preview.pdf — readable Gantt/task-list rendering',
 'README.md / delivery_manifest.json — evidence, branch commits and remaining requirements']:
 d.add_paragraph(item,style='List Bullet')
d.add_heading('Required team additions',1)
d.add_paragraph('The team must supply Gordon’s two quality views, actual GUI/cloud evidence, final reflection and presenter confirmation. No API key, human rehearsal, deployment acceptance or OWL submission is claimed complete.')
d.save(OUT/'00_Title_and_Contents.docx')

# Render the actual workbook data without relying on Excel formula caches.
wb=openpyxl.load_workbook(OUT/'02_Project_Plan_Emily_Update.xlsx',data_only=False)
story=[Paragraph('PR2 plan preview — Gantt table',styles['Heading1'])]
g=wb['Gantt Chart'];rows=[['ID','Task','Status','Start','End','Dependencies']]
for r in g.iter_rows(min_row=3,max_row=70,max_col=7,values_only=True):
 if r[0] is None:continue
 rows.append([str(r[0]),str(r[2]),str(r[3]),r[4].strftime('%b %d') if r[4] else '',r[5].strftime('%b %d') if r[5] else '',str(r[6] or '')])
def table_pdf(rows,widths):
 t=Table([[Paragraph(clean(str(v)),styles['Cell9']) for v in row] for row in rows],colWidths=widths,repeatRows=1)
 t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#dce7f3')),('GRID',(0,0),(-1,-1),.25,colors.grey),('VALIGN',(0,0),(-1,-1),'TOP'),('BOTTOMPADDING',(0,0),(-1,-1),5)]));return t
story.append(table_pdf(rows,[50,360,90,65,65,120]));story.append(PageBreak());story.append(Paragraph('Service task list — all owners retained',styles['Heading1']))
rows=[['Row / Gantt','Owner','Task','Status / due','Notes']]
for i,r in enumerate(wb['Service Task List'].iter_rows(min_row=3,max_col=8,values_only=True),3):
 if r[0] is None:continue
 rows.append([f'{i} / {r[1]}',r[4] or 'Unassigned',r[3] or '',str(r[5] or '')+' / '+(r[6].strftime('%b %d') if r[6] else 'TBD'),r[7] or ''])
story.append(table_pdf(rows,[65,75,230,90,290]))
SimpleDocTemplate(str(OUT/'06_Plan_Preview.pdf'),pagesize=landscape(A3),leftMargin=35,rightMargin=35,topMargin=35,bottomMargin=35).build(story)
print('Generated documents:',*[p.name for p in OUT.iterdir()],sep='\n')
