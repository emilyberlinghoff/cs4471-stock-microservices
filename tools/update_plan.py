"""Create a reviewable planning copy; never overwrite the user's input workbook."""
from pathlib import Path
from datetime import datetime, timedelta
from copy import copy
import argparse
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.formatting.rule import FormulaRule
from openpyxl.worksheet.datavalidation import DataValidation

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description='Prepare an evidence-based copy of the PR2 plan.')
parser.add_argument('source',nargs='?',type=Path,default=Path('/Users/emilyberlinghoff/Downloads/02_Services_Requirements_and_Project_Plan-4.xlsx'))
SOURCE=parser.parse_args().source
OUT=ROOT/'output/pr2/02_Project_Plan_Emily_Update.xlsx'
w=openpyxl.load_workbook(SOURCE)
s=w['Service Task List'];g=w['Gantt Chart']
changes=[]
now=datetime(2026,11,11);pr2=datetime(2026,11,12)

def gid(v):
    if v is None:return ''
    return f'{float(v):.2f}' if isinstance(v,(float,int)) else str(v)

def note(row,text):
    old=s.cell(row,8).value or ''
    s.cell(row,8,str(old).rstrip()+' | '+text)

for row in range(3,s.max_row+1):
    owner=str(s.cell(row,5).value or '')
    task=str(s.cell(row,4).value or '')
    ident=gid(s.cell(row,2).value)
    status=s.cell(row,6).value
    if status=='Completed':s.cell(row,6,'Complete')
    if 'Emily' not in owner and owner!='All':continue
    if s.cell(row,7).value is None and (owner=='Emily' or ident in ['6.20','6.21','6.22','6.24','6.25']):
        s.cell(row,7,pr2 if ident.startswith('6.') else now)
    before=s.cell(row,6).value
    if owner=='Emily':
        if 'Register service at startup' in task:
            s.cell(row,6,'In Progress')
            note(row,'Implemented/tested registration, heartbeat recovery and graceful lease cessation. Local test: S4 expired after 11.41 s while S5 remained healthy. Immediate deregistration endpoint absent in registry; owner contract remains pending.')
        elif ident=='4.04':
            s.cell(row,6,'In Progress');note(row,'Request-driven provider integration and mocked tests complete. User confirms no Alpha Vantage key configured; authenticated access not verified.')
        elif ident=='4.05':
            s.cell(row,6,'Not Started');note(row,'Blocked by provider key/entitlement. Symbols and dates remain user-selected at request time; no fixed company list or actual one-year dataset is claimed.')
        elif ident=='4.06':
            s.cell(row,6,'Complete');note(row,'S4/S5 source tests verify limits, bad payloads, invalid/missing observations, timeout errors and recovery. Offline implementation evidence; no live-provider recovery claim.')
        elif ident=='4.07':
            s.cell(row,6,'Complete');note(row,'Implemented request-driven retrieval, no mandatory shared database or S1 dependency, no synthetic fallback; decision recorded in docs/data-retrieval-decision.md.')
        elif ident=='4.08':
            s.cell(row,6,'In Progress');note(row,'Fixed-data numerical/coverage checks pass. Actual one-year source completeness and correctness await an entitled key and a live request.')
        elif ident in ['6.18','6.19']:
            s.cell(row,6,'Complete');note(row,'Delivered PR2 view with primary diagram, element catalogue, context, variability and architecture background; implemented/planned boundaries and source evidence included.')
        elif ident in ['1.03','1.04']:
            s.cell(row,6,'Complete');note(row,'Prepared dated evidence-based planning copy with PR2 milestones, dependencies and status reconciliation. Other owners still confirm their task completion and unassigned work.')
        elif 'Test normal and error cases' in task:
            note(row,'Current suites: S4 56 and S5 61 offline tests; additional real local registry HTTP test passed. Cloud/GUI and authenticated provider testing remain separate.')
    elif ident=='6.20' and 'Emily' in owner:
        pass
    if ident=='6.20':
        s.cell(row,6,'In Progress');note(row,'Emily communication view complete. The two other quality views remain Gordon/team work; do not mark all three complete.')
    if owner=='All':
        if ident in ['6.21','6.22','6.24','6.25','6.16']:
            s.cell(row,6,'In Progress' if ident!='6.25' else 'Not Started')
            note(row,{'6.21':'Demo runbook and local lifecycle evidence prepared; actual GUI/cloud verification and rehearsal pending.',
                      '6.22':'AI comparison/lessons draft prepared; student-authored baseline was not supplied, and no independent authorship claim is invented.',
                      '6.24':'Editable PR2 support deck prepared; merge Gordon quality views and team updates before calling the full presentation complete.',
                      '6.25':'Presenter/run-of-show proposal prepared; human rehearsal and timing have not occurred.',
                      '6.16':'Acceptance matrix and known results prepared; final system/cloud acceptance execution remains pending.'}[ident])
    if before!=s.cell(row,6).value:changes.append([f'Service Task List!F{row}',before,s.cell(row,6).value,task])

# Distinguish identical per-service data blocks rather than deleting assigned work.
current=''
for row in range(3,s.max_row+1):
    sid=s.cell(row,1).value
    if sid in ['S1','S2','S3','S4','S5']:current=sid
    if sid=='DAT1' and current:
        s.cell(row,3,f'Stock Data Acquisition — {current}')
        note(row,f'Scope: {current}. These are per-service tasks, not repeated shared completion claims.')

if s['I92'].value:
    s['H92']=str(s['I92'].value);s['I92']=None
s.column_dimensions['I'].hidden=True
for row,text in [(88,'System overview provided in Emily’s architecture packet; unassigned owner/team to review.'),
                 (92,'Combined ownership/decomposition example provided in Emily’s packet; team to review.')]:
    s.cell(row,6,'In Progress');note(row,text)

# Summaries are derived from task rows; this does not silently change another owner's tasks.
task_status={}
for row in range(3,s.max_row+1):
    key=gid(s.cell(row,2).value)
    status=s.cell(row,6).value
    if key and status:task_status.setdefault(key,[]).append(status)
def rollup(values):
    return 'Complete' if values and all(v=='Complete' for v in values) else 'In Progress' if any(v in ['Complete','In Progress'] for v in values) else 'Not Started'

dependencies={'4.02':'4.01','4.03':'4.02,4.09','4.04':'4.01','4.05':'4.04','4.06':'4.04','4.07':'4.04','4.08':'4.05,4.06',
 '4.09':'2.01,2.02','5.04':'4.04,4.09','5.05':'4.04,4.09','6.03':'3.04,6.18,6.19,6.20',
 '6.04':'4.03,4.09','6.17':'2.01,2.02,2.03,2.04','6.18':'3.04','6.19':'3.04','6.20':'6.18,6.19',
 '6.21':'6.27','6.23':'6.18,6.19','6.24':'6.17,6.18,6.19,6.20','6.25':'6.24,6.21','6.26':'6.24,6.25','6.27':'6.04,5.07'}
for row in range(3,71):
    ident=gid(g.cell(row,1).value)
    if ident in task_status:
        new=rollup(task_status[ident]);old=g.cell(row,4).value
        if old!=new:changes.append([f'Gantt Chart!D{row}',old,new,'Rollup from task list; other owner statuses remain subject to confirmation'])
        g.cell(row,4,new)
    if ident in dependencies:g.cell(row,7,dependencies[ident])
    if ident in ['6.03','6.06','6.17','6.18','6.19','6.20','6.21','6.22','6.23','6.24','6.25','6.26','6.27']:
        g.cell(row,6,pr2)
    if ident in ['6.18','6.19','6.20','6.23','6.24','6.27']:g.cell(row,6,now)
    if ident=='6.16':g.cell(row,6,None)
    if ident in ['1.09','1.10']:g.cell(row,6,datetime(2026,10,22))
    g.cell(row,1).number_format='0.00' if ident and not ident.endswith('.00') else '0'
for row in [3,14,19,24,34,43]:
    prefix=int(g.cell(row,1).value)
    children=[g.cell(r,4).value for r in range(3,71) if isinstance(g.cell(r,1).value,(int,float)) and int(g.cell(r,1).value)==prefix and r!=row]
    g.cell(row,4,rollup(children))
g['F3']=datetime(2026,10,22)
g['F43']=pr2

# Uniform daily axis and correctly anchored formatting for every task row.
for col in range(8,68):
    g.cell(2,col,datetime(2026,10,10)+timedelta(days=col-8)).number_format='mmm d'
    g.column_dimensions[openpyxl.utils.get_column_letter(col)].width=4
g.conditional_formatting._cf_rules.clear();s.conditional_formatting._cf_rules.clear()
for sheet,col,end in [(g,'D',70),(s,'F',s.max_row)]:
    for status,color in [('Complete','C6EFCE'),('In Progress','FFEB9C'),('Not Started','F2F2F2')]:
        sheet.conditional_formatting.add(f'{col}3:{col}{end}',FormulaRule(formula=[f'${col}3="{status}"'],fill=PatternFill('solid',fgColor=color)))
    sheet.data_validations.dataValidation.clear()
    validation=DataValidation(type='list',formula1='"Not Started,In Progress,Complete"',allow_blank=True)
    sheet.add_data_validation(validation);validation.add(f'{col}3:{col}{end}')
g.conditional_formatting.add('H3:BO70',FormulaRule(formula=['AND(H$2>=$E3,H$2<=$F3,$E3<>"",$F3<>"")'],fill=PatternFill('solid',fgColor='6E9EC5')))
g.freeze_panes='H3';s.freeze_panes='E3'
g.print_options.horizontalCentered=False;g.sheet_properties.pageSetUpPr.fitToPage=True
g.page_setup.orientation='landscape';g.page_setup.paperSize=g.PAPERSIZE_A3;g.page_setup.fitToWidth=1;g.page_setup.fitToHeight=0
g.print_area='A1:AO70';g.print_title_rows='1:2'
s.print_area=f'A1:H{s.max_row}';s.print_title_rows='1:2'
s.sheet_properties.pageSetUpPr.fitToPage=True;s.page_setup.orientation='landscape';s.page_setup.fitToWidth=1;s.page_setup.fitToHeight=0

e=w.create_sheet('Emily Progress Evidence')
entries=[['Area','Evidence / remaining requirement'],
 ['As of','November 11, 2026; source workbook -4 preserved separately.'],
 ['Registry lifecycle','S4/S5 registered; S4 lease expired after 11.41 seconds; S5 stayed healthy. Local HTTP source test, not cloud.'],
 ['Immediate deregistration','Not implemented by the registry image. Explicit endpoint and returned descriptions require its owner. Service rows remain In Progress.'],
 ['Provider access','User confirms no Alpha Vantage key configured. No actual one-year dataset retrieved or live correctness confirmed.'],
 ['User-selected data','Symbols and dates are chosen per request. No fixed company list added.'],
 ['Tests','S4: 56; S5: 61 offline tests. Lifecycle local integration evidence attached.'],
 ['Documentation','Module/C&C packets complete; communication view complete. Other two quality views await Gordon/team.'],
 ['Shared tasks','Support slides, demo runbook, acceptance matrix and AI lessons draft are prepared. Rehearsal, GUI/cloud acceptance, final authorship review and submission are not performed.'],
 ['Other owners','Existing person assignments preserved. Unassigned tasks need team assignment. S2 registration and other claimed completions require owner confirmation.'],
 ['Dates','PR1 presentation October 22; PR2 submission November 12. November 11 internal targets are retained. Final-only acceptance has no invented final date.'],
 ['Change location','Old value','New value','Reason']]+changes
for row in entries:e.append(row)
for c in e[1]:c.fill=PatternFill('solid',fgColor='17365D');c.font=Font(color='FFFFFF',bold=True)
for row in e:
    for c in row:c.alignment=Alignment(wrap_text=True,vertical='top')
e.column_dimensions['A'].width=30;e.column_dimensions['B'].width=85;e.column_dimensions['C'].width=25;e.column_dimensions['D'].width=75
for row in range(2,e.max_row+1):e.row_dimensions[row].height=48
w.calculation=openpyxl.workbook.properties.CalcProperties(fullCalcOnLoad=True)
OUT.parent.mkdir(parents=True,exist_ok=True);w.save(OUT)
test=openpyxl.load_workbook(OUT)
assert len(test.sheetnames)==len(openpyxl.load_workbook(SOURCE).sheetnames)+1
assert test['Service Task List']['F53'].value=='Not Started'
assert test['Service Task List']['F83'].value=='Complete'
assert all(c.data_type!='e' for sh in test for row in sh for c in row)
print(OUT)
