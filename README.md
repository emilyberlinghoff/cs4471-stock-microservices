# cs4471-stock-microservices
A microservices-based stock analysis application developed for CS4471 Software Architectures at Western University.

## Microservice 4 — Moving Averages

Calculates 20- and 50-trading-day simple moving averages. Follow these steps in
your terminal from the repository root. Commands use Python 3.11; install it if
`python3.11` is unavailable. Python 3.10+ is supported.

### 1. Select the branch and install dependencies

Stop any running service with **Control+C** before switching branches. Save or
commit unrelated edits first. S4 and S5 currently live on separate branches;
these instructions run one service at a time in this checkout.

```sh
git switch Microservice-4
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-s4.txt
```

Create the virtual environment once. On later visits, activate it with
`source .venv/bin/activate` and install this branch's requirements.

### 2. Run automated tests — no API key needed

```sh
python -m unittest discover -s tests -v
```

Expected: **56 tests**, ending with `OK`. These tests use synthetic prices and
mocked provider requests, including normal calculations and error cases.

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

Compact mode supplies only the latest 100 trading observations. Select a recent
request interval whose **49 preceding trading sessions** are also covered for
the initial 50-day average. Insufficient compact history produces an explicit
error. A one-year historical request requires full access. See the
[provider documentation](https://www.alphavantage.co/documentation/#daily).

The `.env.example` file lists configuration names; `.env` files are **not loaded
automatically**. Export variables explicitly and keep real keys out of Git.
Restart Flask after changing its environment variables.

### 4. Start the HTTP service

```sh
python -m flask --app 's4_app:create_app()' run --port 5004
```

Keep this terminal open. Flask's development-server message is expected during
local testing. Open the following URLs in your browser, or run the `curl`
commands in a **second terminal**:

```sh
curl -i 'http://localhost:5004/health'
curl -i 'http://localhost:5004/moving-averages'
curl -i 'http://localhost:5004/moving-averages?symbol=MSFT&start_date=2025-02-30&end_date=2025-03-10'
```

Expected results:

- `/health`: **200**, with `status: UP` and `service_id: S4`. This checks the
  service process; it does not confirm live provider access.
- Missing fields: **400**, with a JSON `INVALID_INPUT` error.
- February 30: **400**, identifying `start_date` as invalid.
- A browser request for `/favicon.ico` may return **404** because no tab icon
  is provided; this does not affect the API.

These checks work without an API key.

### 5. Request real moving averages

With a key entitled to full historical data, try:

```sh
curl -i 'http://localhost:5004/moving-averages?symbol=MSFT&start_date=2025-01-02&end_date=2025-01-31'
```

POST accepts the same inputs as a JSON object:

```sh
curl -i -X POST http://localhost:5004/moving-averages \
  -H 'Content-Type: application/json' \
  -d '{"symbol":"MSFT","start_date":"2025-01-02","end_date":"2025-01-31","exchange":"NYSE"}'
```

For compact/free access, replace these example dates with a covered recent
interval. Successful JSON includes dated `sma_20` and `sma_50` values. Incomplete
windows have null values and reasons. A missing key returns **503**; quota
exhaustion returns **429**. Full error codes and payloads are documented in the
[S4 API contract](docs/s4-api.md).

For a direct CLI calculation with the configured key:

```sh
python s4_service.py MSFT 2025-01-02 2025-01-31 --exchange NYSE
```

### Stop or switch services

Press **Control+C** in the server terminal before switching to `Microservice-5`.
Activate `.venv` in each new terminal where you run Python commands. A
`ModuleNotFoundError` usually means the environment is inactive, the branch is
incorrect, or that branch's requirements have not been installed.

More details: [data source integration](docs/s4-data-source.md) and
[HTTP API contract](docs/s4-api.md). Authenticated live retrieval still requires
your own entitled key; the automated tests verify behavior with mocked data.

## Registry lifecycle

See [registration and shutdown](docs/registry-lifecycle.md) for startup leases,
primary/backup configuration, the graceful `s4_server.py` runner, and
the current registry’s lease-expiry removal limitation.
