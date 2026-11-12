# S5 input validation and HTTP errors

Implements Service Task List **row 40**. Uses the existing comparison core and
Alpha Vantage integration. Registry lifecycle remains a separate task.

## Run and call

Install `requirements-s5.txt` and configure the API key as described in
[data source setup](s5-data-source.md). From the repository root:

```sh
python -m flask --app 's5_app:create_app()' run --port 5005
curl 'http://localhost:5005/comparison?symbols=MSFT,AAPL&start_date=2025-01-02&end_date=2025-12-31'
curl -X POST http://localhost:5005/comparison \
  -H 'Content-Type: application/json' \
  -d '{"symbols":["MSFT","SHOP.TRT"],"start_date":"2025-01-02","end_date":"2025-12-31","exchanges":{"SHOP.TRT":"TSX"}}'
curl http://localhost:5005/health
```

This starts a local development server, with debug mode off by default. A WSGI
deployment can use the same `s5_app:create_app()` factory. Production deadlines
and registry lifecycle remain deployment work.

`GET /comparison` accepts comma-separated symbols in query parameters, without a
body. `POST /comparison` requires a JSON object, without query parameters, and
an array of symbols. Per-stock calendar overrides are available through POST.
Successful results retain the existing core/source fields. `GET /health` returns
`{"status":"UP","service_id":"S5"}` without upstream requests; it reports process
health rather than provider availability.

| Field | Rule |
| --- | --- |
| `symbols` | Required 2–5 distinct symbols, trimmed and uppercased. Each symbol has 1–64 ASCII ticker characters: letter/digit/`^` initially, then letters/digits/`.`/`-`/`_`/`^`. No embedded spaces or commas. Duplicates after normalization are rejected. Existence is checked by the provider. |
| `start_date` | Required real calendar date exactly `YYYY-MM-DD`, no later than the server's request date. |
| `end_date` | Same format, on or after start date and no later than the request date. |
| `exchange` | Optional default exchange calendar, `NYSE` by default; non-empty string of at most 64 characters. |
| `exchanges` | Optional POST-only JSON object mapping requested symbols to calendar-name strings. Keys are normalized like symbols; unknown keys or normalization duplicates are rejected. Each calendar must be supported. |

Unknown fields, repeated GET parameters, mixed query/body inputs, malformed JSON,
and non-object bodies are rejected. Strings cannot replace the POST symbols
array, and null/number/boolean/array/object values cannot replace string fields.
Bodies are limited to 16 KiB. Validation happens before stock-data lookup. The
Python integration and CLI share argument validation. International/class-symbol
syntax is allowed; choose the actual exchange explicitly rather than assuming
the default fits every ticker.

## JSON error contract

```json
{
  "error": {
    "code": "INVALID_INPUT",
    "message": "Stock symbols must be distinct after normalization.",
    "field": "symbols"
  }
}
```

Every error has `code` and `message`. Validation errors include `field`;
stock-specific failures include the normalized `symbol` when applicable. Provider
text, credential-bearing exception URLs, and stack traces are excluded.
Unexpected exceptions produce generic errors and log only the exception class.

| HTTP status | Error codes |
| --- | --- |
| 400 | `INVALID_INPUT`, `BAD_REQUEST` for malformed/empty JSON |
| 404 | `UNKNOWN_SYMBOL`, `UNAVAILABLE_DATA`, `NOT_FOUND` for unknown routes |
| 405 | `METHOD_NOT_ALLOWED`, preserving the `Allow` header |
| 413 | `PAYLOAD_TOO_LARGE` |
| 415 | `UNSUPPORTED_MEDIA_TYPE` |
| 422 | `INSUFFICIENT_DATA` |
| 429 | `RATE_LIMITED` |
| 500 | `INTERNAL_ERROR` |
| 502 | `UPSTREAM_ERROR`, `INVALID_DATA` |
| 503 | `CONFIGURATION_ERROR` |
| 504 | `UPSTREAM_TIMEOUT` |

Any failed stock aborts the entire comparison: no partial ranking, fabricated
fallback, or substituted zero is returned. Complete data is required for every
expected session. The existing 12-second shared upstream wait budget remains;
it is not a hard process-level HTTP deadline. See the data-source guide for
running-worker cancellation and socket-timeout limits.

## Verification

```sh
python -m unittest discover -s tests -v
```

All 61 offline tests pass: 35 core/source tests, 15 HTTP tests, and 11 registry lifecycle tests. HTTP tests
exercise real comparisons with a mocked stock client, normalization, five-stock
requests, international symbols, dates/types/counts, mixed exchange overrides,
JSON parsing and body limits, error status mappings, safe internal errors,
missing/invalid prices without partial rankings, and recovery. Authenticated live
retrieval still requires an entitled key and is not verified here.
