<div align="center">

# ⚡ TaskForge

### A production-ready distributed task queue built with FastAPI, Celery, and Redis

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Celery](https://img.shields.io/badge/Celery-5.5-37814A?style=flat&logo=celery&logoColor=white)](https://docs.celeryq.dev/)
[![Redis](https://img.shields.io/badge/Redis-7-DC382D?style=flat&logo=redis&logoColor=white)](https://redis.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow?style=flat)](LICENSE)

</div>

---

TaskForge is a full-stack distributed task queue system that offloads time-intensive background jobs from your main application thread, keeping your API fast and responsive. It ships with a modern, real-time web dashboard for submitting and monitoring tasks, JWT-authenticated REST endpoints, priority task queues, and Celery signal-based database persistence — so task results are written the moment a worker finishes, not only when a client polls.

**The problem it solves:** Synchronous web servers block on long-running work (image processing, ML inference, report generation). TaskForge routes those jobs to isolated worker processes via a persistent message broker, decoupling request handling from computation time.

---

## Table of Contents

1. [Key Features](#key-features)
2. [Architecture Overview](#architecture-overview)
3. [Tech Stack](#tech-stack)
4. [Getting Started](#getting-started)
   - [Prerequisites](#prerequisites)
   - [Installation](#installation)
   - [Configuration](#configuration)
5. [Running the Project](#running-the-project)
6. [Usage](#usage)
   - [Web Dashboard](#web-dashboard)
   - [REST API Examples](#rest-api-examples)
7. [API Reference](#api-reference)
8. [Monitoring with Flower](#monitoring-with-flower)
9. [Testing](#testing)
10. [Security Considerations](#security-considerations)
11. [Contributing](#contributing)
12. [License](#license)

---

## Key Features

- 🚀 **Async FastAPI backend** with JWT Bearer authentication and per-IP rate limiting
- ⚙️ **Celery workers** with priority queues (`default`, `high_priority`) and late acknowledgment for fault tolerance
- 🗄️ **SQLite persistence** — task results are written directly via Celery signals the instant a worker finishes, independent of client polling
- 🔄 **Auto-polling dashboard** — the web UI polls task status every 2 seconds and stops automatically on terminal state (SUCCESS / FAILURE / REVOKED)
- 🛡️ **Proxy-aware rate limiting** — correctly resolves real client IPs behind Nginx, Cloudflare, or any reverse proxy
- 📊 **Flower integration** for real-time worker and task monitoring
- 🌱 **12-Factor App config** — all secrets and URLs are read from environment variables
- 🔁 **Exponential-backoff retries** for transient infrastructure failures

---

## Architecture Overview

```
Browser / API Client
        │
        ▼
 ┌─────────────┐   JWT Auth    ┌──────────────┐
 │  FastAPI    │──────────────▶│  SQLite DB   │
 │  (main.py)  │               │ tasks_and_   │
 └──────┬──────┘               │  users.db    │
        │ task.delay()         └──────▲───────┘
        ▼                             │ Celery signals
 ┌─────────────┐               ┌──────┴───────┐
 │    Redis    │◀─────────────▶│  Celery      │
 │  (Broker +  │               │  Worker(s)   │
 │   Backend)  │               │ (celery_app) │
 └─────────────┘               └─────────────┘
```

1. A client authenticates via `POST /token` and receives a short-lived JWT.
2. The client submits a task via one of the task endpoints (rate-limited to 5/min per IP).
3. FastAPI enqueues the job via `task.delay()` and records it in SQLite as `SUBMITTED`.
4. A Celery worker picks up the job from Redis, executes it, and fires a `task_success` or `task_failure` signal that **immediately** updates the SQLite record.
5. The client's dashboard auto-polls `/tasks/{task_id}` and displays the live result.

---

## Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| **API Framework** | [FastAPI](https://fastapi.tiangolo.com/) 0.115 | Async HTTP endpoints, OpenAPI docs |
| **Task Queue** | [Celery](https://docs.celeryq.dev/) 5.5 | Background job dispatch and execution |
| **Message Broker** | [Redis](https://redis.io/) 7 | Task queue transport and result backend |
| **Database** | [SQLite](https://www.sqlite.org/) + [aiosqlite](https://github.com/omnilib/aiosqlite) | Async task and user persistence |
| **Authentication** | [python-jose](https://python-jose.readthedocs.io/) + [passlib](https://passlib.readthedocs.io/) | JWT tokens, bcrypt password hashing |
| **Rate Limiting** | [SlowAPI](https://github.com/laurentS/slowapi) | Per-IP request throttling |
| **Monitoring** | [Flower](https://flower.readthedocs.io/) | Real-time Celery dashboard |
| **Server** | [Uvicorn](https://www.uvicorn.org/) | ASGI production server |

---

## Getting Started

### Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.12+ | [python.org](https://www.python.org/downloads/) — check "Add Python to PATH" on Windows |
| Docker Desktop | Latest | [docker.com](https://www.docker.com/products/docker-desktop/) — used to run Redis |
| Git | Any | [git-scm.com](https://git-scm.com/) |

### Installation

**1. Clone the repository**

```bash
git clone https://github.com/dhaatrik/distributed-task-queue.git
cd distributed-task-queue
```

**2. Start Redis via Docker**

```bash
docker run -d -p 6379:6379 --name redis-server redis
```

Verify it's running:

```bash
docker ps
# redis-server should appear in the list
```

**3. Create and activate a virtual environment**

```bash
# Windows
python -m venv .venv
.\.venv\Scripts\activate

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
```

**4. Install dependencies**

```bash
pip install -r requirements.txt
```

### Configuration

Copy the example environment file and fill in any values you want to override:

```bash
cp .env.example .env
```

| Variable | Default | Required in Production |
|---|---|---|
| `APP_SECRET_KEY` | *(auto-generated — invalidated on restart)* | ✅ Yes — use `openssl rand -hex 32` |
| `DATABASE_URL` | `tasks_and_users.db` | Optional |
| `CELERY_BROKER_URL` | `redis://localhost:6379/0` | Optional |
| `CELERY_RESULT_BACKEND` | `redis://localhost:6379/0` | Optional |

> [!WARNING]
> Do not run in production without setting `APP_SECRET_KEY`. Without it, a new random key is generated on every startup, invalidating all existing JWT tokens.

---

## Running the Project

You need **four** terminal sessions. Activate your virtual environment (`.\.venv\Scripts\activate`) in each one.

**Terminal 1 — Default queue worker**

```bash
celery -A celery_app worker -Q default --loglevel=info --pool=solo
```

**Terminal 2 — High-priority queue worker**

```bash
celery -A celery_app worker -Q high_priority --loglevel=info --pool=solo
```

> [!NOTE]
> `--pool=solo` is required on Windows because the default `prefork` pool is not supported. On Linux/macOS you can omit it or use `--pool=prefork`.

**Terminal 3 — FastAPI server**

```bash
uvicorn main:app --reload
```

The server starts at **http://127.0.0.1:8000**. The database and default test user are created automatically on first startup.

**Terminal 4 — Flower (optional monitoring)**

```bash
celery -A celery_app flower
```

Flower dashboard: **http://localhost:5555**

**Stopping everything**

```bash
# Press Ctrl+C in each worker/server terminal, then:
docker stop redis-server
```

---

## Usage

### Web Dashboard

Navigate to **http://127.0.0.1:8000** in your browser.

The dashboard provides three bento-style panels:

| Panel | Description |
|---|---|
| **Process Task** | Submit a generic long-running job (~5 s) |
| **Add Numbers** | Submit a summation job over a list of floats |
| **Image Processing** | Simulate an image processing pipeline (~1 s) |
| **Task Monitor** | Auto-polls every 2 s and displays live status + result |

Sign in with the default test credentials:

```
Username: user1
Password: password1
```

### REST API Examples

The interactive API documentation is available at **http://127.0.0.1:8000/docs**.

**Step 1 — Authenticate and obtain a token**

```powershell
# PowerShell
$response = (Invoke-WebRequest -Uri "http://localhost:8000/token" `
    -Method POST `
    -Headers @{ "Content-Type" = "application/x-www-form-urlencoded" } `
    -Body "username=user1&password=password1").Content | ConvertFrom-Json

$TOKEN = $response.access_token
```

```bash
# bash / curl
TOKEN=$(curl -s -X POST "http://localhost:8000/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=user1&password=password1" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
```

**Step 2 — Submit a task**

```powershell
# Generic process task (PowerShell)
$task = (Invoke-WebRequest -Uri "http://localhost:8000/tasks/process" `
    -Method POST `
    -Headers @{ "Authorization" = "Bearer $TOKEN"; "Content-Type" = "application/json" } `
    -Body '{"data": "hello world"}').Content | ConvertFrom-Json

$TASK_ID = $task.task_id
```

```bash
# Add numbers task (bash)
TASK_ID=$(curl -s -X POST "http://localhost:8000/tasks/process-numbers" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"numbers": [1, 2, 3.5, 10]}' | python3 -c "import sys,json; print(json.load(sys.stdin)['task_id'])")
```

**Step 3 — Poll task status**

```powershell
# PowerShell
(Invoke-WebRequest -Uri "http://localhost:8000/tasks/$TASK_ID" `
    -Headers @{ "Authorization" = "Bearer $TOKEN" }).Content | ConvertFrom-Json
```

```bash
# bash
curl -s "http://localhost:8000/tasks/$TASK_ID" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

**Example success response:**

```json
{
    "task_id": "3b6a1e2d-...",
    "name": "add_numbers",
    "status": "SUCCESS",
    "result": "16.5",
    "created_at": "2026-04-15T03:00:00.000000",
    "completed_at": "2026-04-15T03:00:00.412381"
}
```

---

## API Reference

All task endpoints require a `Authorization: Bearer <token>` header.

| Method | Endpoint | Auth | Rate Limit | Description |
|---|---|---|---|---|
| `POST` | `/token` | ❌ | — | Exchange credentials for a JWT |
| `GET` | `/` | ❌ | — | Serve the web dashboard |
| `POST` | `/tasks/process` | ✅ | 5/min | Submit a generic processing task |
| `POST` | `/tasks/process-numbers` | ✅ | 5/min | Submit a number summation task |
| `POST` | `/tasks/process-image` | ✅ | 5/min | Submit an image processing task |
| `GET` | `/tasks/{task_id}` | ✅ | — | Fetch the current status and result of a task |

**Request bodies:**

```jsonc
// POST /tasks/process
{ "data": "any string payload" }

// POST /tasks/process-numbers
{ "numbers": [1, 2, 3.5, 10] }

// POST /tasks/process-image
{ "image_id": "photo_001.jpg" }
```

**Task status values:** `SUBMITTED` → `STARTED` → `SUCCESS` | `FAILURE` | `REVOKED`

---

## Monitoring with Flower

Flower provides a real-time browser dashboard for your Celery cluster.

```bash
celery -A celery_app flower
```

Visit **http://localhost:5555** to see:

- Active, reserved, and completed tasks
- Per-worker throughput and concurrency
- Task arguments, return values, and execution times
- Ability to revoke (cancel) pending tasks

---

## Testing

The project currently ships with manual API tests. Automated test coverage is tracked as a future improvement.

**Manual smoke test (PowerShell)**

Run all three task types end-to-end with a single script:

```powershell
# 1. Authenticate
$token = ((Invoke-WebRequest -Uri "http://localhost:8000/token" -Method POST `
    -Headers @{"Content-Type"="application/x-www-form-urlencoded"} `
    -Body "username=user1&password=password1").Content | ConvertFrom-Json).access_token

$headers = @{ "Authorization" = "Bearer $token"; "Content-Type" = "application/json" }

# 2. Submit all three task types
$g = ((Invoke-WebRequest -Uri "http://localhost:8000/tasks/process"         -Method POST -Headers $headers -Body '{"data":"smoke-test"}').Content        | ConvertFrom-Json).task_id
$n = ((Invoke-WebRequest -Uri "http://localhost:8000/tasks/process-numbers" -Method POST -Headers $headers -Body '{"numbers":[1,2,3]}').Content           | ConvertFrom-Json).task_id
$i = ((Invoke-WebRequest -Uri "http://localhost:8000/tasks/process-image"   -Method POST -Headers $headers -Body '{"image_id":"test.jpg"}').Content       | ConvertFrom-Json).task_id

Write-Host "Tasks submitted: generic=$g numbers=$n image=$i"

# 3. Poll until complete (image task finishes fastest)
Start-Sleep -Seconds 6
foreach ($id in @($g, $n, $i)) {
    ((Invoke-WebRequest -Uri "http://localhost:8000/tasks/$id" `
        -Headers @{ "Authorization" = "Bearer $token" }).Content | ConvertFrom-Json) | Format-List
}
```

**Validate the interactive docs**

Open **http://127.0.0.1:8000/docs** — the auto-generated OpenAPI UI lets you try every endpoint directly in the browser.

**Verify Celery signals write to the database without polling**

1. Submit a task and note the task ID.
2. Wait for the expected processing duration.
3. Query `/tasks/{task_id}` — the status should already be `SUCCESS` or `FAILURE` without any intermediate polling, because the worker's signal handler updates the database directly.

---

## Security Considerations

| Risk | Mitigation |
|---|---|
| **Weak JWT secret** | Set `APP_SECRET_KEY` to a cryptographically random 256-bit value (`openssl rand -hex 32`). A temporary key is generated at startup if unset — all tokens are invalidated on restart. |
| **Credential exposure** | `.env` and `*.db` are gitignored. Never commit secrets to version control. |
| **SQL injection** | All database operations use parameterized queries via `aiosqlite`. |
| **Rate limit bypass via proxy** | `get_proxied_address()` reads `X-Forwarded-For` then `X-Real-IP` before falling back to the direct remote address. |
| **Replay / CSRF** | Short-lived JWTs (30-minute TTL) mitigate replay attacks. Add explicit CSRF protection if you move to cookie-based auth. |
| **Task double-execution** | `task_acks_late = True` improves fault tolerance but means a worker crash may re-run a task. Ensure your tasks are **idempotent** in production. |
| **Broker exposure** | Secure Redis with a password in `CELERY_BROKER_URL`, restrict network access via firewall rules, and use `rediss://` (TLS) over untrusted networks. |
| **Dependency vulnerabilities** | Regularly run `pip-audit` or Snyk against `requirements.txt` and keep packages patched. |

---

## Contributing

Contributions, issues, and feature requests are welcome.

1. **Fork** the repository and create a feature branch:

   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** — keep commits small and focused.
3. **Write tests** for new behaviour where applicable.
4. **Ensure the app starts cleanly** and the smoke-test script passes.
5. **Open a Pull Request** with a clear description of the problem and solution.

Please follow the [Contributor Covenant Code of Conduct](https://www.contributor-covenant.org/version/2/1/code_of_conduct/) in all interactions.

For bug reports and feature suggestions, please [open an issue](https://github.com/dhaatrik/distributed-task-queue/issues).

---

## License

This project is released under the **MIT License** — see the [LICENSE](LICENSE) file for full details.

You are free to use, modify, and distribute this software in any project, commercial or otherwise, provided the original copyright notice is preserved.

---

<div align="center">

Built by [Dhaatrik Chowdhury](https://github.com/dhaatrik) · Powered by FastAPI, Celery & Redis

</div>
