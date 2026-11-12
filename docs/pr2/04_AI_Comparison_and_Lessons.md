# AI assistance comparison and lessons learned — review draft

Prepared for task 6.22. This records the assistance actually used; it does not
invent an independently authored student solution or claim a rehearsal occurred.
The team must review its course AI rules and finalize its own reflection.

| Work item | Student/team starting point | AI-assisted result | Comparison / limitation |
| --- | --- | --- | --- |
| S4/S5 algorithms | User supplied service definitions and requirements; no independently written baseline implementation supplied. | Calculation modules, API/source adapters, validation and tests prepared in requested branches. | Compare against specified formulas and fixed independent references, not invented manual work. |
| Provider access | Team selected Alpha Vantage; user has no key configured. | Request-driven retrieval, explicit compact/full coverage and credential-safe failures. | Code/test completion is different from successful authenticated retrieval. No one-year live dataset claimed. |
| Registry lifecycle | Team image and S3 client existed; delete contract was undocumented. | Image source inspected read-only; lease client registers/renews both registries and stops on shutdown. | Real local test verifies removal/isolation; immediate deletion and description retention remain upstream work. |
| Architecture packets | Team workbook and project brief specified views; current branches were separate. | Module, C&C and communication packets with diagrams, catalogue, context, variability, rationale and limitations. | Team review is needed to confirm its design intent; implemented/planned links are deliberately distinguished. |
| Planning | Workbook contained duplicated-looking data blocks and conflicting summary statuses. | Per-service scope labels, evidence notes, rollups, dependencies and complete chart rules in a copy. | Existing owners retained; unverified live/cloud/rehearsal work is not marked complete. |
| PR review | S3 branch included failure paths and simulated fallback values. | Reproduced failures and submitted changes-requested review. | Passing a normal request is not sufficient evidence for safe failure behavior. |

## Lessons supported by this work

1. Test errors and insufficient observations, not only normal data. Independent
   fixtures expose denominator, missing-session and rounding mistakes.
2. Inspect the actual integration contract. An assumed deregistration endpoint
   would have been wrong for the published registry image.
3. Separate different evidence levels: source inspection, unit tests, real local
   HTTP tests, authenticated provider access and cloud GUI acceptance.
4. Keep credentials out of commits, exception strings and generated artifacts.
5. AI-generated diagrams must be checked against source branches; planned edges
   and missing components should remain visible rather than implied complete.

## Team completion fields

Add each member's own comparison against any independently authored solution,
their actual edits, and their own lessons. Confirm reference/AI disclosure rules
with the course instructions. This draft does not substitute for that reflection.
