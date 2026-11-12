# Preliminary demo runbook and acceptance record

Group 11 · PR2 November 12, 2026 · Prepared by Emily · Team rehearsal pending.

## Proposed run of show (confirm with the team)

| Presenter | Segment | Evidence and handoff |
| --- | --- | --- |
| Gordon | Scope, consumer GUI and service discovery | Show real registry lookup/navigation only if connected; label existing simulated data. |
| Max | S2 API and stock-return calculation | Use its documented endpoint and tests; current branch audit passed 39 tests. |
| Emily | Module/C&C/communication views; S4/S5 validation and calculation | Explain source boundaries, demonstrate invalid inputs and show offline numerical tests. |
| Aashka | Registry, leases, deployment and S3 | Demonstrate actual registry behavior; disclose open S3 review issues and cloud state. |

This is a proposal, not confirmation that team members rehearsed or accepted their
segments. Measure presentation time once the instructor's allotted duration is
confirmed. Keep a local PDF/slide copy and test outputs as a fallback.

## Safe local sequence

1. Record the exact commits for the demonstrated branches. Use separate worktrees
   or processes from independent checkouts; do not switch files under a running server.
2. Install each branch's requirements in a virtual environment. Run the offline
   suites first. Current new-code results: S4 56, S5 61 tests passing.
3. Start S4 on port 5004 with `python s4_server.py` and S5 on port 5005 with
   `python s5_server.py`. Without REGISTRY_URLS, each API runs independently.
4. Show /health (200), /service-info (metadata), a missing-input request (400),
   and an invalid date or duplicate S5 symbol request (400). These need no key.
5. Explain successful numerical calculations using the fixed test datasets. Do not
   describe mocked prices as real market observations.
6. To show real provider results, configure an entitled ALPHA_VANTAGE_API_KEY in
   the server terminal and restart. Full history needs premium access; no actual
   key is configured yet. User-selected symbols and dates are the request inputs.
7. To show leases, start the team's registry image in Docker (Docker must be
   running), set REGISTRY_URLS and SERVICE_PUBLIC_URL for each service, then
   restart both service runners. Inspect GET /services for S4 and S5.
8. Stop S4 with Control+C. Wait for lease expiry (roughly 12 seconds after its last
   renewal). Confirm S4 disappears and S5 still returns health 200. Explain that
   the current registry has no immediate deregistration API.
9. Show browser discovery/invocation only after GUI integration has been verified.
   A label-only failover toggle is not an actual automatic failover demonstration.

Example local registry setup, using the team's image:

```sh
docker run --rm --name pr2-registry -p 5000:5000 aashkaaa/stock-registry:latest
```

In each service terminal, before starting the runner:

```sh
export REGISTRY_URLS='http://localhost:5000'
# Use 5005 for S5; deployed URLs must be reachable by consumers.
export SERVICE_PUBLIC_URL='http://localhost:5004'
```

## Acceptance matrix

| Check | Expected | Current evidence / status |
| --- | --- | --- |
| S4 invalid dates/missing input | JSON 400 before provider calls | Automated tests passed. |
| S5 duplicate/bad symbols | JSON 400 without partial ranking | Automated tests passed. |
| S4 20/50-session means | Match fixed reference, round only final output | Automated tests passed. |
| S5 ranking/ties/common dates | Unrounded ranking, deterministic ties, correct shared endpoints | Automated tests passed. |
| Provider failures | Explicit rate-limit/timeout/error; later valid request succeeds | Mocked recovery tests passed. Live failure injection pending. |
| Registry source integration | Both services visible, S4 removal leaves S5 healthy | Local real HTTP test passed; 11.41-second removal observed. |
| Provider live access | Valid authenticated response for selected symbol | Pending: user has no key configured. |
| One-year completeness | Every expected session validated for the selected run | Pending: entitled key and actual run. |
| Discovery descriptions | Name, description, URL present | Registry currently drops descriptions; owner fix pending. |
| Immediate shutdown deregistration | Explicit agreed deletion if required | Not supported by current image; lease expiry is implemented. |
| Consumer GUI end to end | Discovery to service to actual displayed result | Pending team integration. |
| Cloud independent deployment | Published URLs and isolation under removal | Pending cloud-owner evidence. Local evidence does not establish this. |
| Three quality views | Templates and behavior models for all three | Emily communication packet prepared; other two await Gordon/team. |
| Human rehearsal / final acceptance | Timed run and recorded outcomes | Not performed by document generation. |

## Known remaining actions and fallback

For a key/quota failure, show the honest structured error and the offline tests.
For unavailable Docker/cloud, show the recorded local registry evidence and state
the environment it used. Use the diagrams to explain intended integrations, with
dashed links labelled planned. Do not mark a deployment or live-data task complete
from a screenshot of an isolated health endpoint.

Before submission, merge the team's other quality views and latest GUI/cloud
evidence, confirm each presenter, rehearse, update the workbook statuses, and
verify the actual OWL cutoff. No OWL submission or human rehearsal is automated here.
