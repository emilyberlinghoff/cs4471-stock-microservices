# Emily's PR2 handoff

Prepared November 11, 2026. The editable and PDF outputs are in `output/pr2` at
the repository root. The original Downloads workbook is unchanged.

## Delivered

- Module and Component-and-Connector view packets, each with the five required
  documentation sections, diagrams and implemented/planned boundaries.
- Emily's Communication quality view, including request sequence, lease states,
  messages, rationale, failure behavior and acceptance evidence.
- Updated planning workbook, Gantt formatting, dependencies, per-service data
  scope labels, status rollups and evidence notes.
- Editable 14-slide support presentation with native diagrams, text at least
  20 pt and slide numbering. The other team quality views must be merged in.
- Demo runbook, proposed presenter handoffs, acceptance matrix, and an honest
  AI-assistance comparison/lessons draft.
- Local registry evidence: both services registered, S4 removed through lease
  expiry after 11.41 seconds, S5 remained registered and healthy.

Service work is on Microservice-4 and Microservice-5, with their existing PRs.
S4 has 56 and S5 has 61 passing offline tests. New service metadata, retry/renewal
behavior and graceful runners are documented in each branch's
`docs/registry-lifecycle.md`. The retrieval decision is documented separately.

## Pending external or human work

No provider key is configured: actual live access, one-year retrieval and live
completeness/correctness remain pending. User symbols and dates are request-driven;
no fixed stock list was added. The registry image has no immediate deregistration
endpoint and drops descriptions. Its owner must supply those features if needed.
Gordon's other quality views, real GUI/cloud acceptance, team review, human
rehearsal and OWL submission have not been completed by document generation.

The support slides are a review draft. The AI supplement does not invent a
student-authored baseline. The workbook marks only evidenced local work complete.
Unassigned tasks remain unassigned for the team to decide.

## Regenerate

Requires Python 3.11+, Pandoc, and `requirements-pr2-docs.txt`:

```sh
python -m pip install -r requirements-pr2-docs.txt
python tools/build_figures.py
python tools/update_plan.py /path/to/02_Services_Requirements_and_Project_Plan-4.xlsx
python tools/build_documents.py
```

Word/PDF text and tables were checked structurally. Representative rendered PDF
pages and the workbook table preview were visually inspected. The PowerPoint was
checked for slide bounds and minimum font size; open it in PowerPoint before
rehearsal because no Office/LibreOffice slide renderer is available here.

Check `delivery_manifest.json` for the service commits, file hashes and test
evidence. Shared tasks must not be marked complete until the human/team checks
in the acceptance matrix are actually performed.
