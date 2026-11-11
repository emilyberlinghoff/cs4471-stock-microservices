# S2 — Stock Returns Microservice

A standalone Python service for calculating **daily stock returns in percentage points**
from Alpha Vantage's raw daily closing prices. The separate Python/Flask frontend calls
S2 over HTTP. S2 is not imported into or deployed with the frontend.

## Project files

| File | Purpose |
|---|---|
| `stock_returns.py` | Input validation, Alpha Vantage client, exchange-calendar coverage checks, pure return calculations |
| `app.py` | Independent Flask JSON API, health endpoint, registry metadata |
| `frontend_example.py` | Example of calling S2 from another Flask application via HTTP |
| `tests/` | Fixed-data tests for correctness, errors, and Flask route contracts |
| `openapi.yaml` | HTTP API contract for the frontend and other consumers |
| `Dockerfile` | Standalone container deployment |
| `.env.example` | Configuration example (never commit a real API key) |

## Requirements and assumptions

- Python 3.11+ is recommended.
- Get an API key from https://www.alphavantage.co/support/.
- By default, S2 assumes stocks trade on the **XNYS (New York Stock Exchange)** calendar,
  which is suitable for many US-listed stocks. Other calendars can be configured with
  `EXCHANGE_CALENDAR` (for example, `XTSE` for Toronto). **All symbols served by a single
  configured instance must follow that calendar.** To support stocks on multiple exchanges
  at once, add reliable symbol-to-exchange resolution or make the exchange explicit in
  your API contract. Using the wrong calendar produces false missing-day errors.
- Alpha Vantage's `TIME_SERIES_DAILY` gives **raw, unadjusted closes**. Stock splits and
  dividends are therefore not accounted for in returns.
- Alpha Vantage's **free** `outputsize=compact` gives only the *latest 100 observations*
  (not an arbitrary 100-day historical period). Full-length daily history needs a
  **premium** API key and `ALPHA_VANTAGE_OUTPUTSIZE=full`. If data cannot cover the selected
  interval, S2 rejects the calculation rather than interpolating missing prices.
- Dates mean local exchange dates. Today's session is included only after its scheduled
  close **plus** `DATA_AVAILABILITY_LAG_MINUTES` (default: 240 minutes). This allows
  current-date requests to have an earlier `effective_end_date` if data is not yet
  due. The lag is configurable for the Alpha Vantage publication schedule.

## Setup: local Python

```bash
cd s2_stock_returns
python -m venv .venv
source .venv/bin/activate             # On Windows: .venv\\Scripts\\activate
pip install -r requirements-dev.txt
export ALPHA_VANTAGE_API_KEY="your_actual_key"   # PowerShell: $env:ALPHA_VANTAGE_API_KEY="..."
export ALPHA_VANTAGE_OUTPUTSIZE="compact"        # Use full only with a premium key
python app.py
```

The microservice listens on `http://localhost:5001` by default.
Do **not** put the API key in source code or query parameters sent to S2.

### Call from the Flask frontend

Run S2 separately, then in the frontend's environment set:

```bash
export S2_URL="http://localhost:5001/api/v1/stock-returns"
python frontend_example.py
```

The example frontend listens on port 5000 and forwards requests to S2. In your actual
frontend, copy the small `requests.get(...)` integration and pass dates from the form.
In deployment, use an internal service URL such as `http://s2:5001/api/v1/stock-returns`.

## API

### GET `/api/v1/stock-returns`

All three query parameters are required:

- `symbol`: one stock symbol, e.g. `IBM`
- `start_date`: inclusive YYYY-MM-DD, e.g. `2026-01-05`
- `end_date`: inclusive YYYY-MM-DD, e.g. `2026-01-07`

```bash
curl "http://localhost:5001/api/v1/stock-returns?symbol=IBM&start_date=2026-01-05&end_date=2026-01-07"
```

### POST `/api/v1/stock-returns`

The same parameters can be submitted as a JSON object:

```bash
curl -X POST http://localhost:5001/api/v1/stock-returns \
  -H "Content-Type: application/json" \
  -d '{"symbol":"IBM","start_date":"2026-01-05","end_date":"2026-01-07"}'
```

### Success response (example using fixed test prices, **not** a live IBM quote)

For test closes `2026-01-05: 100`, `2026-01-06: 110`, `2026-01-07: 121`:

```json
{
  "service_id": "S2",
  "symbol": "IBM",
  "requested_start_date": "2026-01-05",
  "requested_end_date": "2026-01-07",
  "effective_start_date": "2026-01-05",
  "effective_end_date": "2026-01-07",
  "price_basis": "raw_close",
  "number_of_returns": 2,
  "returns": [
    {"date": "2026-01-06", "return_percent": 10.0},
    {"date": "2026-01-07", "return_percent": 10.0}
  ]
}
```

Formula for adjacent **trading-day** closes:

`return_percent(t) = (close(t) / close(t-1) - 1) * 100`

All math uses `Decimal` and percentages are rounded **once**, at the end, to four
places using `ROUND_HALF_UP`. JSON values are numeric; insignificant trailing zeros
(e.g. `10.0000`) may be represented as `10.0`.

### Error response (example)

HTTP `422 Unprocessable Entity`:

```json
{
  "error": {
    "code": "INCOMPLETE_DATA",
    "message": "Missing trading-day closing prices for IBM: 2026-01-06."
  }
}
```

Common error codes and statuses:

| HTTP | Code | Meaning |
|---|---|---|
| 400 | `MISSING_INPUT` / `INVALID_DATE` / `INVALID_DATE_RANGE` / `FUTURE_DATE` / `INVALID_SYMBOL` / `INVALID_INPUT` | Bad client input |
| 404 | `UNKNOWN_SYMBOL` | Alpha Vantage specifically identifies an unrecognized symbol |
| 422 | `INSUFFICIENT_DATA` | Fewer than two completed usable observations |
| 422 | `INCOMPLETE_DATA` | Expected exchange sessions lack prices |
| 422 | `INVALID_PRICE` | Non-positive, missing, non-finite or unusable close |
| 422 | `CALENDAR_UNAVAILABLE` | Exchange calendar does not cover chosen period |
| 503 | `DATA_UNAVAILABLE` / `HISTORY_UNAVAILABLE` | Daily data absent or requires upgraded historical access |
| 503 | `UPSTREAM_RATE_LIMIT` | Alpha Vantage quota hit |
| 502 | `UPSTREAM_FAILURE` | Alpha Vantage HTTP/transport/malformed response problem |
| 504 | `UPSTREAM_TIMEOUT` | Alpha Vantage timed out |
| 503 | `CONFIGURATION_ERROR` | API key missing |

S2 does **not** return `0` in place of unavailable data. Genuine zero returns are allowed.

### Service discovery and health

- `GET /health` yields `{"status":"ok","service_id":"S2"}`. This is a **liveness**
  check and does not require Alpha Vantage to be responsive.
- `GET /service-info` provides `{id, title, description, url}` for the **shared**
  registry registration mechanism. Set `SERVICE_PUBLIC_URL` to the address the registry
  should publish. **This endpoint does not register itself.** The group must connect the
  metadata to the agreed registration/removal mechanism to fully satisfy FR8.2 and FR9.
- Removing S2 from the registry must be performed by the shared mechanism. Removing
  its independent process/container must not change other stock-service APIs.

## Tests

```bash
python -m pytest -q
```

Tests use in-memory, fixed price datasets and fake upstream responses: no paid API key
is needed. They cover calculation, four-decimal rounding, holiday/weekend gaps,
insufficient data, unknown symbols, simulated timeouts and subsequent recovery,
validation, JSON routes, and a 100-request microbenchmark with 300 prices.

**Performance and deployment acceptance:** QR1 must be re-measured on the actual
chosen cloud platform (the included benchmark is only an indicative local check).
QR2 must be verified using timed network-failure injection and actual deployment
configuration (request handler, ingress, reverse proxy and process timeout). This
implementation uses short upstream timeouts and at most one transient retry to aim
for the 15-second deadline, but a synchronous HTTP client cannot guarantee a hard
15-second wall-clock limit if a peer continuously trickles data or the platform
stalls. QR4 and QR5 require a multi-service integration test against the group's
real registry and other services.

## Docker (independent deployment)

```bash
docker build -t stock-returns-s2 .
docker run --rm --name stock-returns-s2 -p 5001:5001 \
  --env-file .env stock-returns-s2
```

Copy `.env.example` to `.env`, replace the API key, and set the public service URL
before starting. The independent container can be stopped, replaced, or redeployed
without rebuilding or restarting other stock services. Production deployments
should add health monitoring, log collection, a secret store for the API key and
an ingress with an explicit request deadline.
