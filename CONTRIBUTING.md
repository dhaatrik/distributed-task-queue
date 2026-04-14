# Contributing to TaskForge

Thank you for taking the time to contribute! 🎉  
All contributions — code, documentation, bug reports, and feature suggestions — are welcome.

---

## Table of Contents

1. [Code of Conduct](#code-of-conduct)
2. [Getting Started](#getting-started)
3. [How to Contribute](#how-to-contribute)
   - [Reporting Bugs](#reporting-bugs)
   - [Suggesting Features](#suggesting-features)
   - [Submitting Pull Requests](#submitting-pull-requests)
4. [Development Setup](#development-setup)
5. [Coding Standards](#coding-standards)
6. [Commit Message Guidelines](#commit-message-guidelines)
7. [Project Structure](#project-structure)

---

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct v2.1](https://www.contributor-covenant.org/version/2/1/code_of_conduct/).  
By participating, you agree to uphold a respectful and inclusive environment for everyone.

---

## Getting Started

1. **Fork** this repository on GitHub.
2. **Clone** your fork locally:
   ```bash
   git clone https://github.com/<your-username>/distributed-task-queue.git
   cd distributed-task-queue
   ```
3. **Add the upstream remote** so you can keep your fork in sync:
   ```bash
   git remote add upstream https://github.com/dhaatrik/distributed-task-queue.git
   ```
4. Follow the [Development Setup](#development-setup) steps below.

---

## How to Contribute

### Reporting Bugs

Before opening a bug report, please search the [existing issues](https://github.com/dhaatrik/distributed-task-queue/issues) to avoid duplicates.

When opening a new issue, include:
- A clear, descriptive title.
- Steps to reproduce the problem.
- Expected vs. actual behavior.
- Environment details (OS, Python version, Redis version).
- Relevant log output or error messages.

### Suggesting Features

Feature requests are very welcome! Please [open an issue](https://github.com/dhaatrik/distributed-task-queue/issues) with:
- A description of the problem you are trying to solve.
- Your proposed solution or idea.
- Any alternatives you have considered.

### Submitting Pull Requests

1. Create a focused feature branch from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```
2. Make your changes — keep commits **small and focused** (one logical change per commit).
3. Ensure the application starts cleanly and the manual smoke test passes (see [README — Testing](README.md#testing)).
4. Push your branch and open a Pull Request against `main`:
   ```bash
   git push origin feature/your-feature-name
   ```
5. Fill in the PR template with:
   - **What** the change does.
   - **Why** it is needed.
   - **How** you tested it.

> [!NOTE]
> Please keep PRs focused on a single concern. Large, wide-ranging PRs are harder to review and are more likely to be rejected.

---

## Development Setup

### Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Python | 3.12+ | [python.org](https://www.python.org/downloads/) |
| Docker Desktop | Latest | Used to run Redis locally |
| Git | Any | [git-scm.com](https://git-scm.com/) |

### Installation

```bash
# 1. Create and activate a virtual environment
python -m venv .venv

# Windows
.\.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# 2. Install all dependencies
pip install -r requirements.txt

# 3. Copy and configure environment variables
cp .env.example .env
# Edit .env with your preferred values

# 4. Start Redis
docker run -d -p 6379:6379 --name redis-server redis
```

### Running the Stack

Open four terminals, each with the virtual environment activated:

```bash
# Terminal 1 — Default queue worker
celery -A celery_app worker -Q default --loglevel=info --pool=solo

# Terminal 2 — High-priority queue worker
celery -A celery_app worker -Q high_priority --loglevel=info --pool=solo

# Terminal 3 — FastAPI server
uvicorn main:app --reload

# Terminal 4 — Flower monitor (optional)
celery -A celery_app flower
```

---

## Coding Standards

- **Style**: Follow [PEP 8](https://peps.python.org/pep-0008/). Use a formatter such as `black` or `ruff format` before committing.
- **Type hints**: All new functions and methods must include type annotations.
- **Docstrings**: Public functions should have a concise docstring describing their purpose and any non-obvious behavior.
- **Security**: Never commit secrets, credentials, or `.env` files. Use environment variables for all configuration.
- **Async**: FastAPI endpoints must be `async`; use `aiosqlite` for all database interactions on the API side.
- **Idempotency**: Celery tasks that write to external state should be designed to be safely re-runnable.

---

## Commit Message Guidelines

Follow the [Conventional Commits](https://www.conventionalcommits.org/) specification:

```
<type>(<scope>): <short description>

[optional body]

[optional footer]
```

Common types:

| Type | When to use |
|---|---|
| `feat` | A new feature |
| `fix` | A bug fix |
| `docs` | Documentation changes only |
| `refactor` | Code change that is neither a fix nor a feature |
| `test` | Adding or updating tests |
| `chore` | Build process, dependency updates, tooling |

**Examples:**
```
feat(api): add DELETE /tasks/{task_id} endpoint
fix(worker): prevent signal handler crash on None task_id
docs(readme): update installation steps for Windows
```

---

## Project Structure

```
distributed-task-queue/
├── main.py           # FastAPI application, routes, auth, DB helpers
├── celery_app.py     # Celery app config, signal handlers, task definitions
├── static/
│   └── index.html    # Bento-grid web dashboard (single-page, vanilla JS)
├── .env.example      # Environment variable template
├── requirements.txt  # Pinned Python dependencies
├── LICENSE           # MIT License
└── README.md         # Full project documentation
```

---

## Questions?

If you have a question that is not covered here, feel free to [open an issue](https://github.com/dhaatrik/distributed-task-queue/issues) or reach out via the repository's Discussions tab.

---

*Maintained by [Dhaatrik Chowdhury](https://github.com/dhaatrik)*
