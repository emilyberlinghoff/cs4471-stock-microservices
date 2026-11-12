# cs4471-stock-microservices
A microservices-based stock analysis application developed for CS4471 Software Architectures at Western University.

## Microservice 5 — Stock Comparison

Compares 2–5 stocks over common trading dates and ranks percentage price changes.
Follow these terminal steps from the repository root. Commands use Python 3.11;
install it if `python3.11` is unavailable. Python 3.10+ is supported.

### 1. Select the branch and install dependencies

Stop any running service with **Control+C** before switching branches. Save or
commit unrelated edits first. S4 and S5 currently live on separate branches;
these instructions run one service at a time in this checkout.

```sh
git switch Microservice-5
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-s5.txt
```

Create the environment once. On later visits, activate it with
`source .venv/bin/activate` and install this branch's requirements.

### 2. Run automated tests — no API key needed

```sh
python -m unittest discover -s tests -v
```

Expected: **61 tests**, ending with `OK`. Tests use synthetic prices and mocked
provider requests, including comparisons, concurrent lookups, and error cases.

### 3. Configure real stock data (optional for health/validation testing)

Set these variables in the **same terminal that will start Flask**, before
starting it:

```sh
export ALPHA_VANTAGE_API_KEY='your-own-key'
export ALPHA_VANTAGE_OUTPUTSIZE=full
```

Get your own key from [Alpha Vantage](https://www.alphavantage.co/support/#api-key).
Full historical data requires a premium key. With a free key, use:

```sh
export ALPHA_VANTAGE_OUTPUTSIZE=compact
```

Compact supplies only the latest 100 trading observations. Use a recent interval
covered by **every requested stock**. Missing coverage produces an explicit
error instead of a shortened comparison. A one-year historical request requires
full access. Each comparison consumes 2–5 provider requests, one per stock, so
repeated live tests can exhaust your quota. See the
[provider documentation](https://www.alphavantage.co/documentation/#daily).

`.env.example` lists configuration names; `.env` files are **not loaded
automatically**. Export variables explicitly and keep real keys out of Git.
Restart Flask after changing its environment variables.

### 4. Start the HTTP service

```sh
python -m flask --app 's5_app:create_app()' run --port 5005
```

Keep this terminal open. Flask's development-server message is expected locally.
Open these URLs in a browser, or use `curl` in a **second terminal**:

```sh
curl -i 'http://localhost:5005/health'
curl -i 'http://localhost:5005/comparison'
curl -i 'http://localhost:5005/comparison?symbols=MSFT,MSFT&start_date=2025-01-02&end_date=2025-01-31'
```

Expected results:

- `/health`: **200**, with `status: UP` and `service_id: S5`. This checks the
  process, not live provider availability.
- Missing fields: **400**, with a JSON `INVALID_INPUT` error.
- Duplicate symbols: **400**, identifying `symbols` as invalid.
- A browser request for `/favicon.ico` may return **404** because no tab icon
  is provided; this does not affect the API.

These checks work without an API key.

### 5. Request a real stock comparison

With a key entitled to full historical data, try:

```sh
curl -i 'http://localhost:5005/comparison?symbols=MSFT,AAPL&start_date=2025-01-02&end_date=2025-01-31'
```

POST uses a JSON array of symbols:

```sh
curl -i -X POST http://localhost:5005/comparison \
  -H 'Content-Type: application/json' \
  -d '{"symbols":["MSFT","AAPL"],"start_date":"2025-01-02","end_date":"2025-01-31","exchange":"NYSE"}'
```

For compact/free access, replace the example dates with a covered recent range.
Successful JSON includes common effective dates and a `ranking` ordered by
percentage price change. If any stock fails or has unusable data, the response
contains an error and no partial ranking. A missing key returns **503**; quota
exhaustion returns **429**. POST supports per-symbol `exchanges` overrides for
mixed exchanges; select the stocks' actual calendars. See the
[S5 API contract](docs/s5-api.md) for examples and error codes.

For a direct CLI comparison with the configured key:

```sh
python s5_service.py MSFT,AAPL 2025-01-02 2025-01-31 --exchange NYSE
```

### Stop or switch services

Press **Control+C** in the server terminal before switching to `Microservice-4`.
Activate `.venv` in each new terminal where you run Python commands. A
`ModuleNotFoundError` usually means the environment is inactive, the branch is
incorrect, or that branch's requirements have not been installed.

More details: [data source integration](docs/s5-data-source.md) and
[HTTP API contract](docs/s5-api.md). Authenticated live retrieval still requires
your own entitled key; automated tests verify behavior with mocked data.

## Registry lifecycle

See [registration and shutdown](docs/registry-lifecycle.md) for startup leases,
primary/backup configuration, the graceful `s5_server.py` runner, and
the current registry’s lease-expiry removal limitation.
