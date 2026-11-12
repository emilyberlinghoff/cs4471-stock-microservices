# S4 input validation and HTTP errors

Implements Service Task List **row 34**, using the existing calculation core
and Alpha Vantage integration. Registry lifecycle remains a separate task.

## Run and call the API

Install `requirements-s4.txt` and configure Alpha Vantage as described in
[data source setup](s4-data-source.md). From the repository root:

```sh
python -m flask --app 's4_app:create_app()' run --port 5004
```

This is a local development server; debug mode is off by default. A WSGI
deployment can use the same `s4_app:create_app()` factory. Hard HTTP deadlines
and registry lifecycle remain deployment work.

```sh
curl 'http://localhost:5004/moving-averages?symbol=MSFT&start_date=2025-01-02&end_date=2025-12-31'
curl -X POST http://localhost:5004/moving-averages \
  -H 'Content-Type: application/json' \
  -d '{"symbol":"MSFT","start_date":"2025-01-02","end_date":"2025-12-31","exchange":"NYSE"}'
curl http://localhost:5004/health
```

GET uses query parameters without a body; POST uses a JSON object without query
parameters. Successful responses retain the existing calculation/source fields.
`GET /health` returns `{"status":"UP","service_id":"S4"}` without a provider call;
it reports process health, not provider availability.

| Field | Rule |
| --- | --- |
| `symbol` | Required single stock string, trimmed and uppercased; 1–64 ASCII characters. Starts with a letter, digit, or `^`; subsequent characters may also include `.`, `-`, or `_`. International suffixes and class symbols are accepted; spaces and commas are rejected. Existence is checked by the provider. |
| `start_date` | Required real calendar date, exactly `YYYY-MM-DD`, no later than the server's request date. |
| `end_date` | Same format, on or after start date and no later than the request date. |
| `exchange` | Optional supported calendar name, default `NYSE`; trimmed, non-empty string of at most 64 characters. Select the actual exchange explicitly. |

Unknown fields and repeated GET parameters are rejected. Nulls, numbers, arrays,
and objects cannot substitute for string fields. POST requires a JSON media type;
malformed JSON and non-object bodies are rejected. Bodies are limited to 16 KiB.
Validation failures make no stock-data requests. Argument checks also apply to
the Python integration and CLI.

## Error contract

```json
{
  "error": {
    "code": "INVALID_INPUT",
    "message": "end_date must be on or after start_date.",
    "field": "end_date",
    "symbol": "MSFT"
  }
}
```

Every error contains `code` and `message`. Validation errors include `field`;
`symbol` is included when available and relevant. Provider text, exception URLs,
and stack traces are excluded. Unexpected failures return a generic JSON error
and log only the exception class.

| HTTP status | Error code |
| --- | --- |
| 400 | `INVALID_INPUT`, `BAD_REQUEST` for malformed/empty JSON |
| 404 | `UNKNOWN_SYMBOL`, `UNAVAILABLE_DATA`, `NOT_FOUND` for an unknown route |
| 405 | `METHOD_NOT_ALLOWED`, preserving the `Allow` header |
| 413 | `PAYLOAD_TOO_LARGE` |
| 415 | `UNSUPPORTED_MEDIA_TYPE` |
| 422 | `INSUFFICIENT_DATA` |
| 429 | `RATE_LIMITED` |
| 500 | `INTERNAL_ERROR` |
| 502 | `UPSTREAM_ERROR`, `INVALID_DATA` |
| 503 | `CONFIGURATION_ERROR` |
| 504 | `UPSTREAM_TIMEOUT` |

Partially available series return 200, retaining valid averages and null plus a
reason for incomplete windows. No valid moving-average window anywhere returns
422. Zero or fabricated results never substitute for missing data.

## Verification

```sh
python -m unittest discover -s tests -v
```

All 56 offline tests pass: 30 calculation/source tests, 15 HTTP tests, and 11 registry lifecycle tests. Flask's
test client exercises real S4 calculations with a mocked stock client, including
normalization, types, dates, international symbol syntax, calendars, ambiguous
requests, JSON parsing, body limits, status mappings, framework errors, safe
internal failures, recovery, and partial windows. Authenticated live retrieval
still needs an entitled API key and is not verified here.
