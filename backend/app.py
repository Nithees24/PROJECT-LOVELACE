import sys
import os
import json
import asyncio
import threading
from contextlib import asynccontextmanager
from pathlib import Path

# Ensure the root project directory is in sys.path so 'backend' is recognized as a module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Anchor all filesystem paths to the repo root (like logger.py does) so the
# server works regardless of the CWD it was launched from (BUG-14)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAG_STATE_DIR = PROJECT_ROOT / "backend" / "rag" / "rag_state"
RAG_TEMP_DIR = PROJECT_ROOT / "backend" / "data" / "rag"
FRONTEND_DIR = PROJECT_ROOT / "frontend"

# Extensions extract_text_from_file actually knows how to load (SEC-04/09)
ALLOWED_UPLOAD_EXTENSIONS = {".pdf", ".docx", ".txt", ".xlsx", ".xls"}

# Leading-bytes signatures per allowed extension (SEC-09): a file whose
# content doesn't match its claimed type is rejected before it reaches the
# parsers. .docx/.xlsx are ZIP containers, legacy .xls is an OLE compound
# file; .txt has no signature and is accepted as-is.
UPLOAD_MAGIC_BYTES = {
    ".pdf": (b"%PDF-",),
    ".docx": (b"PK\x03\x04",),
    ".xlsx": (b"PK\x03\x04",),
    ".xls": (b"\xd0\xcf\x11\xe0",),
}

import hashlib
import secrets
import time
import uuid
from datetime import datetime, timedelta

from fastapi import FastAPI, BackgroundTasks, Request, File, UploadFile, Header, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr
from sqlalchemy import func
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHash, VerificationError

from backend.utils.logger import logger
from backend.utils.email_utils import send_verification_email
from backend.utils.prompt_builder import UNTRUSTED_RULES, wrap_untrusted
from backend.utils.artifact_extractor import extract_artifact
from backend.config import (
    BASE_URL,
    CHAT_MODEL,
    RAG_SCORE_THRESHOLD,
    PRODUCTION,
    CORS_ALLOWED_ORIGINS,
    MAX_UPLOAD_BYTES,
    MAX_UPLOAD_MB,
    MAX_DOCS_PER_CONVERSATION,
    GLOBAL_RATE_LIMIT_PER_MINUTE,
    AUTH_RATE_LIMIT_PER_MINUTE,
    LOGIN_MAX_FAILURES,
    LOGIN_FAILURE_WINDOW_SECONDS,
    LOGIN_LOCKOUT_SECONDS,
    VERIFICATION_TOKEN_TTL_HOURS,
)
from backend.utils.rate_limiter import SlidingWindowRateLimiter, FailedLoginTracker
from backend.llm.llm_client import LLMClient
from backend.agents.general_chat_agent import GeneralChatAgent
from backend.agents.deep_research_agent import DeepResearchAgent
from backend.agents.document_agent import DocumentAgent
from backend.agents.generator_agent import (
    DocumentGeneratorAgent,
    FormatUnavailableError,
    UnsupportedFormatError,
)
from backend.pipeline.planner import Planner
from backend.database.connection import create_tables, SessionLocal
from backend.database.user_model import User
from backend.database.conversation_model import Conversation
from backend.database.message_model import Message
from backend.database.message_repo import save_message, get_messages, get_conversation_history
from backend.rag.pdf_utils import extract_text_from_file, chunk_text
from backend.rag.vector_store import VectorStore
from backend.agents.research.events import EventEmitter

# Globals populated by the lifespan handler at startup (BUG-17). Importing
# this module is side-effect-free: no DB connection, no LLM client work.
llm_client = None
general_agent = None
deep_agent = None
document_agent = None
planner = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global llm_client, general_agent, deep_agent, document_agent, planner
    create_tables()
    llm_client = LLMClient()
    llm_client.probe()  # fail loudly at boot on a bad model name (BUG-02)
    general_agent = GeneralChatAgent(llm_client)
    deep_agent = DeepResearchAgent(llm_client)
    # Shares the research agent's collection pipeline rather than its own tools.
    document_agent = DocumentAgent(llm_client, deep_agent)
    planner = Planner(llm_client)
    logger.info("Startup complete: database ready, agents initialized.")
    yield

app = FastAPI(lifespan=lifespan)

# CORS: explicit origin allowlist only (SEC-08) — a wildcard origin must
# never be paired with allow_credentials=True. See config.CORS_ALLOWED_ORIGINS.
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# Rate limiting (SEC-12): baseline per-IP limit on every API route plus a
# tighter per-IP limit and per-account lockout on the unauthenticated auth
# endpoints. NOTE: keys use the direct client IP — behind a reverse proxy
# this collapses to the proxy's address and must switch to a validated
# X-Forwarded-For.
_rate_limiter = SlidingWindowRateLimiter()
_failed_logins = FailedLoginTracker(
    max_failures=LOGIN_MAX_FAILURES,
    window_seconds=LOGIN_FAILURE_WINDOW_SECONDS,
    lockout_seconds=LOGIN_LOCKOUT_SECONDS,
)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _rate_limit_response(retry_after: int, message: str) -> JSONResponse:
    # Body keeps the {"error": ...} shape the frontend already handles.
    return JSONResponse(
        {"error": message},
        status_code=429,
        headers={"Retry-After": str(retry_after)},
    )


def _internal_error(exc: Exception, context: str = "") -> JSONResponse:
    """Log the full error server-side under a correlation id and return a
    generic 500 to the client (SEC-15). Raw exception text — DB driver
    messages, SQLAlchemy internals, stack details — must never reach the
    caller; the request_id lets a user report be traced back to the log
    line. Body keeps the {"error": ...} shape the frontend already reads,
    now with a real 5xx status instead of a misleading 200."""
    request_id = uuid.uuid4().hex[:12]
    label = f"{context} " if context else ""
    logger.error(f"[req {request_id}] {label}unhandled error: {exc}", exc_info=True)
    return JSONResponse(
        {"error": "An internal error occurred. Please try again.", "request_id": request_id},
        status_code=500,
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Catch-all safety net (SEC-15): any exception that escapes a handler
    (or is raised in a dependency) returns a generic 500, never a stack
    trace. HTTPException has its own handler and is unaffected."""
    return _internal_error(exc, f"{request.method} {request.url.path}")


def _check_auth_rate_limit(request: Request, endpoint: str):
    """Shared per-IP limiter for unauthenticated auth endpoints. Returns a
    429 JSONResponse when over the limit, else None."""
    ip = _client_ip(request)
    allowed, retry_after = _rate_limiter.hit(
        f"auth:{endpoint}:{ip}", AUTH_RATE_LIMIT_PER_MINUTE, 60
    )
    if not allowed:
        logger.warning(f"[RateLimit] {endpoint} limit exceeded for IP {ip}")
        return _rate_limit_response(retry_after, "Too many attempts. Please try again later.")
    return None


@app.middleware("http")
async def global_rate_limit(request: Request, call_next):
    # Baseline defence for every API route (static files excluded) — the
    # endpoint-specific auth limits above are much tighter.
    if request.url.path.startswith("/api/"):
        ip = _client_ip(request)
        allowed, retry_after = _rate_limiter.hit(
            f"global:{ip}", GLOBAL_RATE_LIMIT_PER_MINUTE, 60
        )
        if not allowed:
            logger.warning(
                f"[RateLimit] Global limit exceeded for IP {ip} on {request.url.path}"
            )
            return _rate_limit_response(retry_after, "Too many requests. Please slow down.")
    return await call_next(request)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    client_host = request.client.host if request.client else "unknown"
    logger.info(f"Incoming request: {request.method} {request.url.path} from client {client_host}")
    
    try:
        response = await call_next(request)
        process_time = (time.time() - start_time) * 1000
        logger.info(f"Completed request: {request.method} {request.url.path} - Status: {response.status_code} - Processed in {process_time:.2f}ms")
        return response
    except Exception as e:
        process_time = (time.time() - start_time) * 1000
        logger.error(f"Request failed: {request.method} {request.url.path} - Error: {str(e)} - Processed in {process_time:.2f}ms", exc_info=True)
        raise e

class CheckEmailRequest(BaseModel):
    email: EmailStr

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    first_name: str
    last_name: str
    role: str
    dob: str = None
    gender: str = None

# Argon2id password hashing (SEC-03): salted + slow, per-user salt embedded
# in the output string. Replaces unsalted single-round SHA-256.
_password_hasher = PasswordHasher()

# Argon2 hashes the whole password with no built-in length cap. Because
# register/login are unauthenticated and unthrottled (SEC-12), an attacker
# could POST a multi-megabyte password to force expensive hashing work
# (a cheap DoS). Reject absurd lengths before spending any hashing effort;
# no legitimate password comes anywhere near this.
MAX_PASSWORD_LENGTH = 1024

# Single generic message for every credential failure (SEC-14): a distinct
# "User not found" vs "Incorrect password" lets an attacker enumerate which
# emails are registered. Both now return this identical string.
INVALID_CREDENTIALS_ERROR = "Invalid email or password."

# A throwaway Argon2 hash used to run a real verification when the account
# doesn't exist (SEC-14). Without it, the not-found path returns before the
# expensive Argon2 work that the wrong-password path performs, so response
# TIMING distinguishes registered from unregistered emails even though the
# error text is identical. Verifying the submitted password against this
# hash always fails but costs the same as a real check.
_DUMMY_ARGON2_HASH = _password_hasher.hash("timing-equalization-placeholder")

def hash_password(password: str) -> str:
    if password is None or len(password) > MAX_PASSWORD_LENGTH:
        raise ValueError("Password exceeds maximum allowed length")
    return _password_hasher.hash(password)

def _is_legacy_sha256(stored_hash: str) -> bool:
    """Old hashes are 64 lowercase hex chars; Argon2 hashes start with $argon2."""
    return (
        isinstance(stored_hash, str)
        and len(stored_hash) == 64
        and all(c in "0123456789abcdef" for c in stored_hash)
    )

def verify_password(password: str, stored_hash: str) -> tuple:
    """Return (is_valid, needs_rehash).

    Verifies against Argon2id, falling back to the legacy unsalted SHA-256
    scheme so pre-existing accounts keep working. A legacy match (or an
    Argon2 hash whose cost parameters are now out of date) reports
    needs_rehash=True so the caller can transparently upgrade it (SEC-03)."""
    if not stored_hash:
        return False, False
    # An over-length password can never match a stored hash (hash_password
    # would have rejected it at registration), so fail cheaply without
    # handing the oversized input to Argon2 (SEC-03 DoS guard).
    if password is None or len(password) > MAX_PASSWORD_LENGTH:
        return False, False
    if _is_legacy_sha256(stored_hash):
        legacy = hashlib.sha256(password.encode()).hexdigest()
        return secrets.compare_digest(legacy, stored_hash), True
    try:
        _password_hasher.verify(stored_hash, password)
    except (VerifyMismatchError, InvalidHash, VerificationError):
        return False, False
    return True, _password_hasher.check_needs_rehash(stored_hash)

def normalize_email(email: str) -> str:
    """Lowercase so A@x.com and a@x.com can't become two accounts (BUG-26)."""
    return email.strip().lower()

def parse_dob(dob_str: str):
    """Strictly validate a YYYY-MM-DD date of birth (BUG-27).

    Returns (normalized_dob_string, age). Raises ValueError for impossible
    calendar dates (e.g. 2000-02-31) or dates in the future."""
    dob_date = datetime.strptime(dob_str.strip(), "%Y-%m-%d")
    today = datetime.utcnow()
    if dob_date > today:
        raise ValueError("date of birth is in the future")
    age = today.year - dob_date.year - ((today.month, today.day) < (dob_date.month, dob_date.day))
    return dob_date.strftime("%Y-%m-%d"), age

INVALID_DOB_ERROR = "Invalid date of birth: please enter a real calendar date (YYYY-MM-DD) that is not in the future."

def find_user_by_email(db, email: str):
    """Case-insensitive lookup — tolerates mixed-case emails stored before
    normalization was introduced."""
    return db.query(User).filter(func.lower(User.email) == normalize_email(email)).first()


# ──────────────────────────────────────────────
# Authentication / authorization (SEC-01, SEC-02)
#
# Every request must present a bearer token issued at login. Identity is
# resolved from that token, never from a user_id in the URL or body — this
# closes the IDOR where any integer let you read/delete another user's data.
# The token is an unguessable server-issued secret with a finite lifetime,
# so a client can no longer assert identity by setting a small integer.
# ──────────────────────────────────────────────

SESSION_TTL = timedelta(days=7)  # how long a login stays valid (SEC-02)

def issue_session(user) -> str:
    """Mint a fresh opaque token + expiry on the user row and return it."""
    user.session_token = secrets.token_urlsafe(32)
    user.session_expires_at = datetime.utcnow() + SESSION_TTL
    return user.session_token

def get_current_user_id(authorization: str = Header(None)) -> int:
    """FastAPI dependency: resolve the authenticated user id from the
    'Authorization: Bearer <token>' header. Raises 401 if the token is
    absent, unknown, or expired.

    Runs before the route body (via Depends), so the 401 is not swallowed by
    a route's broad `except Exception` handler."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.session_token == token).first()
        if not user:
            raise HTTPException(status_code=401, detail="Invalid or expired session")
        # Expiry check (SEC-02): reject and clear a stale token
        if not user.session_expires_at or user.session_expires_at < datetime.utcnow():
            user.session_token = None
            user.session_expires_at = None
            db.commit()
            raise HTTPException(status_code=401, detail="Session expired")
        return user.id
    finally:
        db.close()


def require_owned_conversation(db, conversation_id: int, user_id: int):
    """Return the conversation only if it belongs to `user_id`, else 404.

    404 (not 403) so an attacker can't distinguish 'not yours' from
    'does not exist' by probing ids. Callers that wrap the body in a broad
    `except Exception` must re-raise HTTPException first (see the routes)."""
    conv = (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id, Conversation.user_id == user_id)
        .first()
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv

@app.post("/api/auth/check-email")
def check_email(req: CheckEmailRequest, request: Request):
    # Throttled per-IP (SEC-12) — this endpoint reveals account existence,
    # so unrestricted calls enable bulk user enumeration.
    limited = _check_auth_rate_limit(request, "check-email")
    if limited:
        return limited
    # This endpoint is an inherent existence oracle: the frontend needs the
    # boolean to branch between the login and signup UI, so it can't be
    # removed. Bulk enumeration is bounded by the per-IP auth rate limit
    # (SEC-12) rather than by hiding the answer (SEC-14).
    db = SessionLocal()
    try:
        user = find_user_by_email(db, req.email)
        return {"exists": user is not None}
    except Exception as e:
        return _internal_error(e)
    finally:
        db.close()

@app.post("/api/auth/register")
def register(req: SignupRequest, background_tasks: BackgroundTasks, request: Request):
    # Same per-IP throttle as login (SEC-12): registration is unauthenticated
    # and triggers Argon2 hashing plus an SMTP send per call.
    limited = _check_auth_rate_limit(request, "register")
    if limited:
        return limited
    db = SessionLocal()
    try:
        email = normalize_email(req.email)
        exists = find_user_by_email(db, email)
        if exists:
            return {"error": "Email already registered"}
        
        # Validate dob strictly — reject impossible dates instead of silently
        # storing them with a NULL age (BUG-27)
        dob = None
        calculated_age = None
        if req.dob:
            try:
                dob, calculated_age = parse_dob(req.dob)
            except ValueError:
                return {"error": INVALID_DOB_ERROR}

        verification_token = str(uuid.uuid4())

        new_user = User(
            email=email,
            password_hash=hash_password(req.password),
            first_name=req.first_name,
            last_name=req.last_name,
            role=req.role,
            age=calculated_age,
            dob=dob,
            gender=req.gender,
            verification_token=verification_token,
            verification_token_created_at=datetime.utcnow(),  # SEC-13
        )
        db.add(new_user)
        db.commit()

        background_tasks.add_task(
            send_verification_email,
            email,
            verification_token,
            BASE_URL
        )

        return {"success": True, "message": "User created successfully"}
    except Exception as e:
        return _internal_error(e)
    finally:
        db.close()

@app.get("/api/auth/verify/{token}", response_class=HTMLResponse)
def verify_email(token: str):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.verification_token == token).first()
        if not user:
            return HTMLResponse(content="""
                <html>
                    <body style="background-color:#182321; color:#fff; font-family:sans-serif; text-align:center; padding-top:100px;">
                        <h2>Verification Failed</h2>
                        <p style="color:#ff8d72;">Invalid or expired verification link.</p>
                    </body>
                </html>
            """, status_code=404)

        # Enforce the 24h expiry the email advertises (SEC-13). A missing
        # timestamp means the token predates the expiry column — expired.
        issued_at = user.verification_token_created_at
        if not issued_at or datetime.utcnow() - issued_at > timedelta(hours=VERIFICATION_TOKEN_TTL_HOURS):
            # Clear the stale token so a resend mints a fresh one
            user.verification_token = None
            user.verification_token_created_at = None
            db.commit()
            return HTMLResponse(content="""
                <html>
                    <body style="background-color:#182321; color:#fff; font-family:sans-serif; text-align:center; padding-top:100px;">
                        <h2>Verification Link Expired</h2>
                        <p style="color:#ff8d72;">This link is older than 24 hours. Please request a new verification email from the login page.</p>
                    </body>
                </html>
            """, status_code=410)

        user.is_verified = True
        user.verification_token = None
        user.verification_token_created_at = None
        db.commit()
        
        return HTMLResponse(content="""
            <html>
                <body style="background-color:#182321; color:#fff; font-family:sans-serif; text-align:center; padding-top:100px;">
                    <h2>Email Verified Successfully!</h2>
                    <p style="color:#34A853;">Your research identity has been confirmed. You can close this tab and return to the login page.</p>
                </body>
            </html>
        """)
    except Exception as e:
        # Generic HTML error — never echo the raw exception to the page (SEC-15)
        request_id = uuid.uuid4().hex[:12]
        logger.error(f"[req {request_id}] verify_email unhandled error: {e}", exc_info=True)
        return HTMLResponse(content=f"""
            <html>
                <body style="background-color:#182321; color:#fff; font-family:sans-serif; text-align:center; padding-top:100px;">
                    <h2>Something went wrong</h2>
                    <p style="color:#ff8d72;">We couldn't complete verification. Please try again later.</p>
                    <p style="color:#8c8c8c; font-size:12px;">Reference: {request_id}</p>
                </body>
            </html>
        """, status_code=500)
    finally:
        db.close()

class ResendEmailRequest(BaseModel):
    email: EmailStr

@app.post("/api/auth/resend-email")
def resend_email(req: ResendEmailRequest, background_tasks: BackgroundTasks):
    db = SessionLocal()
    try:
        user = find_user_by_email(db, req.email)
        if not user:
            return {"error": "User not found"}
        if user.is_verified:
            return {"error": "User is already verified"}
            
        now = datetime.utcnow()
        current_count = user.resend_count or 0
        
        if current_count >= 3:
            if user.last_resend_time and now - user.last_resend_time < timedelta(hours=6):
                return {"error": "max no.of time used, try after some time."}
            else:
                user.resend_count = 1
                user.last_resend_time = now
        else:
            if user.last_resend_time and now - user.last_resend_time > timedelta(hours=24):
                user.resend_count = 1
            else:
                user.resend_count = current_count + 1
            user.last_resend_time = now
            
        # Always rotate the token on resend (SEC-13): the old link dies, so
        # one long-lived secret can't accumulate across inboxes/mail logs,
        # and the new one gets a fresh 24h expiry window.
        user.verification_token = str(uuid.uuid4())
        user.verification_token_created_at = datetime.utcnow()

        db.commit()
        
        background_tasks.add_task(
            send_verification_email,
            user.email,
            user.verification_token,
            BASE_URL
        )
        
        return {"success": True, "message": "Verification email resent"}
    except Exception as e:
        return _internal_error(e)
    finally:
        db.close()

@app.post("/api/auth/login")
def login(req: LoginRequest, request: Request):
    # Per-IP throttle + per-account lockout (SEC-12). The lockout is keyed
    # by the submitted (normalized) email, so it follows the targeted
    # account across attacking IPs.
    limited = _check_auth_rate_limit(request, "login")
    if limited:
        return limited
    account_key = normalize_email(req.email)
    locked, retry_after = _failed_logins.is_locked(account_key)
    if locked:
        logger.warning(f"[Auth] Login rejected — account '{account_key}' is locked ({_client_ip(request)})")
        return _rate_limit_response(
            retry_after,
            "Too many failed login attempts. This account is temporarily locked — try again later.",
        )

    db = SessionLocal()
    try:
        user = find_user_by_email(db, req.email)
        if not user:
            # Run a real (always-failing) verification so a missing account
            # costs the same time as a wrong password — otherwise latency is
            # an enumeration oracle even with identical error text (SEC-14).
            verify_password(req.password, _DUMMY_ARGON2_HASH)
            logger.warning(f"[Auth] Failed login for unknown '{account_key}' from {_client_ip(request)}")
            _failed_logins.record_failure(account_key)
            return {"error": INVALID_CREDENTIALS_ERROR}

        ok, needs_rehash = verify_password(req.password, user.password_hash)
        if not ok:
            logger.warning(f"[Auth] Failed login for '{account_key}' from {_client_ip(request)}")
            _failed_logins.record_failure(account_key)
            return {"error": INVALID_CREDENTIALS_ERROR}

        # Reached only after a correct password, so this does not leak account
        # existence to an attacker who doesn't already hold valid credentials;
        # kept distinct so a legitimate unverified user gets actionable UX
        # instead of a misleading "invalid password" (SEC-14).
        if not user.is_verified:
            return {"error": "Please verify your email address before logging in."}

        # Opportunistically upgrade a legacy/outdated hash to current Argon2id (SEC-03)
        if needs_rehash:
            user.password_hash = hash_password(req.password)

        # Successful login clears the failure counter for this account
        _failed_logins.record_success(account_key)

        # Issue a fresh, expiring bearer token the client sends on every
        # subsequent request (SEC-01, SEC-02)
        token = issue_session(user)
        db.commit()

        return {
            "success": True,
            "user_id": user.id,
            "first_name": user.first_name,
            "token": token,
        }
    except Exception as e:
        return _internal_error(e)
    finally:
        db.close()

class UpdateProfileRequest(BaseModel):
    user_id: int
    password: str
    first_name: str = None
    last_name: str = None
    dob: str = None
    gender: str = None

class ChangePasswordRequest(BaseModel):
    user_id: int
    current_password: str
    new_password: str

@app.get("/api/auth/profile/{user_id}")
def get_profile(user_id: int, current_user_id: int = Depends(get_current_user_id)):
    # Identity comes from the token; the path id must match it (SEC-01)
    if user_id != current_user_id:
        raise HTTPException(status_code=404, detail="User not found")
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == current_user_id).first()
        if not user:
            return {"error": "User not found"}
        return {
            "success": True,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "dob": user.dob,
            "gender": user.gender,
            "role": user.role
        }
    except HTTPException:
        raise
    except Exception as e:
        return _internal_error(e)
    finally:
        db.close()

@app.put("/api/auth/profile")
def update_profile(req: UpdateProfileRequest, current_user_id: int = Depends(get_current_user_id)):
    db = SessionLocal()
    try:
        # Always operate on the authenticated user; body user_id is ignored (SEC-01)
        user = db.query(User).filter(User.id == current_user_id).first()
        if not user:
            return {"error": "User not found"}
        ok, needs_rehash = verify_password(req.password, user.password_hash)
        if not ok:
            return {"error": "Incorrect password"}
        if needs_rehash:
            user.password_hash = hash_password(req.password)

        if req.first_name is not None:
            user.first_name = req.first_name
        if req.last_name is not None:
            user.last_name = req.last_name
        if req.dob is not None:
            try:
                user.dob, user.age = parse_dob(req.dob)
            except ValueError:
                return {"error": INVALID_DOB_ERROR}
        if req.gender is not None:
            user.gender = req.gender

        db.commit()
        return {"success": True, "first_name": user.first_name}
    except Exception as e:
        return _internal_error(e)
    finally:
        db.close()

@app.put("/api/auth/change-password")
def change_password(req: ChangePasswordRequest, current_user_id: int = Depends(get_current_user_id)):
    db = SessionLocal()
    try:
        # Always operate on the authenticated user; body user_id is ignored (SEC-01)
        user = db.query(User).filter(User.id == current_user_id).first()
        if not user:
            return {"error": "User not found"}
        ok, _ = verify_password(req.current_password, user.password_hash)
        if not ok:
            return {"error": "Current password is incorrect"}
        if len(req.new_password) < 6:
            return {"error": "New password must be at least 6 characters"}

        user.password_hash = hash_password(req.new_password)
        # Rotate the session token so the changed password invalidates the
        # old credential (SEC-01)
        new_token = issue_session(user)
        db.commit()
        return {"success": True, "token": new_token}
    except Exception as e:
        return _internal_error(e)
    finally:
        db.close()

class CreateConversationRequest(BaseModel):
    user_id: int

@app.post("/api/conversations")
def create_conversation(req: CreateConversationRequest, current_user_id: int = Depends(get_current_user_id)):
    db = SessionLocal()
    try:
        # Always create for the authenticated user; body user_id is ignored (SEC-01)
        new_conv = Conversation(user_id=current_user_id, title="New Conversation")
        db.add(new_conv)
        db.commit()
        db.refresh(new_conv)
        return {"success": True, "conversation_id": new_conv.id, "title": new_conv.title}
    except Exception as e:
        return _internal_error(e)
    finally:
        db.close()

@app.get("/api/conversations/{user_id}")
def get_user_conversations(user_id: int, current_user_id: int = Depends(get_current_user_id)):
    # A user may only list their own conversations (SEC-01)
    if user_id != current_user_id:
        raise HTTPException(status_code=404, detail="Not found")
    db = SessionLocal()
    try:
        conversations = db.query(Conversation).filter(
            Conversation.user_id == current_user_id
        ).order_by(
            Conversation.is_pinned.desc(),
            Conversation.pinned_at.desc().nullslast(),
            Conversation.created_at.desc()
        ).all()
        return {
            "success": True, 
            "conversations": [
                {
                    "id": c.id,
                    "title": c.title,
                    "created_at": c.created_at.isoformat(),
                    "is_pinned": c.is_pinned
                } for c in conversations
            ]
        }
    except Exception as e:
        return _internal_error(e)
    finally:
        db.close()

@app.post("/api/conversations/{conversation_id}/pin")
def toggle_pin_conversation(conversation_id: int, current_user_id: int = Depends(get_current_user_id)):
    db = SessionLocal()
    try:
        conv = require_owned_conversation(db, conversation_id, current_user_id)
        conv.is_pinned = not conv.is_pinned
        conv.pinned_at = datetime.utcnow() if conv.is_pinned else None
        db.commit()
        return {"success": True, "is_pinned": conv.is_pinned}
    except HTTPException:
        raise
    except Exception as e:
        return _internal_error(e)
    finally:
        db.close()

class RateConversationRequest(BaseModel):
    score: int # +1 or -1

@app.post("/api/conversations/{conversation_id}/rate")
def rate_conversation(conversation_id: int, req: RateConversationRequest, current_user_id: int = Depends(get_current_user_id)):
    logger.info(f"Rating conversation {conversation_id} with score {req.score}")
    db = SessionLocal()
    try:
        conv = require_owned_conversation(db, conversation_id, current_user_id)
        # Increment/Decrement the rating
        conv.rating = (conv.rating or 0) + req.score
        db.commit()
        return {"success": True, "new_rating": conv.rating}
    except HTTPException:
        raise
    except Exception as e:
        return _internal_error(e)
    finally:
        db.close()

def generate_thread_title(first_prompt: str):
    try:
        # Only the opening of the message is needed to name the thread; feeding
        # the whole request just inflates prompt-processing time for no gain.
        snippet = first_prompt[:500]
        # Generate an expressive and unique title. Cap the output (max_tokens)
        # so the model stops after the few words we keep instead of rambling —
        # a title is never more than ~6 words.
        prompt = f"Create a concise, unique, and highly descriptive 3-6 word title for a chat thread starting with this user request. Avoid generic starting words like 'Understanding', 'Exploring', or 'A Guide to'. Tailor the title specifically to the topic. Return ONLY the title text, no quotes or punctuation: {snippet}"
        title = llm_client.generate(prompt, model=CHAT_MODEL, max_tokens=24)
        # Remove quotes if the LLM adds them anyway
        title = title.strip().strip('\"\'')
        return title
    except Exception as e:
        # Fallback to snippet if LLM fails
        logger.error(f"Failed to generate title: {e}", exc_info=True)
        return first_prompt[:30] + "..." if len(first_prompt) > 30 else first_prompt

@app.get("/api/messages/{conversation_id}")
def get_conversation_messages_endpoint(conversation_id: int, current_user_id: int = Depends(get_current_user_id)):
    db = SessionLocal()
    try:
        require_owned_conversation(db, conversation_id, current_user_id)
        messages = get_messages(db, conversation_id)
        result = []
        for m in messages:
            msg_data = {
                # id lets the export endpoint re-render a stored report from
                # the database instead of trusting a client-supplied body.
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "timestamp": m.timestamp.isoformat()
            }
            if m.sources:
                try:
                    msg_data["sources"] = json.loads(m.sources)
                except (json.JSONDecodeError, TypeError):
                    msg_data["sources"] = []
            else:
                msg_data["sources"] = []
            # Deep-research runs persist their full plan + activity trace so the
            # two-pane workspace can be replayed on reload (Phase 2).
            if getattr(m, "research_trace", None):
                try:
                    msg_data["research_trace"] = json.loads(m.research_trace)
                except (json.JSONDecodeError, TypeError):
                    msg_data["research_trace"] = None
            # Document runs persist their brief + interview the same way.
            if getattr(m, "doc_trace", None):
                try:
                    msg_data["doc_trace"] = json.loads(m.doc_trace)
                except (json.JSONDecodeError, TypeError):
                    msg_data["doc_trace"] = None
            # Artifact, so its canvas card reappears on reload.
            if getattr(m, "artifact", None):
                try:
                    msg_data["artifact"] = json.loads(m.artifact)
                except (json.JSONDecodeError, TypeError):
                    msg_data["artifact"] = None
            result.append(msg_data)
        return {
            "success": True,
            "messages": result
        }
    except HTTPException:
        raise
    except Exception as e:
        return _internal_error(e)
    finally:
        db.close()

class RenameConversationRequest(BaseModel):
    title: str

@app.patch("/api/conversations/{conversation_id}")
def rename_conversation(conversation_id: int, req: RenameConversationRequest, current_user_id: int = Depends(get_current_user_id)):
    db = SessionLocal()
    try:
        conv = require_owned_conversation(db, conversation_id, current_user_id)
        conv.title = req.title
        db.commit()
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        return _internal_error(e)
    finally:
        db.close()

@app.delete("/api/conversations/{conversation_id}")
def delete_conversation(conversation_id: int, background_tasks: BackgroundTasks, current_user_id: int = Depends(get_current_user_id)):
    db = SessionLocal()
    try:
        conv = require_owned_conversation(db, conversation_id, current_user_id)

        db.query(Message).filter(Message.conversation_id == conversation_id).delete()

        db.delete(conv)
        db.commit()

        # Delete RAG data if exists
        rag_path = RAG_STATE_DIR / f"{conversation_id}.marker"
        if rag_path.exists():
            rag_path.unlink()
            # Delete the corresponding namespace in Pinecone in the background
            def remove_namespace():
                try:
                    store = VectorStore()
                    store.delete_namespace(conversation_id)
                except Exception as e:
                    logger.error(f"Background task failed to delete namespace: {e}", exc_info=True)
            background_tasks.add_task(remove_namespace)

        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        return _internal_error(e)
    finally:
        db.close()

@app.post("/api/rag/upload")
async def upload_document(conversation_id: int, file: UploadFile = File(...), current_user_id: int = Depends(get_current_user_id)):
    try:
        # Only the conversation's owner may attach documents to it (SEC-01)
        db = SessionLocal()
        try:
            require_owned_conversation(db, conversation_id, current_user_id)
            # Cap documents per conversation (SEC-09) — uploads are recorded
            # as "Uploaded file: ..." user messages, so count those.
            doc_count = (
                db.query(Message)
                .filter(
                    Message.conversation_id == conversation_id,
                    Message.role == "user",
                    Message.content.like("Uploaded file: %"),
                )
                .count()
            )
            if doc_count >= MAX_DOCS_PER_CONVERSATION:
                return {"error": f"Document limit reached for this conversation ({MAX_DOCS_PER_CONVERSATION} files)."}
        finally:
            db.close()

        # Never trust file.filename for a path — it's fully attacker-controlled
        # and a name like "../../app.py" escapes RAG_TEMP_DIR (SEC-04). Derive
        # only the extension from it (needed to pick a loader) and write under
        # a random server-generated name instead.
        ext = os.path.splitext(file.filename or "")[1].lower()
        if ext not in ALLOWED_UPLOAD_EXTENSIONS:
            return {"error": f"Unsupported file extension: {ext or '(none)'}"}

        RAG_TEMP_DIR.mkdir(parents=True, exist_ok=True)
        temp_path = RAG_TEMP_DIR / f"temp_{uuid.uuid4().hex}{ext}"
        # Defense in depth: confirm the resolved path still lands inside
        # RAG_TEMP_DIR before writing anything to disk.
        if RAG_TEMP_DIR.resolve() not in temp_path.resolve().parents:
            return {"error": "Invalid upload path"}

        # Always remove the temp file afterwards, even if extraction/indexing
        # raises. extract_text_from_file re-raises on any parse failure (common
        # with malformed docs), and the random UUID names mean orphaned files
        # would otherwise accumulate on disk indefinitely.
        try:
            # Stream to disk with a running size check (SEC-09): the request
            # body is never buffered in memory, and an oversized upload is
            # rejected mid-stream instead of after it has filled the disk
            # (the enclosing finally removes the partial file).
            bytes_written = 0
            with open(temp_path, "wb") as buffer:
                while chunk := await file.read(1024 * 1024):
                    bytes_written += len(chunk)
                    if bytes_written > MAX_UPLOAD_BYTES:
                        return {"error": f"File too large. Maximum size is {MAX_UPLOAD_MB} MB."}
                    buffer.write(chunk)

            # Reject files whose content doesn't match their claimed
            # extension before they reach the parsers (SEC-09).
            expected_signatures = UPLOAD_MAGIC_BYTES.get(ext)
            if expected_signatures:
                with open(temp_path, "rb") as fh:
                    head = fh.read(8)
                if not any(head.startswith(sig) for sig in expected_signatures):
                    return {"error": f"File content does not match a valid {ext} file."}

            # Extract and chunk
            logger.info(f"Extracting text from {temp_path}...")
            text = extract_text_from_file(str(temp_path))
            logger.info(f"Extracted {len(text)} characters. Chunking...")
            chunks = chunk_text(text)

            # Add chunks to Pinecone
            logger.info(f"Indexing {len(chunks)} chunks for conversation {conversation_id}...")
            store = VectorStore()
            store.add_chunks(chunks, conversation_id)
            logger.info("Indexing complete.")
        finally:
            temp_path.unlink(missing_ok=True)

        # Persist the upload action in the chat history
        db = SessionLocal()
        try:
            save_message(db, conversation_id, "user", f"Uploaded file: {file.filename}")
        except Exception as e:
            logger.error(f"Failed to save upload message: {e}", exc_info=True)
        finally:
            db.close()

        # We still create a small marker file to know RAG is enabled for this conv
        RAG_STATE_DIR.mkdir(parents=True, exist_ok=True)
        rag_marker = RAG_STATE_DIR / f"{conversation_id}.marker"
        rag_marker.write_text("rag_enabled")

        return {"success": True, "message": f"Successfully indexed {len(chunks)} chunks in Pinecone for conversation {conversation_id}"}
    except HTTPException:
        raise
    except Exception as e:
        return _internal_error(e, "upload")

class ChatRequest(BaseModel):
    message: str
    conversation_id: int
    mode: str = "Chat Agent"
    # NOTE: conversation history is intentionally NOT accepted from the
    # client — it is rebuilt server-side from the database (BUG-12)

# ✅ API endpoint
@app.post("/api/chat")
def chat(req: ChatRequest, current_user_id: int = Depends(get_current_user_id)):
    db = SessionLocal()

    try:
        # Only the conversation's owner may post to it (SEC-01)
        conv = require_owned_conversation(db, req.conversation_id, current_user_id)

        # 🔹 Smart Title Update: If it's a new conversation, generate the title
        # in PARALLEL with the main answer instead of as a blocking LLM call
        # on the request path (BUG-03). Joined before returning so the
        # frontend's post-reply conversation refresh sees the final title.
        title_thread = None
        title_result = {}
        if conv.title == "New Conversation":
            def _gen_title(message=req.message):
                title_result["title"] = generate_thread_title(message)
            title_thread = threading.Thread(target=_gen_title, daemon=True)
            title_thread.start()

        # 🔹 Save user message
        save_message(db, req.conversation_id, "user", req.message)

        # 🔹 Check for RAG context
        rag_context = ""
        rag_marker = RAG_STATE_DIR / f"{req.conversation_id}.marker"
        if rag_marker.exists():
            store = VectorStore()
            results = store.search(req.message, req.conversation_id, top_k=3)
            # Hybrid retrieval (semantic + BM25 keyword). Inject a chunk if it
            # clears the semantic relevance threshold OR is a strong keyword
            # match — top-k alone returns the nearest chunks even when the
            # question is unrelated to the document (BUG-13), while a keyword-
            # only hit (score=None) should still surface exact-term matches.
            relevant = [
                r for r in results
                if (r.get("score") is not None and r["score"] >= RAG_SCORE_THRESHOLD)
                or r.get("keyword_hit")
            ]
            if results:
                logger.info(
                    f"[RAG] conv {req.conversation_id}: scores="
                    f"{[round(r['score'], 3) if r['score'] is not None else None for r in results]} "
                    f"keyword_hits={sum(1 for r in results if r.get('keyword_hit'))} "
                    f"threshold={RAG_SCORE_THRESHOLD} kept={len(relevant)}"
                )
            if relevant:
                # Uploaded-document chunks are untrusted data — delimited so
                # embedded instructions aren't followed by the model (SEC-11).
                rag_context = (
                    f"\n\n{UNTRUSTED_RULES}\n\n"
                    "Context from uploaded documents:\n"
                    + wrap_untrusted("\n".join(r["chunk"] for r in relevant))
                )

        # 🔬 Deep Research → stateless
        if req.mode == "Deep Research":
            reply, sources = deep_agent.run(req.message + rag_context)

        # 🧠 General Chat → stateful
        else:
            history = get_conversation_history(db, req.conversation_id)

            # 📄 A chat turn can be a document request — outright ("write me a
            # PDF on X") or as a follow-up to what was just discussed ("turn
            # that into a report"). The router reads the same history the chat
            # agent gets and returns a seeded brief, so the interview skips
            # whatever the conversation already settled. Answering the turn
            # here would be wrong, so this returns instead of replying: the
            # frontend picks the brief up and runs the document workspace.
            # Artifact mode is exempt — the user already chose their deliverable.
            if req.mode != "Artifact":
                doc_brief = document_agent.brief_from_chat(req.message, history)
                if doc_brief:
                    if title_thread:
                        title_thread.join()
                        new_title = title_result.get("title")
                        if new_title:
                            conv.title = new_title
                            db.commit()
                    # The user's message is already saved above, so the document
                    # stream must not save it again.
                    return {"route": "document", "brief": doc_brief,
                            "reply": "", "sources": [], "artifact": None,
                            "model": CHAT_MODEL}

            prompt_with_context = req.message
            if rag_context:
                prompt_with_context = f"CONTEXT FROM UPLOADED DOCUMENTS:\n{rag_context}\n\nUSER QUESTION: {req.message}"

            # "Artifact" is the general chat agent with the deliverable made
            # mandatory (the + menu's Create Artifact option), not a separate
            # agent — so it keeps history, RAG context and the same reply shape.
            reply, sources = general_agent.run_with_history(
                prompt_with_context,
                history,
                force_artifact=(req.mode == "Artifact"),
            )

        # 🎨 Pull a self-contained artifact (runnable page / code file) out of
        # the reply so the frontend can render it in the canvas instead of
        # inline. No-op when the reply contains no artifact block.
        reply, artifact = extract_artifact(reply)

        # 🔹 Save assistant reply (with sources + artifact as JSON)
        sources_json = json.dumps(sources) if sources else None
        artifact_json = json.dumps(artifact) if artifact else None
        save_message(db, req.conversation_id, "assistant", reply,
                     sources=sources_json, artifact=artifact_json)

        # 🔹 Commit the title generated in parallel (finishes well before the
        # main answer, so this join is effectively free)
        if title_thread:
            title_thread.join()
            new_title = title_result.get("title")
            if new_title:
                conv.title = new_title
                db.commit()

        return {"reply": reply, "sources": sources, "artifact": artifact,
                "model": CHAT_MODEL}

    except HTTPException:
        raise
    except Exception as e:
        return _internal_error(e)

    finally:
        db.close()

# ──────────────────────────────────────────────
# Deep Research — plan preview + streaming execution (Phase 1)
# The frontend shows the plan (left pane) and the live activity feed (right
# pane). Flow: POST /api/research/plan returns a structured, editable plan;
# the user approves/edits it; POST /api/research/stream executes it and streams
# NDJSON progress events. Auth stays on the Bearer header (no EventSource).
# ──────────────────────────────────────────────
class ResearchPlanRequest(BaseModel):
    message: str
    conversation_id: int


@app.post("/api/research/plan")
def research_plan(req: ResearchPlanRequest, current_user_id: int = Depends(get_current_user_id)):
    """Return a structured research plan for the user to approve/edit. No
    gathering happens here — it's a single planning LLM call.

    Also auto-titles a still-"New Conversation" thread here, at plan time —
    the user should see a real title while reviewing/approving the plan,
    not have to wait until research execution starts (which only happens
    after approval, sometimes much later or never if they back out)."""
    db = SessionLocal()
    try:
        conv = require_owned_conversation(db, req.conversation_id, current_user_id)
        conv_is_new = conv.title == "New Conversation"

        # Run the title call in parallel with plan generation (both are LLM
        # calls) and join before returning, so the plan response already
        # carries the final title — same pattern as /api/chat.
        title_result = {}
        title_thread = None
        if conv_is_new:
            def _gen_title(message=req.message):
                title_result["title"] = generate_thread_title(message)
            title_thread = threading.Thread(target=_gen_title, daemon=True)
            title_thread.start()

        plan = deep_agent.research_planner.generate_plan(req.message)

        new_title = None
        if title_thread:
            title_thread.join()
            new_title = title_result.get("title")
            if new_title:
                conv.title = new_title
                db.commit()

        return {"plan": plan, "title": new_title}
    except HTTPException:
        raise
    except Exception as e:
        return _internal_error(e)
    finally:
        db.close()


class ResearchStreamRequest(BaseModel):
    message: str
    conversation_id: int
    plan: dict | None = None  # optional user-approved/edited plan


@app.post("/api/research/stream")
async def research_stream(req: ResearchStreamRequest, current_user_id: int = Depends(get_current_user_id)):
    """Execute deep research and stream NDJSON progress events. The research
    runs in a worker thread; events are drained to the client as they arrive,
    and the final report + full trace are persisted so the run can be replayed."""
    # Ownership is validated up front so an unauthorized caller never starts a run.
    db = SessionLocal()
    try:
        require_owned_conversation(db, req.conversation_id, current_user_id)
    finally:
        db.close()

    emitter = EventEmitter()
    captured = {"report": None, "sources": None, "plan": req.plan, "events": []}

    def worker():
        # Runs the (blocking) pipeline off the event loop; emitter is closed in
        # run_streaming's finally, which ends the drain loop below.
        deep_agent.run_streaming(req.message, emitter, plan=req.plan)

    async def stream():
        loop = asyncio.get_event_loop()

        # Persist the user's request as a message before work begins, and note
        # whether this is a still-untitled conversation.
        conv_is_new = False
        db_user = SessionLocal()
        try:
            save_message(db_user, req.conversation_id, "user", req.message)
            conv = db_user.query(Conversation).filter(
                Conversation.id == req.conversation_id
            ).first()
            conv_is_new = bool(conv and conv.title == "New Conversation")
        except Exception as e:
            logger.error(f"Failed to save research request message: {e}", exc_info=True)
        finally:
            db_user.close()

        # Auto-title a research-first conversation — /api/chat does this but the
        # streaming research path never did, so those threads stayed "New
        # Conversation" in the sidebar. Runs off the streaming path in a thread;
        # a `title` event is emitted once ready so the client updates the list.
        title_result = {}
        title_thread = None
        title_state = {"emitted": False}
        if conv_is_new:
            def _gen_title(message=req.message):
                title_result["title"] = generate_thread_title(message)
            title_thread = threading.Thread(target=_gen_title, daemon=True)
            title_thread.start()

        def _maybe_title_line():
            """If the title is ready and not yet sent, commit it and return the
            NDJSON `title` event line; otherwise None."""
            if title_thread is None or title_state["emitted"] or title_thread.is_alive():
                return None
            title_state["emitted"] = True
            new_title = (title_result.get("title") or "").strip()
            if not new_title:
                return None
            db_t = SessionLocal()
            try:
                conv = db_t.query(Conversation).filter(
                    Conversation.id == req.conversation_id
                ).first()
                if conv and conv.title == "New Conversation":
                    conv.title = new_title
                    db_t.commit()
            except Exception as e:
                logger.error(f"Failed to set research conversation title: {e}", exc_info=True)
            finally:
                db_t.close()
            return json.dumps({
                "type": "title",
                "title": new_title,
                "conversation_id": req.conversation_id,
            }) + "\n"

        threading.Thread(target=worker, daemon=True).start()

        while True:
            evt = await loop.run_in_executor(None, emitter.get)
            if evt is None:
                break
            captured["events"].append(evt)
            if evt["type"] == "plan":
                captured["plan"] = evt.get("plan")
            elif evt["type"] == "report":
                captured["report"] = evt.get("markdown")
                captured["sources"] = evt.get("sources")
            yield json.dumps(evt) + "\n"

            # Surface the generated title as soon as it's ready (interleaved
            # with research events).
            title_line = _maybe_title_line()
            if title_line:
                yield title_line

        # Title generation may still be finishing after the last research event
        # (e.g. a very short run) — wait briefly and flush it before closing.
        if title_thread is not None and not title_state["emitted"]:
            title_thread.join(timeout=15)
            title_line = _maybe_title_line()
            if title_line:
                yield title_line

        # Persist the assistant report + full trace once the stream completes.
        db_save = SessionLocal()
        try:
            trace = json.dumps({"plan": captured["plan"], "events": captured["events"]})
            save_message(
                db_save, req.conversation_id, "assistant",
                captured["report"] or "No result.",
                sources=json.dumps(captured["sources"]) if captured["sources"] else None,
                research_trace=trace,
            )
        except Exception as e:
            logger.error(f"Failed to persist research result: {e}", exc_info=True)
        finally:
            db_save.close()

    return StreamingResponse(stream(), media_type="application/x-ndjson")


# ──────────────────────────────────────────────
# Document agent — interview, then research + write
# The interview is stateless: every /next call carries the whole brief, so
# there is no server-side session to expire and a page reload loses nothing.
# The brief is the user's own input echoed back, so accepting it from the
# client is not a trust boundary — but the conversation is still ownership-
# checked on every call.
# ──────────────────────────────────────────────
class DocumentBrief(BaseModel):
    topic: str = ""
    format: str = "md"
    answers: list[dict] = []
    round: int = 1


class DocumentNextRequest(BaseModel):
    conversation_id: int
    brief: DocumentBrief


@app.post("/api/document/next")
def document_next(req: DocumentNextRequest,
                  current_user_id: int = Depends(get_current_user_id)):
    """Return the next batch of clarifying questions, or ready=true when the
    brief is specific enough to write from. One LLM call, no gathering."""
    db = SessionLocal()
    try:
        require_owned_conversation(db, req.conversation_id, current_user_id)
        return document_agent.next_step(req.brief.model_dump())
    except HTTPException:
        raise
    except Exception as e:
        return _internal_error(e)
    finally:
        db.close()


class DocumentStreamRequest(BaseModel):
    conversation_id: int
    brief: DocumentBrief
    # Set when the run was routed out of /api/chat, which already stored the
    # user's actual wording. Storing the distilled topic on top of it would
    # show the turn twice. Only affects what the transcript looks like — not a
    # trust boundary, and the conversation is still ownership-checked.
    skip_user_message: bool = False


@app.post("/api/document/stream")
async def document_stream(req: DocumentStreamRequest,
                          current_user_id: int = Depends(get_current_user_id)):
    """Research and write the document, streaming NDJSON progress events. Same
    transport and threading as /api/research/stream; the final document and the
    full interview trace are persisted so the run can be replayed."""
    db = SessionLocal()
    try:
        require_owned_conversation(db, req.conversation_id, current_user_id)
    finally:
        db.close()

    brief = req.brief.model_dump()
    emitter = EventEmitter()
    captured = {"markdown": None, "sources": None, "events": []}

    def worker():
        document_agent.run_streaming(brief, emitter)

    async def stream():
        loop = asyncio.get_event_loop()

        # The topic is what the user typed, so it is the message worth storing —
        # the answers are captured in the trace.
        conv_is_new = False
        db_user = SessionLocal()
        try:
            if not req.skip_user_message:
                save_message(db_user, req.conversation_id, "user", brief.get("topic") or "")
            conv = db_user.query(Conversation).filter(
                Conversation.id == req.conversation_id
            ).first()
            conv_is_new = bool(conv and conv.title == "New Conversation")
        except Exception as e:
            logger.error(f"Failed to save document request message: {e}", exc_info=True)
        finally:
            db_user.close()

        # Title a document-first conversation off the streaming path, exactly as
        # the research stream does.
        title_result = {}
        title_thread = None
        title_state = {"emitted": False}
        if conv_is_new:
            def _gen_title(message=brief.get("topic") or ""):
                title_result["title"] = generate_thread_title(message)
            title_thread = threading.Thread(target=_gen_title, daemon=True)
            title_thread.start()

        def _maybe_title_line():
            if title_thread is None or title_state["emitted"] or title_thread.is_alive():
                return None
            title_state["emitted"] = True
            new_title = (title_result.get("title") or "").strip()
            if not new_title:
                return None
            db_t = SessionLocal()
            try:
                conv = db_t.query(Conversation).filter(
                    Conversation.id == req.conversation_id
                ).first()
                if conv and conv.title == "New Conversation":
                    conv.title = new_title
                    db_t.commit()
            except Exception as e:
                logger.error(f"Failed to set document conversation title: {e}", exc_info=True)
            finally:
                db_t.close()
            return json.dumps({
                "type": "title",
                "title": new_title,
                "conversation_id": req.conversation_id,
            }) + "\n"

        threading.Thread(target=worker, daemon=True).start()

        while True:
            evt = await loop.run_in_executor(None, emitter.get)
            if evt is None:
                break
            captured["events"].append(evt)
            if evt["type"] == "document":
                captured["markdown"] = evt.get("markdown")
                captured["sources"] = evt.get("sources")
            yield json.dumps(evt) + "\n"

            title_line = _maybe_title_line()
            if title_line:
                yield title_line

        if title_thread is not None and not title_state["emitted"]:
            title_thread.join(timeout=15)
            title_line = _maybe_title_line()
            if title_line:
                yield title_line

        db_save = SessionLocal()
        try:
            trace = json.dumps({"brief": brief, "events": captured["events"]})
            save_message(
                db_save, req.conversation_id, "assistant",
                captured["markdown"] or "No document was generated.",
                sources=json.dumps(captured["sources"]) if captured["sources"] else None,
                doc_trace=trace,
            )
        except Exception as e:
            logger.error(f"Failed to persist document result: {e}", exc_info=True)
        finally:
            db_save.close()

    return StreamingResponse(stream(), media_type="application/x-ndjson")


# ──────────────────────────────────────────────
# Export — a finished report or document as a downloadable file
# The generator is deterministic (no LLM), stateless and cheap to construct,
# so unlike the chat/research agents it needs no lifespan wiring. Serves both
# producers (deep research and the document agent), hence the neutral path.
# ──────────────────────────────────────────────
generator_agent = DocumentGeneratorAgent()


class ExportRequest(BaseModel):
    conversation_id: int
    format: str                      # md | txt | docx | pdf
    markdown: str = ""               # body; ignored when message_id is given
    title: str = ""
    sources: list[dict] | None = None
    message_id: int | None = None    # preferred: export a stored message by id


@app.post("/api/documents/export")
def export_report(req: ExportRequest, current_user_id: int = Depends(get_current_user_id)):
    """Render report/document markdown as .md/.txt/.docx/.pdf and return it as a
    file download.

    When `message_id` is supplied the content is read from the database, so the
    export is exactly what was saved. The live streaming path has no message id
    yet (the row is written after the stream closes), so it may post the
    markdown it just rendered instead — that content came from this server in
    the same session, and the conversation is still ownership-checked."""
    db = SessionLocal()
    try:
        require_owned_conversation(db, req.conversation_id, current_user_id)

        markdown, title, sources = req.markdown, req.title, req.sources
        if req.message_id is not None:
            # Scoped to the owned conversation, so a foreign message id 404s
            # rather than leaking another user's report (SEC: IDOR).
            msg = (
                db.query(Message)
                .filter(
                    Message.id == req.message_id,
                    Message.conversation_id == req.conversation_id,
                    Message.role == "assistant",
                )
                .first()
            )
            if not msg:
                raise HTTPException(status_code=404, detail="Report not found")
            markdown = msg.content or ""
            if msg.sources:
                try:
                    sources = json.loads(msg.sources)
                except json.JSONDecodeError:
                    sources = None

        if not (markdown or "").strip():
            raise HTTPException(status_code=400, detail="Nothing to export")

        data, mime, filename = generator_agent.generate(
            markdown, title=title, sources=sources, fmt=req.format
        )
        return Response(
            content=data,
            media_type=mime,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                # The filename is derived server-side, but the header is still
                # the browser's cue to save rather than render the bytes.
                "X-Content-Type-Options": "nosniff",
            },
        )
    except HTTPException:
        raise
    except UnsupportedFormatError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FormatUnavailableError as e:
        # The format is real but its library is missing on this deployment.
        logger.error(f"Export dependency missing: {e}")
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        return _internal_error(e)
    finally:
        db.close()


class AbortMessageRequest(BaseModel):
    conversation_id: int
    message: str

@app.post("/api/chat/save_aborted")
def save_aborted_message(req: AbortMessageRequest, current_user_id: int = Depends(get_current_user_id)):
    db = SessionLocal()
    try:
        require_owned_conversation(db, req.conversation_id, current_user_id)
        save_message(db, req.conversation_id, "assistant", req.message)
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        return _internal_error(e)
    finally:
        db.close()

@app.get("/")
def read_root():
    return RedirectResponse(url="/login.html")

app.mount("/", StaticFiles(directory=str(FRONTEND_DIR)), name="frontend")

if __name__ == "__main__":
    import uvicorn
    # PRODUCTION=true in .env disables the auto-reloader (BUG-15)
    uvicorn.run("backend.app:app", host="0.0.0.0", port=8000, reload=not PRODUCTION)

