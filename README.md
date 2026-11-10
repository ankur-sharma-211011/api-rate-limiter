# API Rate Limiter

A Python API rate-limiting project built with **FastAPI** and
**Memurai** (a Redis-compatible data store). It demonstrates four
commonly used rate-limiting algorithms and applies limits per client IP
address.

## Features

- Four rate-limiting strategies:
  - **Fixed Window**
  - **Sliding Window**
  - **Token Bucket**
  - **Leaky Bucket**
- FastAPI dependency-based request checking.
- Memurai/Redis-backed shared rate-limit state.
- Lua scripts execute each algorithm's Redis operations atomically.
- Configurable failure policies:
  - `fail_open`
  - `fail_closed`
  - `fallback_memory`
- A simple in-memory fallback limiter is provided for use when the
  data store is unavailable.

## Project structure

```text
.
├── main.py              # FastAPI application and endpoint configuration
├── rate_limiters.py     # Rate-limiting algorithms and Redis Lua scripts
├── redis_connection.py  # Memurai/Redis connection
├── fallback.py          # In-memory fallback limiter
├── requirements.txt      # Python dependencies
└── README.md
```

## Requirements

- Python 3.10 or later
- Memurai running locally or at a reachable Redis-compatible address
- Python packages listed in `requirements.txt`

## Setup

### 1. Clone the repository

```bash
git clone <your-repository-url>
cd <your-project-folder>
```

### 2. Create and activate a virtual environment

**Windows PowerShell:**

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**Linux/macOS:**

```bash
python -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Start Memurai

Start the Memurai service on your machine. The application currently
uses this default connection URL:

```text
redis://localhost:6379
```

You can override it with the `REDIS_URL` environment variable.

**Windows PowerShell:**

```powershell
$env:REDIS_URL = "redis://localhost:6379"
```

If the Memurai command-line client is installed and available on your
PATH, check the connection with:

```powershell
memurai-cli ping
```

A successful response is:

```text
PONG
```

If the command is not on PATH, use the Memurai installation directory or
check that the Memurai service is running through Windows Services.

### 5. Run the API

```bash
uvicorn main:app --reload
```

The API will normally be available at:

```text
http://127.0.0.1:8000
```

FastAPI's interactive API documentation is available at:

```text
http://127.0.0.1:8000/docs
```

## API endpoints

Each endpoint demonstrates a different rate-limiting algorithm.

---

Endpoint Algorithm Current configuration

---

`GET /fixed` Fixed Window 5 requests per 60
seconds

`GET /sliding` Sliding Window 5 requests per 60
seconds

`GET /token` Token Bucket Capacity 5; refill rate
5 tokens per 60 seconds

`GET /leaky` Leaky Bucket Capacity 5; leak rate 5
requests per 60 seconds

---

For example, open the following URL in a browser or send a request using
curl:

```bash
curl http://127.0.0.1:8000/fixed
```

When a request is accepted, the endpoint returns a success message. When
the configured limit is exceeded, the limiter raises HTTP **429 Too Many
Requests**.

## How the algorithms work

### 1. Fixed Window

Time is divided into fixed intervals. A counter is maintained for each
client IP and time window. Requests are accepted until the counter
exceeds the configured limit.

**Trade-off:** It is simple and efficient, but requests can bunch around
a window boundary. For example, a client may use its limit just before a
window resets and send another batch immediately after the reset.

### 2. Sliding Window

The limiter stores request timestamps in a sorted set. Before checking a
new request, it removes timestamps older than the configured time window
and counts the remaining requests.

**Benefit:** It provides a more accurate rolling-window limit and avoids
the fixed-window boundary burst.

### 3. Token Bucket

A bucket holds tokens up to a configured capacity. Each accepted request
consumes one token. Tokens are replenished over time at the configured
refill rate.

**Benefit:** It allows short bursts while controlling the average
request rate over time.

### 4. Leaky Bucket

The bucket tracks queued request load. Its stored amount decreases over
time at the configured leak rate. A new request is accepted only if
adding it does not exceed the bucket capacity.

**Benefit:** It smooths incoming traffic by limiting how quickly
requests can accumulate.

## Failure policies

The limiter code supports three policies for Redis connection or timeout
failures:

---

Policy Intended behavior

---

`fail_open` Allow the request if Redis is
unavailable.

`fail_closed` Reject the request with HTTP 503 if
Redis is unavailable.

`fallback_memory` Use the in-memory fallback limiter
if Redis is unavailable.

---

The current `main.py` configures all four limiters with:

```python
FAILURE_POLICY="fail_closed"
```

Therefore, the in-memory fallback is **not active by default**. To use
it, change the policy to:

```python
FAILURE_POLICY="fallback_memory"
```

The shared `MemoryFallback` instance currently has a limit of 10
requests per 60 seconds. It is a simplified emergency fallback, not an
exact replacement for each Redis-backed algorithm. Its state is local to
the Python process, so separate application workers do not share the
same fallback counters.

## Configuration

The current settings are defined in `main.py`:

```python
memory_fallback = MemoryFallback(limit=10, window=60)

fixed_limiter = FixedWindowLimiter(
    limit=5,
    window=60,
    fallback=memory_fallback.allow_request,
    FAILURE_POLICY="fail_closed"
)
```

The other limiter instances are configured there in the same way. Adjust
the limit, window, capacity, refill rate, leak rate, and failure policy
to experiment with different behaviors.

The Redis connection is configured in `redis_connection.py`. It reads
`REDIS_URL` from the environment and otherwise uses
`redis://localhost:6379`.

## Current implementation notes

- Client identification currently uses `request.client.host`.
  Forwarded IP headers are not trusted or processed by this
  implementation.
- The in-memory fallback is process-local and is not shared between
  multiple Uvicorn workers.
- The current fallback uses a fixed-window counter, even when the
  primary Redis limiter uses another algorithm.
- The Redis execution helper currently issues `WAIT 1 100` after the
  Lua script and requires at least one replica acknowledgement. A
  typical standalone Memurai instance has no replica, so this can
  cause requests to receive HTTP 503 even when Memurai is reachable.
  For a standalone local Memurai setup, remove the replication `WAIT`
  requirement (and execute the Lua script directly) unless you have
  deliberately configured a replica.
- The current fixed-window Lua script returns the request count, while
  the other three scripts return `1` or `0`. The fixed-window check
  uses that count to decide whether to reject the request.

These notes describe the uploaded implementation; they are not claims
that the application has been tested in every deployment configuration.

## Possible future improvements

- Add automated tests for limits, window boundaries, concurrency, and
  Redis failure behavior.
- Add trusted reverse-proxy support for deployments behind a known
  proxy.
- Add cleanup and monitoring for in-memory fallback state.
- Add configuration through environment variables rather than
  hard-coded limiter settings.
- Compare algorithm behavior under concurrent request loads.

## License

MIT License
