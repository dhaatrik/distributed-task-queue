# TaskForge — Distributed Task Queue
# Author: Dhaatrik Chowdhury <https://github.com/dhaatrik>
# Repository: https://github.com/dhaatrik/distributed-task-queue
# License: MIT

import os
import logging
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import AsyncGenerator

import aiosqlite
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from celery.result import AsyncResult
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from celery_app import add_numbers, process_task, simulate_image_processing

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (env vars / 12-Factor App)
# ---------------------------------------------------------------------------
DATABASE_URL: str = os.getenv("DATABASE_URL", "tasks_and_users.db")
ALGORITHM: str = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

_raw_secret = os.getenv("APP_SECRET_KEY")
if _raw_secret:
    SECRET_KEY: str = _raw_secret
else:
    SECRET_KEY = secrets.token_hex(32)
    logger.warning(
        "APP_SECRET_KEY is not set. A temporary key has been generated for this "
        "session — all tokens will be invalidated on restart. "
        "Set APP_SECRET_KEY in your environment or .env file before going to production."
    )

# ---------------------------------------------------------------------------
# Password context & OAuth2
# ---------------------------------------------------------------------------
pwd_context = CryptContext(schemes=["bcrypt"], default="bcrypt", bcrypt__rounds=12)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


# ---------------------------------------------------------------------------
# DB dependency injection
# ---------------------------------------------------------------------------
async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """Yield a single aiosqlite connection per request; close it on teardown."""
    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row
        yield db


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_user_from_db(username: str, db: aiosqlite.Connection):
    """Fetch a user row by username; returns an aiosqlite.Row or None."""
    async with db.execute(
        "SELECT username, hashed_password, disabled FROM users WHERE username = ?",
        (username,),
    ) as cursor:
        return await cursor.fetchone()


async def authenticate_user(username: str, password: str, db: aiosqlite.Connection):
    user = await get_user_from_db(username, db)
    if not user or not verify_password(password, user["hashed_password"]):
        return False
    return user


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Validate the JWT bearer token and return the authenticated user row."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str | None = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = await get_user_from_db(username, db)
    if user is None:
        raise credentials_exception
    return user


# ---------------------------------------------------------------------------
# Proxy-aware rate-limiter key function
# ---------------------------------------------------------------------------
def get_proxied_address(request: Request) -> str:
    """
    Resolve the real client IP even when running behind a reverse proxy.

    Precedence:
      1. X-Forwarded-For header (leftmost entry = original client)
      2. X-Real-IP header
      3. Direct remote address (fallback for non-proxied deployments)
    """
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # The header can be comma-separated; the leftmost IP is the originating client.
        return forwarded_for.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "unknown"


limiter = Limiter(key_func=get_proxied_address)


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------
async def _init_schema(db: aiosqlite.Connection) -> None:
    """Create application tables if they do not already exist."""
    await db.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            task_id      TEXT PRIMARY KEY,
            name         TEXT NOT NULL,
            status       TEXT NOT NULL,
            result       TEXT,
            created_at   TEXT NOT NULL,
            completed_at TEXT
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username        TEXT PRIMARY KEY,
            hashed_password TEXT NOT NULL,
            disabled        INTEGER DEFAULT 0
        )
    """)
    await db.commit()


async def _seed_test_user(db: aiosqlite.Connection) -> None:
    """Insert a default test user if one does not already exist."""
    async with db.execute(
        "SELECT username FROM users WHERE username = ?", ("user1",)
    ) as cursor:
        exists = await cursor.fetchone()

    if not exists:
        hashed = pwd_context.hash("password1")
        await db.execute(
            "INSERT INTO users (username, hashed_password, disabled) VALUES (?, ?, ?)",
            ("user1", hashed, 0),
        )
        await db.commit()
        logger.info("Test user 'user1' created with default password 'password1'.")
    else:
        logger.info("Test user 'user1' already exists — skipping seed.")


# ---------------------------------------------------------------------------
# Lifespan context manager (replaces deprecated @app.on_event)
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Handle application startup and graceful shutdown."""
    logger.info("Startup — initialising database…")
    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row
        await _init_schema(db)
        await _seed_test_user(db)
    logger.info("Database ready. Application is accepting requests.")
    yield
    logger.info("Shutdown complete.")


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Distributed Task Queue",
    description="A FastAPI + Celery distributed task processing service.",
    version="1.0.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class TaskData(BaseModel):
    data: str


class NumbersTaskData(BaseModel):
    numbers: list[float]


class ImageTaskData(BaseModel):
    image_id: str


class TaskResultModel(BaseModel):
    task_id: str
    name: str
    status: str
    result: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def read_root():
    try:
        with open("static/index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read(), status_code=200)
    except FileNotFoundError:
        return HTMLResponse(
            content="<h1>File not found</h1><p>index.html missing from static folder.</p>",
            status_code=404,
        )


@app.post("/token")
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: aiosqlite.Connection = Depends(get_db),
):
    user = await authenticate_user(form_data.username, form_data.password, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(
        data={"sub": user["username"]},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return {"access_token": access_token, "token_type": "bearer"}


@app.post("/tasks/process", dependencies=[Depends(get_current_user)])
@limiter.limit("5/minute")
async def create_process_task(
    request: Request,
    task: TaskData,
    db: aiosqlite.Connection = Depends(get_db),
):
    # IMPORTANT: If 'task.data' is used in DB queries, file-system ops, or shell
    # commands it MUST be validated and sanitised to prevent injection attacks.
    result = process_task.delay(task.data)
    await db.execute(
        "INSERT INTO tasks (task_id, name, status, created_at) VALUES (?, ?, ?, ?)",
        (result.id, "process_task", "SUBMITTED", datetime.utcnow().isoformat()),
    )
    await db.commit()
    return {"task_id": result.id}


@app.post("/tasks/process-numbers", dependencies=[Depends(get_current_user)])
@limiter.limit("5/minute")
async def create_add_numbers_task(
    request: Request,
    task_data: NumbersTaskData,
    db: aiosqlite.Connection = Depends(get_db),
):
    result = add_numbers.delay(task_data.numbers)
    await db.execute(
        "INSERT INTO tasks (task_id, name, status, created_at) VALUES (?, ?, ?, ?)",
        (result.id, "add_numbers", "SUBMITTED", datetime.utcnow().isoformat()),
    )
    await db.commit()
    return {"task_id": result.id}


@app.post("/tasks/process-image", dependencies=[Depends(get_current_user)])
@limiter.limit("5/minute")
async def create_simulate_image_processing_task(
    request: Request,
    task_data: ImageTaskData,
    db: aiosqlite.Connection = Depends(get_db),
):
    result = simulate_image_processing.delay(task_data.image_id)
    await db.execute(
        "INSERT INTO tasks (task_id, name, status, created_at) VALUES (?, ?, ?, ?)",
        (result.id, "simulate_image_processing", "SUBMITTED", datetime.utcnow().isoformat()),
    )
    await db.commit()
    return {"task_id": result.id}


@app.get("/tasks/{task_id}", dependencies=[Depends(get_current_user)])
async def get_task_status(
    task_id: str,
    db: aiosqlite.Connection = Depends(get_db),
):
    task_result = AsyncResult(task_id)

    if task_result.ready():
        # Safety-net upsert — Celery signals should have already written to the DB,
        # but this guarantees correctness even if the signal was missed.
        await db.execute(
            "UPDATE tasks SET status = ?, result = ?, completed_at = ? WHERE task_id = ?",
            (
                task_result.status,
                str(task_result.result),
                datetime.utcnow().isoformat(),
                task_id,
            ),
        )
        await db.commit()

    async with db.execute(
        "SELECT task_id, name, status, result, created_at, completed_at FROM tasks WHERE task_id = ?",
        (task_id,),
    ) as cursor:
        db_row = await cursor.fetchone()

    if db_row:
        return dict(db_row)

    # Last-resort fallback for tasks not yet present in the database.
    return {
        "task_id": task_id,
        "name": "N/A",
        "status": task_result.state if task_result else "UNKNOWN",
        "result": str(task_result.result) if task_result.ready() else None,
        "source": "celery_direct",
    }