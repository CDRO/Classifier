"""Native configuration API for the n8n/local classification workflow."""

import asyncio
import json
import base64
import hashlib
import logging
import os
import re
import shutil
import subprocess
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import quote

import httpx
import pymupdf as fitz
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator, model_validator

DEFAULT_DESTINEES: List[str] = []
APP_VERSION = os.getenv("APP_VERSION", "2.0.0")
APP_REVISION = os.getenv("APP_REVISION", "unknown")


def canonicalize_runtime_path(value: object) -> str:
    """Normalize container mount paths without altering real Windows local paths."""
    text = str(value).strip()
    normalized = text.replace("\\", "/")
    if normalized.startswith("/data"):
        return normalized
    return text


def is_container_data_path(value: object) -> bool:
    return canonicalize_runtime_path(value).startswith("/data")


def resolve_runtime_path(env_name: str, fallback: str) -> Path:
    raw_value = os.getenv(env_name, fallback)
    normalized = canonicalize_runtime_path(raw_value)
    return Path(normalized)


SOURCE_PATH = resolve_runtime_path("RAW_INPUT_PATH", "/data/source")
DESTINATION_PATH = resolve_runtime_path("CLASSIFIED_OUTPUT_PATH", "/data/destination")
ARCHIVE_PATH = resolve_runtime_path("PROCESSED_ARCHIVE_PATH", "/data/archive")
DISMISSED_PATH = resolve_runtime_path("DISMISSED_ARCHIVE_PATH", "/data/archive/dismissed")
CONFIG_PATH = resolve_runtime_path("CLASSIFICATION_CONFIG_PATH", "/data/config/classification.json")
DOCUMENTS_PATH = resolve_runtime_path("DOCUMENTS_STATUS_PATH", "/data/config/documents.json")
ANALYSIS_STATUS_PATH = resolve_runtime_path("ANALYSIS_STATUS_PATH", "/data/config/analysis-status.json")
JOB_STATUS_PATH = resolve_runtime_path("JOB_STATUS_PATH", "/data/config/jobs.json")
APPROVAL_AUDIT_PATH = resolve_runtime_path("APPROVAL_AUDIT_PATH", "/data/config/approval-audit.json")
TEMP_PATH = resolve_runtime_path("TEMP_PATH", "/data/temp")
FRONTEND_DIR = Path("/app/frontend") if Path("/app/frontend").exists() else Path(__file__).resolve().parent.parent / "frontend"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_ENDPOINT = os.getenv(
    "GEMINI_ENDPOINT",
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent",
)
GEMINI_TIMEOUT = float(os.getenv("GEMINI_TIMEOUT", "20"))
OCR_LANGUAGES = os.getenv("OCR_LANGUAGES", "eng+deu")
OCR_RENDER_SCALE = float(os.getenv("OCR_RENDER_SCALE", "2"))

logger = logging.getLogger(__name__)


_DESTINEE_PATTERN = re.compile(r"^[^/\\\x00]+$")
_FILENAME_PATTERN = re.compile(r"^[^/\\\x00]+\.pdf$", re.IGNORECASE)
_DATE_PATTERN = re.compile(r"(?:19|20)\d{2}[-/.]\d{1,2}[-/.]\d{1,2}")
_AMOUNT_PATTERN = re.compile(r"(?:€|EUR|USD|GBP|CHF)\s?\d+[\d.,]*|\d+[\d.,]*\s?(?:€|EUR|USD|GBP|CHF)", re.IGNORECASE)
_REFERENCE_PATTERN = re.compile(r"(?:invoice|rechnung|reference|referenz|policy|police|customer|kunden)[\s#:.-]*([A-Z0-9][A-Z0-9./-]{2,})", re.IGNORECASE)
_TOPIC_KEYWORDS: Dict[str, List[str]] = {
    "Invoice": ["invoice", "rechnung", "amount due", "vat", "mwst"],
    "Receipt": ["receipt", "quittung", "kassenbon", "total"],
    "Contract": ["contract", "vertrag", "agreement", "parties"],
    "Insurance": ["insurance", "versicherung", "policy number", "claim"],
    "Tax": ["tax", "steuer", "finanzamt", "tax return"],
}
_LANGUAGE_KEYWORDS: Dict[str, List[str]] = {
    "de": ["der", "die", "das", "und", "von", "für", "rechnung", "attest"],
    "en": ["the", "and", "from", "for", "invoice", "certificate"],
}


class ClassificationConfig(BaseModel):
    """User-editable first-level classification configuration."""

    destinees: List[str] = Field(min_length=0, max_length=50)
    source_roots: List[str] = Field(default_factory=list, min_length=0, max_length=20)
    destination_roots: Dict[str, str] = Field(default_factory=dict)

    @field_validator("destinees")
    @classmethod
    def validate_destinees(cls, values: List[str]) -> List[str]:
        cleaned = [value.strip() for value in values]
        if any(not value for value in cleaned):
            raise ValueError("Destinee names cannot be empty")
        if any(len(value) > 80 for value in cleaned):
            raise ValueError("Destinee names cannot exceed 80 characters")
        if any(not _DESTINEE_PATTERN.fullmatch(value) for value in cleaned):
            raise ValueError("Destinee names cannot contain path separators")
        if len({value.casefold() for value in cleaned}) != len(cleaned):
            raise ValueError("Destinee names must be unique")
        return cleaned

    @field_validator("source_roots")
    @classmethod
    def validate_source_roots(cls, values: List[str]) -> List[str]:
        cleaned = [canonicalize_runtime_path(value).strip() for value in values]
        if any(not value for value in cleaned):
            raise ValueError("Source roots cannot be empty")
        if len({value.casefold() for value in cleaned}) != len(cleaned):
            raise ValueError("Source roots must be unique")
        for value in cleaned:
            if is_container_data_path(value):
                continue
            resolved = Path(value).expanduser()
            if not resolved.exists() or not resolved.is_dir():
                raise ValueError(f"Source root does not exist or is not a directory: {value}")
        return cleaned

    @field_validator("destination_roots")
    @classmethod
    def validate_destination_roots(cls, values: Dict[str, str]) -> Dict[str, str]:
        normalized: Dict[str, str] = {}
        for destinee, path in values.items():
            cleaned_name = str(destinee).strip()
            cleaned_path = canonicalize_runtime_path(path).strip()
            if not cleaned_name:
                raise ValueError("Destination route mappings must include a destinee name")
            if not cleaned_path:
                raise ValueError("Destination route mappings must include a folder path")
            if any(not _DESTINEE_PATTERN.fullmatch(cleaned_name) for _ in [cleaned_name]):
                raise ValueError("Destination route names cannot contain path separators")
            normalized[cleaned_name] = cleaned_path
        return normalized

    @model_validator(mode="after")
    def validate_destination_roots_match_destinees(self):
        configured_names = {value.casefold() for value in self.destinees}
        for destinee in self.destination_roots:
            if destinee.casefold() not in configured_names:
                raise ValueError("Destination route names must match configured destinees")
        return self


class ClassificationResponse(ClassificationConfig):
    """Configuration response including immutable runtime paths."""

    input_path: str
    output_root: str
    source_roots: List[str]
    destination_roots: Dict[str, str]


class FinalizeRequest(BaseModel):
    """Request to route a prepared document to one configured destinee."""

    processing_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-f0-9]+$")
    destinee: str = Field(min_length=1, max_length=80)
    output_filename: Optional[str] = Field(default=None, max_length=180)
    actor: Optional[str] = Field(default=None, max_length=80)
    role: Optional[str] = Field(default=None, max_length=20)

    @field_validator("output_filename")
    @classmethod
    def validate_output_filename(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        cleaned = value.strip()
        if not _FILENAME_PATTERN.fullmatch(cleaned):
            raise ValueError("Output filename must be a single .pdf filename")
        return cleaned

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        normalized = value.strip().lower()
        if normalized not in {"reviewer", "approver", "admin"}:
            raise ValueError("Role must be reviewer, approver, or admin")
        return normalized


class RouteRequest(BaseModel):
    """Resolve a configured route before a document is exported."""

    destinee: str = Field(min_length=1, max_length=80)
    filename: Optional[str] = Field(default=None, max_length=180)

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Filename cannot be empty")
        if not _FILENAME_PATTERN.fullmatch(cleaned):
            raise ValueError("Output filename must be a single .pdf filename")
        return cleaned


class RotateRequest(BaseModel):
    """Requested clockwise rotation for one prepared page."""

    processing_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-f0-9]+$")
    page: int = Field(ge=1)
    rotation: int

    @field_validator("rotation")
    @classmethod
    def validate_rotation(cls, value: int) -> int:
        if value not in {0, 90, 180, 270}:
            raise ValueError("Rotation must be 0, 90, 180, or 270 degrees")
        return value


class SplitRequest(BaseModel):
    """Requested page boundaries for splitting one prepared PDF."""

    processing_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-f0-9]+$")
    split_pages: List[int] = Field(default_factory=list, max_length=100)


class SplitOutput(BaseModel):
    """Filename and explicit destinee for one split PDF part."""

    part: int = Field(ge=1)
    destinee: str = Field(min_length=1, max_length=80)
    output_filename: str = Field(min_length=1, max_length=180)

    @field_validator("output_filename")
    @classmethod
    def validate_output_filename(cls, value: str) -> str:
        cleaned = value.strip()
        if not _FILENAME_PATTERN.fullmatch(cleaned):
            raise ValueError("Output filename must be a single .pdf filename")
        return cleaned


class SplitFinalizeRequest(BaseModel):
    """Finalization choices for all generated split parts."""

    processing_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-f0-9]+$")
    outputs: List[SplitOutput] = Field(min_length=1, max_length=100)


class ReorderPagesRequest(BaseModel):
    """Requested page order for one prepared document."""

    processing_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-f0-9]+$")
    page_order: List[int] = Field(min_length=1, max_length=1000)

    @field_validator("page_order")
    @classmethod
    def validate_page_order(cls, value: List[int]) -> List[int]:
        if not value:
            raise ValueError("Page order cannot be empty")
        if any(page < 1 for page in value):
            raise ValueError("Page order values must be positive")
        return value


class MergeDocumentsRequest(BaseModel):
    """Requests to combine multiple source PDFs into one routed output."""

    documents: List[str] = Field(min_length=2, max_length=10)
    destinee: str = Field(min_length=1, max_length=80)
    output_filename: str = Field(min_length=1, max_length=180)

    @field_validator("documents")
    @classmethod
    def validate_documents(cls, value: List[str]) -> List[str]:
        cleaned = [item.strip() for item in value]
        if any(not item for item in cleaned):
            raise ValueError("Document names cannot be empty")
        if len(set(item.casefold() for item in cleaned)) != len(cleaned):
            raise ValueError("Document names must be unique")
        return cleaned

    @field_validator("output_filename")
    @classmethod
    def validate_output_filename(cls, value: str) -> str:
        cleaned = value.strip()
        if not _FILENAME_PATTERN.fullmatch(cleaned):
            raise ValueError("Output filename must be a single .pdf filename")
        return cleaned


_cleanup_task: Optional[asyncio.Task[None]] = None
_prewarm_task: Optional[asyncio.Task[None]] = None


async def private_retention_worker() -> None:
    """Run periodic cleanup so expired private files are removed even without a fresh user request."""
    while True:
        try:
            expired = cleanup_private_documents()
            if expired:
                logger.info("Expired private documents removed", extra={"count": len(expired), "items": expired})
        except Exception as exc:  # pragma: no cover - defensive guard for background task
            logger.exception("Private retention cleanup failed", exc_info=exc)
        await asyncio.sleep(60)


async def prewarm_worker() -> None:
    """Scan source folders and precompute metadata for pending PDFs before the user opens the web UI."""
    while True:
        try:
            processed = prewarm_pending_documents()
            if processed:
                logger.info("Background prewarm processed pending documents", extra={"count": processed})
        except Exception as exc:  # pragma: no cover - defensive guard for background task
            logger.exception("Background prewarm failed", exc_info=exc)
        await asyncio.sleep(30)


def prewarm_pending_documents(limit: Optional[int] = None) -> int:
    """Prepare and analyze PDFs that are queued but not yet processed, using the existing workflow."""
    scan_input_directory()
    states = read_document_states()
    pending_names: List[str] = []
    for source_root in read_source_roots():
        if not source_root.exists() or not source_root.is_dir():
            continue
        for path in source_root.rglob("*.pdf"):
            if not path.is_file():
                continue
            relative_name = path.relative_to(source_root).as_posix()
            if any(part.startswith(".") for part in path.relative_to(source_root).parts):
                continue
            state = states.get(relative_name)
            if not isinstance(state, dict):
                pending_names.append(relative_name)
                continue
            if state.get("duplicate_of"):
                continue
            if state.get("status") in {"received", "failed"}:
                pending_names.append(relative_name)
                continue
            if state.get("status") == "in_review" and state.get("processing_id") and not state.get("suggested_filename"):
                pending_names.append(relative_name)
                continue

    processed = 0
    for filename in pending_names:
        if limit is not None and processed >= limit:
            break
        try:
            prepared = prepare_document(filename, async_mode=False)
            if isinstance(prepared, Response):
                prepared_data = json.loads(prepared.body.decode("utf-8")) if prepared.body else {}
            else:
                prepared_data = prepared if isinstance(prepared, dict) else {}
            processing_id = prepared_data.get("processing_id")
            if not processing_id:
                continue
            analyze_document(filename, processing_id)
            processed += 1
        except HTTPException:
            continue
        except OSError:
            continue
        except (TypeError, ValueError):
            continue
    return processed


async def startup_event() -> None:
    global _cleanup_task, _prewarm_task
    if _cleanup_task is None or _cleanup_task.done():
        _cleanup_task = asyncio.create_task(private_retention_worker())
    if _prewarm_task is None or _prewarm_task.done():
        _prewarm_task = asyncio.create_task(prewarm_worker())


async def shutdown_event() -> None:
    global _cleanup_task, _prewarm_task
    if _cleanup_task is not None:
        _cleanup_task.cancel()
        try:
            await _cleanup_task
        except asyncio.CancelledError:
            pass
        _cleanup_task = None
    if _prewarm_task is not None:
        _prewarm_task.cancel()
        try:
            await _prewarm_task
        except asyncio.CancelledError:
            pass
        _prewarm_task = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    await startup_event()
    try:
        yield
    finally:
        await shutdown_event()


app = FastAPI(
    title="Document Classifier API",
    version=os.getenv("APP_VERSION", "0.10.0"),
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/")
@app.get("/index.html")
def serve_index() -> Response:
    """Serve the work interface with a cache-busting version stamp."""
    index_path = FRONTEND_DIR / "index.html"
    content = index_path.read_text(encoding="utf-8").replace("__APP_VERSION__", APP_VERSION)
    return Response(content=content, media_type="text/html", headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"})


@app.get("/config")
@app.get("/config.html")
def serve_config_page() -> Response:
    """Serve the separate configuration interface for routing rules."""
    config_path = FRONTEND_DIR / "config.html"
    content = config_path.read_text(encoding="utf-8").replace("__APP_VERSION__", APP_VERSION)
    return Response(content=content, media_type="text/html", headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"})


def read_config() -> List[str]:
    if not CONFIG_PATH.exists():
        return list(DEFAULT_DESTINEES)
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return ClassificationConfig.model_validate(data).destinees
    except (OSError, json.JSONDecodeError, ValueError):
        return list(DEFAULT_DESTINEES)


def read_source_roots() -> List[Path]:
    default_roots = [SOURCE_PATH]
    if not CONFIG_PATH.exists():
        return default_roots
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        config = ClassificationConfig.model_validate(data)
        configured = []
        for value in config.source_roots:
            normalized = canonicalize_runtime_path(value)
            if is_container_data_path(normalized):
                configured.append(Path(normalized))
            else:
                configured.append(Path(normalized).expanduser())
        if configured:
            return configured
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    return default_roots


def read_document_states() -> dict:
    if not DOCUMENTS_PATH.exists():
        return {}
    try:
        data = json.loads(DOCUMENTS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def write_document_state(filename: str, status: str, **details: object) -> None:
    states = read_document_states()
    existing = states.get(filename, {}) if isinstance(states.get(filename), dict) else {}
    states[filename] = {**existing, "status": status, **details}
    DOCUMENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOCUMENTS_PATH.write_text(json.dumps(states, indent=2), encoding="utf-8")


def cleanup_private_documents(now: Optional[datetime] = None) -> List[str]:
    """Delete private files from source/destination and remove matching log records after the retention window expires."""
    current_time = now or datetime.now(timezone.utc)
    states = read_document_states()
    expired_files: List[str] = []

    for filename, details in list(states.items()):
        if not isinstance(details, dict) or not details.get("private"):
            continue
        delete_after = details.get("delete_after")
        if not delete_after:
            continue
        try:
            deadline = datetime.fromisoformat(str(delete_after).replace("Z", "+00:00"))
        except ValueError:
            continue
        if current_time < deadline:
            continue

        expired_files.append(filename)
        relative_name = None
        try:
            relative_name = normalize_relative_document_path(filename)
        except HTTPException:
            relative_name = None

        candidate_roots = [SOURCE_PATH, ARCHIVE_PATH, DESTINATION_PATH]
        for root in candidate_roots:
            if relative_name is not None:
                candidate = root / relative_name
                if candidate.exists() and candidate.is_file():
                    candidate.unlink()
            if root == DESTINATION_PATH:
                for nested in root.rglob(filename):
                    if nested.is_file():
                        nested.unlink()
            elif root == SOURCE_PATH:
                source_candidate = root / filename
                if source_candidate.exists() and source_candidate.is_file():
                    source_candidate.unlink()

        for candidate in (
            details.get("destination_path"),
            details.get("archive_path"),
            details.get("source_path"),
        ):
            if not candidate:
                continue
            try:
                path = Path(str(candidate))
                if path.exists() and path.is_file():
                    path.unlink()
            except (TypeError, ValueError, OSError):
                continue

        states.pop(filename, None)

    if expired_files:
        DOCUMENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        DOCUMENTS_PATH.write_text(json.dumps(states, indent=2), encoding="utf-8")

        jobs = read_job_store()
        for job_id, job in list(jobs.items()):
            if isinstance(job, dict) and job.get("filename") in expired_files:
                jobs.pop(job_id, None)
        JOB_STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
        JOB_STATUS_PATH.write_text(json.dumps(jobs, indent=2), encoding="utf-8")

        audit = read_approval_audit()
        entries = audit.get("entries", [])
        audit["entries"] = [
            entry for entry in entries if not isinstance(entry, dict) or entry.get("filename") not in expired_files
        ]
        APPROVAL_AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        APPROVAL_AUDIT_PATH.write_text(json.dumps(audit, indent=2), encoding="utf-8")

    return expired_files


def cached_analysis_result(filename: str, processing_path: Path) -> Optional[dict]:
    states = read_document_states()
    state = states.get(filename)
    if not isinstance(state, dict):
        return None
    if state.get("sha256") != calculate_file_hash(processing_path):
        return None
    cached = {
        key: value for key, value in state.items()
        if key not in {"status", "sha256", "duplicate_of", "destinee", "destination_path", "archive_path", "processing_id", "reason", "dismissed_path"}
    }
    if not cached.get("suggested_filename"):
        return None
    return cached


def normalize_relative_document_path(filename: str) -> Path:
    relative_path = Path(filename.replace("\\", "/"))
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise HTTPException(status_code=404, detail="Document not found")
    if not relative_path.name or relative_path.name in {"", ".", ".."}:
        raise HTTPException(status_code=404, detail="Document not found")
    return relative_path


def resolve_source_document(filename: str) -> Path:
    relative_path = normalize_relative_document_path(filename)
    for source_root in read_source_roots():
        source_root_resolved = source_root.resolve()
        document_path = (source_root_resolved / relative_path).resolve()
        if document_path.is_relative_to(source_root_resolved) and document_path.is_file() and document_path.suffix.casefold() == ".pdf":
            return document_path
    raise HTTPException(status_code=404, detail="Document not found")


def relative_archive_path(path: Path) -> Path:
    try:
        return ARCHIVE_PATH / path.relative_to(SOURCE_PATH)
    except ValueError:
        return ARCHIVE_PATH / path.name


def calculate_file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_analysis_status() -> dict:
    if not ANALYSIS_STATUS_PATH.exists():
        return {"available": bool(GEMINI_API_KEY), "message": None, "retry_after": None}
    try:
        data = json.loads(ANALYSIS_STATUS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"available": bool(GEMINI_API_KEY)}
    except (OSError, json.JSONDecodeError):
        return {"available": bool(GEMINI_API_KEY), "message": None, "retry_after": None}


def write_analysis_status(available: bool, message: Optional[str] = None, retry_after: Optional[str] = None) -> None:
    ANALYSIS_STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    ANALYSIS_STATUS_PATH.write_text(
        json.dumps({"available": available, "message": message, "retry_after": retry_after}, indent=2),
        encoding="utf-8",
    )


def read_approval_audit() -> dict:
    if not APPROVAL_AUDIT_PATH.exists():
        return {"entries": []}
    try:
        data = json.loads(APPROVAL_AUDIT_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("entries"), list):
            return data
        return {"entries": []}
    except (OSError, json.JSONDecodeError):
        return {"entries": []}


def append_approval_audit(action: str, filename: str, actor: Optional[str], role: Optional[str], **details: object) -> dict:
    audit = read_approval_audit()
    entry = {
        "action": action,
        "filename": filename,
        "actor": actor or "unknown",
        "role": role or "unknown",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **details,
    }
    audit.setdefault("entries", []).append(entry)
    APPROVAL_AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    APPROVAL_AUDIT_PATH.write_text(json.dumps(audit, indent=2), encoding="utf-8")
    return entry


def read_job_store() -> dict:
    if not JOB_STATUS_PATH.exists():
        return {}
    try:
        data = json.loads(JOB_STATUS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def write_job_record(job_id: str, status: str, **details: object) -> None:
    jobs = read_job_store()
    job = jobs.get(job_id)
    updated = {} if not isinstance(job, dict) else dict(job)
    updated.update({"job_id": job_id, "status": status, **details})
    jobs[job_id] = updated
    JOB_STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    JOB_STATUS_PATH.write_text(json.dumps(jobs, indent=2), encoding="utf-8")


def create_job_record(filename: str, processing_id: str, route_details: dict, page_count: int) -> str:
    job_id = uuid.uuid4().hex
    job_timestamp = datetime.now(timezone.utc).isoformat()
    write_job_record(
        job_id,
        "queued",
        filename=filename,
        processing_id=processing_id,
        route=route_details.get("route"),
        queue_status=route_details.get("queue_status"),
        processing_strategy=route_details.get("processing_strategy"),
        processing_profile=route_details.get("processing_profile"),
        quality_score=route_details.get("quality_score"),
        recommended_provider=route_details.get("recommended_provider"),
        local_classification=route_details.get("local_classification"),
        page_count=page_count,
        retry_count=0,
        created_at=job_timestamp,
        updated_at=job_timestamp,
    )
    return job_id


def summarize_jobs() -> dict:
    jobs = read_job_store()
    status_breakdown = {"queued": 0, "processing": 0, "ready": 0, "failed": 0}
    status_names = {"queued", "processing", "ready", "failed"}
    latency_total = 0.0
    failure_count = 0
    local_count = 0
    ai_count = 0
    job_rows: List[dict] = []

    for job in jobs.values():
        if not isinstance(job, dict):
            continue
        status = str(job.get("status", "unknown")).strip().lower()
        if status in status_names:
            status_breakdown[status] += 1

        profile = job.get("processing_profile") if isinstance(job.get("processing_profile"), dict) else {}
        latency = profile.get("median_latency_ms")
        if isinstance(latency, (int, float)):
            latency_total += float(latency)

        strategy = str(job.get("processing_strategy", "")).strip().lower()
        recommended_provider = str(job.get("recommended_provider", "")).strip().lower()
        if strategy in {"local-rule-engine", "local-preprocessing"} or recommended_provider == "local":
            local_count += 1
        elif strategy in {"gemini-enrichment", "ocr-fallback"} or recommended_provider == "gemini":
            ai_count += 1

        if status == "failed":
            failure_count += 1

        classification = job.get("local_classification") if isinstance(job.get("local_classification"), dict) else {}
        job_rows.append({
            "job_id": job.get("job_id"),
            "filename": job.get("filename"),
            "status": status,
            "route": job.get("route"),
            "processing_strategy": job.get("processing_strategy"),
            "queue_status": job.get("queue_status"),
            "quality_score": job.get("quality_score"),
            "recommended_provider": job.get("recommended_provider"),
            "retry_count": job.get("retry_count", 0),
            "created_at": job.get("created_at"),
            "updated_at": job.get("updated_at"),
            "confidence": classification.get("confidence"),
            "destinee": classification.get("destinee"),
            "intent": classification.get("intent"),
        })

    total_jobs = len(job_rows)
    job_rows.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    summary = {
        "total_jobs": total_jobs,
        "queued": status_breakdown["queued"],
        "processing": status_breakdown["processing"],
        "ready": status_breakdown["ready"],
        "failed": status_breakdown["failed"],
        "status_breakdown": status_breakdown,
        "average_latency_ms": round(latency_total / total_jobs, 2) if total_jobs else 0.0,
        "failure_rate": round(failure_count / total_jobs, 4) if total_jobs else 0.0,
        "local_resolution_rate": round(local_count / total_jobs, 4) if total_jobs else 0.0,
        "ai_resolution_rate": round(ai_count / total_jobs, 4) if total_jobs else 0.0,
        "jobs": job_rows,
    }
    return summary


def extract_page_text(page: object) -> tuple[str, bool]:
    text = page.get_text()
    if text.strip():
        return text, False
    return "", False


def extract_page_text_with_ocr(page: object) -> tuple[str, bool]:
    text = page.get_text()
    if text.strip():
        return text, False
    image = page.get_pixmap(
        matrix=fitz.Matrix(OCR_RENDER_SCALE, OCR_RENDER_SCALE),
        colorspace=fitz.csGRAY,
        alpha=False,
    ).tobytes("png")
    try:
        result = subprocess.run(
            ["tesseract", "stdin", "stdout", "-l", OCR_LANGUAGES, "--psm", "3", "--dpi", "300"],
            input=image,
            capture_output=True,
            check=False,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "", False
    if result.returncode != 0:
        return "", False
    return result.stdout.decode("utf-8", errors="replace"), True


def infer_local_classification(page_texts: List[str]) -> dict:
    """Infer likely intent and destinee using local text patterns before Gemini is consulted."""
    text = "\n".join(page_texts).lower()
    if not text.strip():
        configured_destinees = read_config()
        fallback_destinee = configured_destinees[0] if configured_destinees else "Unassigned"
        return {
            "intent": "unknown",
            "destinee": fallback_destinee,
            "confidence": 0.15,
            "matched_terms": [],
            "reason": "no readable text was extracted",
        }

    rule_map = {
        "invoice": {
            "keywords": ["invoice", "rechnung", "amount due", "vat", "mwst", "payment due", "zahllast"],
            "destinees": ["Finance", "Accounting", "Billing"],
        },
        "tax": {
            "keywords": ["tax", "steuer", "tax return", "finanzamt"],
            "destinees": ["Finance", "Tax"],
        },
        "contract": {
            "keywords": ["contract", "vertrag", "agreement", "parties"],
            "destinees": ["Legal", "Contracts"],
        },
        "receipt": {
            "keywords": ["receipt", "quittung", "kassenbon", "total"],
            "destinees": ["Operations", "Finance"],
        },
        "letter": {
            "keywords": ["letter", "brief", "dear", "hello"],
            "destinees": ["Operations", "Legal"],
        },
    }

    best_intent = "unknown"
    best_destinee = "Unassigned"
    best_confidence = 0.25
    matched_terms: List[str] = []

    configured_destinees = read_config()
    preferred_destinees = {value.casefold(): value for value in configured_destinees}

    for intent, rule in rule_map.items():
        hits = [keyword for keyword in rule["keywords"] if keyword in text]
        if not hits:
            continue
        for candidate in rule["destinees"]:
            normalized = candidate.casefold()
            if normalized in preferred_destinees:
                best_destinee = preferred_destinees[normalized]
                break
        else:
            best_destinee = configured_destinees[0] if configured_destinees else "Unassigned"
        best_intent = intent
        matched_terms = hits
        best_confidence = 0.82 if len(hits) >= 2 else 0.68
        break

    if best_intent == "unknown":
        best_destinee = configured_destinees[0] if configured_destinees else "Unassigned"
        best_confidence = 0.35

    return {
        "intent": best_intent,
        "destinee": best_destinee,
        "confidence": round(best_confidence, 2),
        "matched_terms": matched_terms,
        "reason": f"matched local intent {best_intent}" if best_intent != "unknown" else "no decisive keyword match",
    }


def determine_document_route(page_texts: List[str], ocr_used: bool = False) -> dict:
    """Choose a single, explicit processing strategy for readable, OCR, or AI-enriched documents."""
    combined_text = "\n".join(page_texts)
    readable = bool(combined_text.strip())
    tokens = re.findall(r"\b\w+\b", combined_text)
    word_count = len(tokens)
    unique_words = len({token.casefold() for token in tokens if len(token) > 2})
    text_density = min(1.0, len(combined_text) / 6000)
    quality_score = min(1.0, max(0.05, text_density * 0.7 + (0.3 if not ocr_used else 0.15))) if readable else 0.0
    looks_like_noise = word_count > 0 and unique_words <= 2 and re.search(r"\b(?:x|y|z|lorem|ipsum)\b", combined_text, re.IGNORECASE) is not None
    local_classification = infer_local_classification(page_texts)

    if not readable:
        processing_strategy = "ocr-fallback"
        route = "ocr-fallback"
        queue_status = "awaiting_ocr"
        recommended_provider = "gemini" if GEMINI_API_KEY else "local"
        processing_profile = {
            "provider": "tesseract",
            "median_latency_ms": 2300,
            "estimated_cost_usd": 0.0,
            "benchmark_source": "local-ocr",
        }
    else:
        route = "local-preprocessing"
        queue_status = "ready_for_review"
        if not ocr_used and (quality_score >= 0.25 or unique_words >= 4) and not looks_like_noise:
            processing_strategy = "local-rule-engine"
            recommended_provider = "local"
            processing_profile = {
                "provider": "local",
                "median_latency_ms": 180,
                "estimated_cost_usd": 0.0,
                "benchmark_source": "local-rule-engine",
            }
        else:
            processing_strategy = "gemini-enrichment"
            recommended_provider = "gemini"
            processing_profile = {
                "provider": "gemini",
                "median_latency_ms": 1800,
                "estimated_cost_usd": 0.00015,
                "benchmark_source": "gemini-enrichment",
            }

    return {
        "readable": readable,
        "route": route,
        "queue_status": queue_status,
        "processing_strategy": processing_strategy,
        "local_classification": local_classification,
        "quality_score": round(max(0.0, min(1.0, quality_score)), 2),
        "recommended_provider": recommended_provider,
        "processing_profile": processing_profile,
    }


def analyze_text(text: str, filename: str) -> dict:
    normalized_text = text.casefold()
    language_scores = {
        language: sum(normalized_text.count(f" {keyword} ") for keyword in keywords)
        for language, keywords in _LANGUAGE_KEYWORDS.items()
    }
    language = max(language_scores, key=language_scores.get) if max(language_scores.values(), default=0) else "unknown"
    scores = {
        topic: sum(normalized_text.count(keyword.casefold()) for keyword in keywords)
        for topic, keywords in _TOPIC_KEYWORDS.items()
    }
    topic = max(scores, key=scores.get) if max(scores.values(), default=0) else "Document"
    score = scores.get(topic, 0)
    confidence = min(0.95, 0.45 + (score * 0.1)) if score else 0.25
    signals = [f"Matched topic keywords for {topic}: {score}"] if score else ["No local topic keywords matched"]
    if language != "unknown":
        signals.append(f"Detected language: {language}")
    dates = [match.replace("/", "-").replace(".", "-") for match in _DATE_PATTERN.findall(text)]
    date = dates[0] if dates else "undated"
    amounts = _AMOUNT_PATTERN.findall(text)
    references = _REFERENCE_PATTERN.findall(text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    title = lines[0][:120] if lines else Path(filename).stem
    party_match = re.search(
        r"(?:from|vendor|seller|company|sender|von|anbieter|firma)\s*[:\-]?\s*([^\n,]{2,80})",
        text,
        re.IGNORECASE,
    )
    party = party_match.group(1).strip() if party_match else None
    source_stem = Path(filename).stem
    safe_stem = re.sub(r"[^A-Za-z0-9]+", "-", source_stem).strip("-") or "document"
    suggested_filename = f"{date}_{topic}_{safe_stem}.pdf"
    summary = " ".join(text.split())[:240] or "No readable text was extracted from this PDF."
    return {
        "topic": topic,
        "category": topic,
        "language": language,
        "confidence": round(confidence, 2),
        "date": date,
        "dates": dates[:10],
        "amounts": amounts[:10],
        "reference_numbers": references[:10],
        "party": party,
        "title": title,
        "summary": summary,
        "suggested_filename": suggested_filename,
        "analysis_source": "local",
        "signals": signals,
    }


def analyze_with_gemini(text: str, filename: str, pdf: object = None, layout: Optional[dict] = None) -> Optional[dict]:
    if not GEMINI_API_KEY:
        return None
    prompt = (
        "Analyze this document text and return JSON only with these fields: "
        "language (ISO 639-1 code), category (short noun in the document language), "
        "title (short title in the document language), date (YYYY-MM-DD or undated), "
        "party (sender/vendor/person or null), summary (one sentence), "
        "confidence (number from 0 to 1), suggested_filename (single safe .pdf filename using words from the document language). "
        "Do not translate the filename into English unless the document is in English.\n\n"
        f"Original filename: {filename}\nTop-of-page layout clues:\n{layout or {}}\nDocument text:\n{text[:12000]}"
    )
    parts = [{"text": prompt}]
    if not text.strip() and pdf is not None:
        for page in list(pdf)[:4]:
            image = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False).tobytes("jpeg")
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(image).decode("ascii")}})
    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {"response_mime_type": "application/json"},
    }
    try:
        with httpx.Client(timeout=GEMINI_TIMEOUT) as client:
            response = client.post(
                GEMINI_ENDPOINT,
                headers={"x-goog-api-key": GEMINI_API_KEY},
                json=payload,
            )
            if response.status_code == 429:
                retry_after = response.headers.get("retry-after")
                try:
                    retry_after = response.json().get("error", {}).get("details", [{}])[-1].get("retryDelay") or retry_after
                except (IndexError, TypeError, ValueError, json.JSONDecodeError):
                    pass
                write_analysis_status(
                    False,
                    "Gemini quota or rate limit reached. Local analysis is active until Gemini is available again.",
                    retry_after,
                )
                return None
            response.raise_for_status()
            candidates = response.json().get("candidates", [])
            response_text = candidates[0]["content"]["parts"][0]["text"]
            result = json.loads(response_text)
        if not isinstance(result, dict):
            return None
        local_result = analyze_text(text, filename)
        category = str(result.get("category") or local_result["category"])[:80]
        suggested_filename = str(result.get("suggested_filename") or local_result["suggested_filename"]).strip()
        if not _FILENAME_PATTERN.fullmatch(suggested_filename):
            suggested_filename = local_result["suggested_filename"]
        confidence = float(result.get("confidence", local_result["confidence"]))
        write_analysis_status(True)
        return {
            **local_result,
            "topic": category,
            "category": category,
            "language": str(result.get("language") or local_result["language"])[:10],
            "title": str(result.get("title") or local_result["title"])[:120],
            "date": str(result.get("date") or local_result["date"])[:20],
            "dates": result.get("dates") or local_result["dates"],
            "amounts": result.get("amounts") or local_result["amounts"],
            "reference_numbers": result.get("reference_numbers") or local_result["reference_numbers"],
            "party": result.get("party") or local_result["party"],
            "summary": str(result.get("summary") or local_result["summary"])[:240],
            "confidence": round(max(0.0, min(1.0, confidence)), 2),
            "suggested_filename": suggested_filename,
            "analysis_source": "gemini",
            "signals": ["Gemini analyzed document content"],
        }
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
        write_analysis_status(
            False,
            "Gemini is temporarily unavailable. Local analysis is active.",
        )
        return None


def read_destination_roots() -> Dict[str, str]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        config = ClassificationConfig.model_validate(data)
        configured = {
            destinee: canonicalize_runtime_path(path)
            for destinee, path in config.destination_roots.items()
            if destinee.casefold() in {value.casefold() for value in config.destinees}
        }
        return configured
    except (OSError, json.JSONDecodeError, ValueError):
        return {}


def response_for(destinees: List[str]) -> ClassificationResponse:
    ensure_destinee_directories(destinees)
    source_roots = [canonicalize_runtime_path(str(path)) for path in read_source_roots()]
    destination_roots = {destinee: canonicalize_runtime_path(path) for destinee, path in read_destination_roots().items()}
    return ClassificationResponse(
        destinees=destinees,
        input_path=source_roots[0] if source_roots else canonicalize_runtime_path(str(SOURCE_PATH)),
        output_root=f"{canonicalize_runtime_path(str(DESTINATION_PATH))}/",
        source_roots=source_roots,
        destination_roots=destination_roots,
    )


def resolve_route_for_destinee(destinee: str, filename: Optional[str] = None) -> dict:
    """Resolve the effective output root for a configured destinee and filename."""
    configured_destinees = read_config()
    matching_destinee = next(
        (value for value in configured_destinees if value.casefold() == destinee.casefold()),
        None,
    )
    if matching_destinee is None:
        raise HTTPException(status_code=400, detail=f"Destinee '{destinee}' is not configured")

    root = Path(read_destination_roots().get(matching_destinee, str(DESTINATION_PATH / matching_destinee))).expanduser()
    root.mkdir(parents=True, exist_ok=True)

    safe_name = "document.pdf"
    if filename:
        candidate = Path(filename.strip()).name
        if candidate and candidate not in {".", ".."}:
            safe_name = candidate

    destination_path = (root / safe_name).resolve()
    if str(destination_path).startswith(str(root.resolve())) or str(destination_path) == str(root.resolve()):
        return {
            "resolved_destinee": matching_destinee,
            "root_path": str(root),
            "destination_path": str(destination_path),
        }
    raise HTTPException(status_code=400, detail="The requested filename would escape the configured output root")


def move_or_archive_document(document_path: Path) -> Path:
    archived_file = relative_archive_path(document_path)
    archived_file.parent.mkdir(parents=True, exist_ok=True)
    if archived_file.exists():
        raise HTTPException(status_code=409, detail=f"An archived document with this name already exists: {archived_file.name}")
    shutil.move(str(document_path), archived_file)
    return archived_file


def ensure_destinee_directories(destinees: List[str]) -> None:
    DESTINATION_PATH.mkdir(parents=True, exist_ok=True)
    for destinee in destinees:
        (DESTINATION_PATH / destinee).mkdir(exist_ok=True)


class PrivateDocumentRequest(BaseModel):
    """Request model for privacy retention scheduling."""

    private: bool = True
    delete_after_minutes: int = Field(default=60, ge=1, le=1440)


def extract_layout_metadata(pdf: object) -> dict:
    """Extract stable positional clues without exposing the original PDF layout."""
    first_page = pdf[0] if len(pdf) else None
    if first_page is None:
        return {"first_page_title": None, "top_text": "", "page_text_lengths": []}
    blocks = first_page.get_text("blocks")
    blocks.sort(key=lambda block: (block[1], block[0]))
    top_text = " ".join(block[4].strip() for block in blocks if block[1] < first_page.rect.height * 0.3)
    first_page_title = top_text.splitlines()[0][:120] if top_text else None
    return {
        "first_page_title": first_page_title,
        "top_text": top_text[:500],
        "page_text_lengths": [len(page.get_text()) for page in pdf],
    }


@app.get("/api/ingestion/status")
def ingestion_status() -> dict:
    roots = read_source_roots()
    return {
        "provider": "n8n",
        "input_path": str(roots[0]) if roots else str(SOURCE_PATH),
        "source_roots": [str(path) for path in roots],
        "ready": any(path.exists() and path.is_dir() for path in roots),
    }


@app.get("/api/analysis/status")
def analysis_status() -> dict:
    """Report the configured analysis provider without exposing credentials."""
    current = read_analysis_status()
    return {
        "gemini_configured": bool(GEMINI_API_KEY),
        "endpoint": GEMINI_ENDPOINT,
        "fallback": "local",
        "available": current.get("available", bool(GEMINI_API_KEY)),
        "message": current.get("message"),
        "retry_after": current.get("retry_after"),
    }


@app.get("/api/version")
def version_status() -> dict:
    """Return the non-secret version embedded in the running container."""
    return {"version": APP_VERSION, "revision": APP_REVISION}


@app.get("/api/config", response_model=ClassificationResponse)
@app.get("/api/classification/config", response_model=ClassificationResponse)
def get_classification_config() -> ClassificationResponse:
    return response_for(read_config())


@app.post("/api/config", response_model=ClassificationResponse)
@app.post("/api/classification/config", response_model=ClassificationResponse)
def update_classification_config(config: ClassificationConfig) -> ClassificationResponse:
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(config.model_dump_json(indent=2), encoding="utf-8")
        ensure_destinee_directories(config.destinees)
        for destinee, destination_path in config.destination_roots.items():
            Path(destination_path).mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise HTTPException(status_code=500, detail="Unable to persist classification configuration") from exc
    return response_for(config.destinees)


@app.post("/api/classification/route")
def route_document(request: RouteRequest) -> dict:
    """Return the resolved path for the selected destinee before writing output files."""
    return resolve_route_for_destinee(request.destinee, request.filename)


@app.post("/api/classification/prewarm")
def trigger_prewarm() -> dict:
    """Run the same scan/prepare/analyze workflow in the background for any pending PDFs."""
    return {"processed": prewarm_pending_documents(), "status": "ok"}


@app.post("/api/documents/{filename:path}/private")
def mark_document_private(filename: str, request: PrivateDocumentRequest) -> dict:
    """Mark a document as private and schedule automatic deletion after the configured retention window."""
    try:
        relative_path = normalize_relative_document_path(filename)
    except HTTPException:
        raise HTTPException(status_code=404, detail="Document not found")

    source_path = (SOURCE_PATH / relative_path).resolve()
    destination_matches = list(DESTINATION_PATH.rglob(filename)) if DESTINATION_PATH.exists() else []
    if not source_path.exists() and not destination_matches:
        raise HTTPException(status_code=404, detail="Document not found")

    delete_after = datetime.now(timezone.utc) + timedelta(minutes=request.delete_after_minutes)
    document_details = read_document_states().get(filename, {})
    if not isinstance(document_details, dict):
        document_details = {}
    document_details.update({
        "private": bool(request.private),
        "private_at": datetime.now(timezone.utc).isoformat(),
        "delete_after": delete_after.isoformat(),
        "source_path": str(source_path),
        "destination_path": str(destination_matches[0]) if destination_matches else document_details.get("destination_path"),
    })
    write_document_state(filename, "private", **document_details)
    return {
        "status": "private",
        "filename": filename,
        "delete_after": delete_after.isoformat(),
        "delete_after_minutes": request.delete_after_minutes,
    }


@app.post("/api/classification/scan")
def scan_input_directory() -> dict:
    cleanup_private_documents()
    source_roots = read_source_roots()
    if not any(root.exists() and root.is_dir() for root in source_roots):
        raise HTTPException(status_code=503, detail="n8n input directory is unavailable")
    states = read_document_states()
    classified_hashes = {
        details.get("sha256"): filename
        for filename, details in states.items()
        if isinstance(details, dict)
        and details.get("status") == "classified"
        and details.get("sha256")
    }
    if ARCHIVE_PATH.exists():
        for archived_file in ARCHIVE_PATH.rglob("*.pdf"):
            if archived_file.is_file() and not any(part.startswith(".") for part in archived_file.relative_to(ARCHIVE_PATH).parts):
                classified_hashes.setdefault(calculate_file_hash(archived_file), archived_file.relative_to(ARCHIVE_PATH).as_posix())
    pdfs = []
    seen_paths = set()
    for source_root in source_roots:
        if not source_root.exists() or not source_root.is_dir():
            continue
        for path in source_root.rglob("*.pdf"):
            if not path.is_file():
                continue
            relative_path = path.relative_to(source_root)
            if any(part.startswith(".") for part in relative_path.parts):
                continue
            key = str(relative_path.as_posix()) + "@" + str(source_root)
            if key in seen_paths:
                continue
            seen_paths.add(key)
            pdfs.append((relative_path, path, source_root))
    for relative_path, path, _source_root in pdfs:
        relative_name = relative_path.as_posix()
        file_hash = calculate_file_hash(path)
        if relative_name not in states:
            duplicate_of = classified_hashes.get(file_hash)
            states[relative_name] = {
                "status": "duplicate" if duplicate_of else "received",
                "sha256": file_hash,
                **({"duplicate_of": duplicate_of} if duplicate_of else {}),
            }
        elif states[relative_name].get("sha256") != file_hash:
            states[relative_name]["sha256"] = file_hash
    DOCUMENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOCUMENTS_PATH.write_text(json.dumps(states, indent=2), encoding="utf-8")
    files = [
        {
            "name": relative_path.as_posix(),
            "path": str(path),
            "size": path.stat().st_size,
            "status": states.get(relative_name, {}).get("status", "received"),
            "sha256": states.get(relative_name, {}).get("sha256"),
            "duplicate_of": states.get(relative_name, {}).get("duplicate_of"),
        }
        for relative_path, path, _source_root in pdfs
        for relative_name in [relative_path.as_posix()]
    ]
    files.sort(key=lambda file: file["name"].casefold())
    return {"files": files, "count": len(files)}


@app.get("/api/documents/history")
def document_history() -> dict:
    """Return known documents and their persisted lifecycle states."""
    states = read_document_states()
    documents = [
        {"name": filename, **details}
        for filename, details in states.items()
        if isinstance(details, dict)
    ]
    documents.sort(key=lambda document: document["name"].casefold())
    return {"documents": documents, "count": len(documents)}


@app.get("/api/documents/{filename:path}/file")
def serve_document(filename: str):
    """Serve one source PDF for browser review without exposing other paths."""
    try:
        document_path = resolve_source_document(filename)
    except HTTPException:
        raise HTTPException(status_code=404, detail="Document not found")
    return FileResponse(
        document_path,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(document_path.name)}"
        },
    )


@app.get("/api/documents/{filename:path}")
def get_document(filename: str) -> dict:
    """Return metadata for one completed PDF in the n8n input directory."""
    try:
        document_path = resolve_source_document(filename)
    except HTTPException:
        archived_path = (ARCHIVE_PATH / filename).resolve()
        if not archived_path.is_relative_to(ARCHIVE_PATH.resolve()) or not archived_path.is_file() or archived_path.suffix.casefold() != ".pdf":
            raise HTTPException(status_code=404, detail="Document not found")
        document_path = archived_path
    try:
        metadata = document_path.stat()
    except OSError as exc:
        raise HTTPException(status_code=404, detail="Document not found") from exc
    state = read_document_states().get(filename, {})
    return {
        "name": filename,
        "path": str(document_path),
        "size": metadata.st_size,
        "modified": metadata.st_mtime,
        "status": state.get("status", "received"),
        **{key: value for key, value in state.items() if key != "status"},
    }


def prepared_file(processing_id: str) -> Path:
    processing_path = (TEMP_PATH / "processing" / processing_id / "original.pdf").resolve()
    processing_root = (TEMP_PATH / "processing").resolve()
    if processing_path.parent.parent != processing_root or not processing_path.is_file():
        raise HTTPException(status_code=404, detail="Prepared document not found")
    return processing_path


@app.get("/api/processing/{processing_id}/file")
def serve_prepared_document(processing_id: str):
    """Serve the current prepared PDF, including review rotations."""
    processing_path = prepared_file(processing_id)
    return FileResponse(processing_path, media_type="application/pdf")


@app.get("/api/processing/{processing_id}/pages/{page}/thumbnail")
def serve_page_thumbnail(processing_id: str, page: int):
    """Render one prepared page as a JPEG thumbnail for review."""
    processing_path = prepared_file(processing_id)
    thumbnail_path = processing_path.parent / f"page_{page:04d}.jpg"
    try:
        with fitz.open(processing_path) as pdf:
            if page < 1 or page > pdf.page_count:
                raise HTTPException(status_code=404, detail="Page not found")
            if not thumbnail_path.exists():
                pixmap = pdf[page - 1].get_pixmap(matrix=fitz.Matrix(1, 1), alpha=False)
                pixmap.save(thumbnail_path)
    except HTTPException:
        raise
    except (OSError, fitz.FileDataError) as exc:
        raise HTTPException(status_code=422, detail="Unable to render page thumbnail") from exc
    return FileResponse(thumbnail_path, media_type="image/jpeg")


@app.post("/api/documents/{filename:path}/rotate")
def rotate_document_page(filename: str, request: RotateRequest) -> dict:
    """Rotate one page in the prepared PDF without changing the source PDF."""
    processing_path = prepared_file(request.processing_id)
    try:
        with fitz.open(processing_path) as pdf:
            if request.page > pdf.page_count:
                raise HTTPException(status_code=422, detail="Page is outside the document")
            page_object = pdf[request.page - 1]
            effective_rotation = (page_object.rotation + request.rotation) % 360
            page_object.set_rotation(effective_rotation)
            pdf.save(processing_path.with_suffix(".rotated.pdf"))
        processing_path.with_suffix(".rotated.pdf").replace(processing_path)
        (processing_path.parent / f"page_{request.page:04d}.jpg").unlink(missing_ok=True)
    except HTTPException:
        raise
    except (OSError, fitz.FileDataError) as exc:
        raise HTTPException(status_code=422, detail="Unable to rotate PDF page") from exc
    return {
        "processing_id": request.processing_id,
        "page": request.page,
        "rotation": effective_rotation,
    }


@app.post("/api/documents/{filename:path}/split")
def split_document(filename: str, request: SplitRequest) -> dict:
    """Create numbered PDF parts from the prepared working copy."""
    processing_path = prepared_file(request.processing_id)
    try:
        with fitz.open(processing_path) as source_pdf:
            page_count = source_pdf.page_count
            boundaries = sorted(set(request.split_pages))
            if any(page < 2 or page > page_count for page in boundaries):
                raise HTTPException(status_code=422, detail="Split boundary is outside the document")
            starts = [1, *boundaries]
            ends = [page - 1 for page in boundaries] + [page_count]
            parts = []
            for index, (start, end) in enumerate(zip(starts, ends), start=1):
                output_pdf = fitz.open()
                output_pdf.insert_pdf(source_pdf, from_page=start - 1, to_page=end - 1)
                output_path = processing_path.parent / f"{Path(filename).stem}_part_{index:02d}.pdf"
                output_pdf.save(output_path)
                output_pdf.close()
                parts.append({"part": index, "start_page": start, "end_page": end, "path": str(output_path)})
    except HTTPException:
        raise
    except (OSError, fitz.FileDataError) as exc:
        raise HTTPException(status_code=422, detail="Unable to split PDF") from exc
    return {"processing_id": request.processing_id, "part_count": len(parts), "parts": parts}


@app.post("/api/documents/{filename:path}/reorder-pages")
def reorder_document_pages(filename: str, request: ReorderPagesRequest) -> dict:
    """Persist a new page order for the prepared working copy."""
    processing_path = prepared_file(request.processing_id)
    try:
        with fitz.open(processing_path) as pdf:
            page_count = pdf.page_count
            normalized_order = sorted(set(request.page_order))
            if len(request.page_order) != page_count or sorted(request.page_order) != list(range(1, page_count + 1)):
                raise HTTPException(status_code=422, detail="Page order must contain each page exactly once")
            ordered_pdf = fitz.open()
            for page_number in request.page_order:
                ordered_pdf.insert_pdf(pdf, from_page=page_number - 1, to_page=page_number - 1)
            reordered_path = processing_path.with_suffix(".reordered.pdf")
            ordered_pdf.save(reordered_path)
            ordered_pdf.close()
        reordered_path.replace(processing_path)
        for thumbnail_path in sorted(processing_path.parent.glob("page_*.jpg")):
            thumbnail_path.unlink(missing_ok=True)
    except HTTPException:
        raise
    except (OSError, fitz.FileDataError) as exc:
        raise HTTPException(status_code=422, detail="Unable to reorder PDF pages") from exc
    return {"processing_id": request.processing_id, "page_order": request.page_order, "status": "reordered"}


@app.post("/api/documents/{filename:path}/finalize-split")
def finalize_split_document(filename: str, request: SplitFinalizeRequest) -> dict:
    """Finalize every split part, then archive the source once."""
    try:
        document_path = resolve_source_document(filename)
    except HTTPException:
        raise HTTPException(status_code=404, detail="Document not found")
    processing_path = prepared_file(request.processing_id)
    configured_destinees = read_config()
    if len({output.part for output in request.outputs}) != len(request.outputs):
        raise HTTPException(status_code=400, detail="Each split part must be listed once")
    for output in request.outputs:
        if output.destinee.casefold() not in {value.casefold() for value in configured_destinees}:
            raise HTTPException(status_code=400, detail="Destinee is not configured")
    try:
        generated_parts = sorted(processing_path.parent.glob(f"{Path(filename).stem}_part_*.pdf"))
        if len(generated_parts) != len(request.outputs):
            raise HTTPException(status_code=422, detail="Split outputs do not match prepared parts")
        destinations = []
        relative_path = normalize_relative_document_path(filename)
        for output in request.outputs:
            matching_destinee = next(value for value in configured_destinees if value.casefold() == output.destinee.casefold())
            destination_file = DESTINATION_PATH / matching_destinee / relative_path.parent / output.output_filename
            if destination_file.exists():
                raise HTTPException(status_code=409, detail="A split output already exists")
            destinations.append((output, destination_file))
        archived_file = relative_archive_path(document_path)
        if archived_file.exists():
            raise HTTPException(status_code=409, detail="An archived document with this name already exists")
        created_files = []
        for generated_part, (_, destination_file) in zip(generated_parts, destinations):
            destination_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(generated_part, destination_file)
            created_files.append(destination_file)
        archived_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(document_path), archived_file)
        write_document_state(
            filename,
            "classified",
            processing_id=request.processing_id,
            split=True,
            outputs=[str(path) for path in created_files],
            archive_path=str(archived_file),
            sha256=calculate_file_hash(archived_file),
        )
        shutil.rmtree(processing_path.parent, ignore_errors=True)
    except HTTPException:
        raise
    except OSError as exc:
        for created_file in locals().get("created_files", []):
            created_file.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="Unable to finalize split document") from exc
    return {"status": "classified", "filename": filename, "outputs": [str(path) for path in created_files], "archive_path": str(archived_file)}


class DismissRequest(BaseModel):
    """Optional explanation for dismissing an inbox document."""

    reason: Optional[str] = Field(default=None, max_length=240)


@app.post("/api/documents/{filename:path}/dismiss")
def dismiss_document(filename: str, request: DismissRequest) -> dict:
    """Move an inbox PDF to the dismissed archive without processing it."""
    try:
        document_path = resolve_source_document(filename)
    except HTTPException:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        dismissed_file = DISMISSED_PATH / Path(filename)
        dismissed_file.parent.mkdir(parents=True, exist_ok=True)
        if dismissed_file.exists():
            raise HTTPException(status_code=409, detail="A dismissed document with this name already exists")
        file_hash = calculate_file_hash(document_path)
        shutil.move(str(document_path), dismissed_file)
        write_document_state(
            filename,
            "dismissed",
            sha256=file_hash,
            reason=(request.reason or "").strip() or None,
            dismissed_path=str(dismissed_file),
        )
    except HTTPException:
        raise
    except OSError as exc:
        raise HTTPException(status_code=500, detail="Unable to dismiss document") from exc

    return {
        "status": "dismissed",
        "filename": filename,
        "dismissed_path": str(dismissed_file),
    }


@app.get("/api/approval/audit")
def get_approval_audit() -> dict:
    """Return the persisted approval/audit history for user actions."""
    return read_approval_audit()


@app.get("/api/jobs/summary")
def get_job_summary() -> dict:
    """Return a minimal operational summary of the persisted job queue."""
    return summarize_jobs()


@app.get("/api/jobs/{job_id}")
def get_job_status(job_id: str) -> dict:
    """Read the persisted status for a queued or processed preparation job."""
    jobs = read_job_store()
    job = jobs.get(job_id)
    if not isinstance(job, dict):
        raise HTTPException(status_code=404, detail="Job not found")
    job.setdefault("retry_count", 0)
    return job


@app.post("/api/jobs/{job_id}/retry")
def retry_job(job_id: str) -> dict:
    """Reset a job to the queued state and increment its retry count for admin recovery."""
    jobs = read_job_store()
    job = jobs.get(job_id)
    if not isinstance(job, dict):
        raise HTTPException(status_code=404, detail="Job not found")
    retry_count = int(job.get("retry_count", 0) or 0) + 1
    job_timestamp = datetime.now(timezone.utc).isoformat()
    job.update({
        "status": "queued",
        "retry_count": retry_count,
        "updated_at": job_timestamp,
    })
    jobs[job_id] = job
    JOB_STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    JOB_STATUS_PATH.write_text(json.dumps(jobs, indent=2), encoding="utf-8")
    return job


@app.post("/api/jobs/{job_id}/reassign")
def reassign_job(job_id: str, payload: dict) -> dict:
    """Allow admin reassignment of a queued job to a different destinee or queue bucket."""
    jobs = read_job_store()
    job = jobs.get(job_id)
    if not isinstance(job, dict):
        raise HTTPException(status_code=404, detail="Job not found")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Assignment payload must be an object")
    destinee = payload.get("destinee")
    if destinee:
        job["destinee"] = str(destinee)
    queue_status = payload.get("queue_status")
    if queue_status:
        status = str(queue_status).strip().lower()
        if status in {"queued", "processing", "ready", "failed"}:
            job["status"] = status
            job["queue_status"] = status
    job["updated_at"] = datetime.now(timezone.utc).isoformat()
    jobs[job_id] = job
    JOB_STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    JOB_STATUS_PATH.write_text(json.dumps(jobs, indent=2), encoding="utf-8")
    return job


@app.post("/api/documents/{filename:path}/prepare")
def prepare_document(filename: str, async_mode: bool = Query(False, alias="async")) -> dict:
    """Copy a source PDF into processing storage and return page metadata."""
    try:
        document_path = resolve_source_document(filename)
    except HTTPException:
        raise HTTPException(status_code=404, detail="Document not found")

    processing_id = uuid.uuid4().hex
    processing_directory = TEMP_PATH / "processing" / processing_id
    processing_path = processing_directory / "original.pdf"
    try:
        processing_directory.mkdir(parents=True, exist_ok=False)
        shutil.copy2(document_path, processing_path)
        try:
            with fitz.open(processing_path) as pdf:
                pages = []
                page_ocr_used = False
                for page_number, page in enumerate(pdf):
                    page_text, ocr_used = extract_page_text(page)
                    page_ocr_used = page_ocr_used or ocr_used
                    pages.append(
                        {"page": page_number + 1, "text": page_text[:2000], "ocr_used": ocr_used}
                    )
                page_count = len(pages)
                route_details = determine_document_route([page["text"] for page in pages], page_ocr_used)
        except (OSError, ValueError, RuntimeError, fitz.FileDataError):
            pages = [{"page": 1, "text": "", "ocr_used": False}]
            page_count = 1
            route_details = determine_document_route([""], False)
        write_document_state(
            filename,
            "in_review",
            processing_id=processing_id,
            sha256=calculate_file_hash(processing_path),
            **route_details,
        )
    except OSError as exc:
        try:
            write_document_state(document_path.name, "failed", error="Unable to prepare PDF")
        except OSError:
            pass
        shutil.rmtree(processing_directory, ignore_errors=True)
        raise HTTPException(status_code=422, detail="Unable to prepare PDF for processing") from exc

    relative_source_path = document_path.relative_to(SOURCE_PATH)
    response = {
        "processing_id": processing_id,
        "original_name": document_path.name,
        "source_path": relative_source_path.as_posix(),
        "source_directory": relative_source_path.parent.as_posix() if relative_source_path.parent != Path(".") else "root",
        "processing_path": str(processing_path),
        "page_count": page_count,
        "pages": pages,
        "ocr_used": any(page["ocr_used"] for page in pages),
        "readable": route_details["readable"],
        "route": route_details["route"],
        "queue_status": route_details["queue_status"],
        "processing_strategy": route_details["processing_strategy"],
        "local_classification": route_details["local_classification"],
        "quality_score": route_details["quality_score"],
        "recommended_provider": route_details["recommended_provider"],
        "processing_profile": route_details["processing_profile"],
        "status": "in_review",
    }

    if async_mode:
        job_id = create_job_record(filename, processing_id, route_details, page_count)
        async_payload = {**response, "job_id": job_id, "processing_id": processing_id, "status": "queued"}
        return Response(
            content=json.dumps(async_payload),
            media_type="application/json",
            status_code=202,
        )

    return response


@app.post("/api/documents/{filename:path}/analyze")
def analyze_document(filename: str, processing_id: str) -> dict:
    """Analyze extracted PDF text and suggest a descriptive output filename."""
    processing_path = (TEMP_PATH / "processing" / processing_id / "original.pdf").resolve()
    processing_root = (TEMP_PATH / "processing").resolve()
    if processing_path.parent.parent != processing_root or not processing_path.is_file():
        raise HTTPException(status_code=404, detail="Prepared document not found")
    try:
        cached_result = cached_analysis_result(filename, processing_path)
        if cached_result:
            write_document_state(
                filename,
                "in_review",
                processing_id=processing_id,
                sha256=calculate_file_hash(processing_path),
                **cached_result,
            )
            return {"status": "in_review", **cached_result}

        with fitz.open(processing_path) as pdf:
            text = "\n".join(page.get_text() for page in pdf)
            if not text.strip():
                text = "\n".join(extract_page_text_with_ocr(page)[0] for page in pdf)
            layout = extract_layout_metadata(pdf)
            if GEMINI_API_KEY:
                result = analyze_with_gemini(text, filename, pdf, layout) or analyze_text(text, filename)
            else:
                result = analyze_text(text, filename)
            result["layout"] = layout
    except (OSError, fitz.FileDataError) as exc:
        write_document_state(filename, "failed", error="Unable to analyze PDF")
        raise HTTPException(status_code=422, detail="Unable to analyze PDF") from exc
    write_document_state(
        filename,
        "in_review",
        processing_id=processing_id,
        sha256=calculate_file_hash(processing_path),
        **result,
    )
    return {"status": "in_review", **result}


@app.post("/api/documents/merge")
def merge_documents(request: MergeDocumentsRequest) -> dict:
    """Combine multiple source PDFs into a single classified output."""
    configured_destinees = read_config()
    matching_destinee = next(
        (value for value in configured_destinees if value.casefold() == request.destinee.casefold()),
        None,
    )
    if matching_destinee is None:
        if configured_destinees:
            raise HTTPException(status_code=400, detail="Destinee is not configured")
        matching_destinee = request.destinee.strip()
        ensure_destinee_directories([matching_destinee])

    resolved_documents: List[tuple[str, Path]] = []
    for filename in request.documents:
        try:
            resolved_documents.append((filename, resolve_source_document(filename)))
        except HTTPException as exc:
            raise HTTPException(status_code=404, detail=f"Document not found: {filename}") from exc

    destination_directory = DESTINATION_PATH / matching_destinee
    destination_file = destination_directory / request.output_filename
    if destination_file.exists():
        raise HTTPException(status_code=409, detail="A document with this name already exists")

    merged_pdf = fitz.open()
    try:
        for _, document_path in resolved_documents:
            with fitz.open(document_path) as source_pdf:
                merged_pdf.insert_pdf(source_pdf)
        destination_directory.mkdir(parents=True, exist_ok=True)
        merged_pdf.save(destination_file)
    except (OSError, fitz.FileDataError) as exc:
        raise HTTPException(status_code=422, detail="Unable to merge PDF documents") from exc
    finally:
        merged_pdf.close()

    try:
        archived_files = [move_or_archive_document(document_path) for _, document_path in resolved_documents]
        write_document_state(
            request.output_filename,
            "classified",
            destinee=matching_destinee,
            destination_path=str(destination_file),
            archive_paths=[str(path) for path in archived_files],
            source_documents=request.documents,
            sha256=calculate_file_hash(destination_file),
        )
    except HTTPException:
        raise
    except OSError as exc:
        raise HTTPException(status_code=500, detail="Unable to archive merged documents") from exc

    return {
        "status": "classified",
        "filename": request.output_filename,
        "destinee": matching_destinee,
        "destination_path": str(destination_file),
        "source_documents": request.documents,
        "archive_paths": [str(path) for path in archived_files],
    }


@app.post("/api/documents/{filename:path}/finalize")
def finalize_document(filename: str, request: FinalizeRequest) -> dict:
    """Route a prepared PDF to a configured destinee without overwriting files."""
    try:
        document_path = resolve_source_document(filename)
    except HTTPException:
        raise HTTPException(status_code=404, detail="Document not found")

    configured_destinees = read_config()
    matching_destinee = next(
        (value for value in configured_destinees if value.casefold() == request.destinee.casefold()),
        None,
    )
    if matching_destinee is None:
        if configured_destinees:
            raise HTTPException(status_code=400, detail="Destinee is not configured")
        matching_destinee = request.destinee.strip()
        ensure_destinee_directories([matching_destinee])

    if configured_destinees:
        route = resolve_route_for_destinee(matching_destinee, request.output_filename or Path(filename).name)
    else:
        root = (DESTINATION_PATH / matching_destinee).expanduser()
        root.mkdir(parents=True, exist_ok=True)
        output_name = request.output_filename or Path(filename).name
        route = {
            "resolved_destinee": matching_destinee,
            "root_path": str(root),
            "destination_path": str((root / output_name).resolve()),
        }

    role = (request.role or "").strip().lower()
    actor = (request.actor or "").strip()
    if role and role not in {"reviewer", "approver", "admin"}:
        raise HTTPException(status_code=403, detail="Unsupported approval role")
    if role and role != "approver" and role != "admin":
        raise HTTPException(status_code=403, detail="Only approvers or admins can finalize documents")

    processing_path = (TEMP_PATH / "processing" / request.processing_id / "original.pdf").resolve()
    processing_root = (TEMP_PATH / "processing").resolve()
    if processing_path.parent.parent != processing_root or not processing_path.is_file():
        raise HTTPException(status_code=404, detail="Prepared document not found")

    output_filename = request.output_filename or Path(filename).name
    destination_directory = Path(route["root_path"]).resolve()
    destination_file = destination_directory / output_filename
    archived_file = relative_archive_path(document_path)
    try:
        destination_directory.mkdir(parents=True, exist_ok=True)
        archived_file.parent.mkdir(parents=True, exist_ok=True)
        if archived_file.exists():
            raise HTTPException(status_code=409, detail="An archived document with this name already exists")
        if destination_file.exists():
            raise HTTPException(status_code=409, detail="A document with this name already exists")
        shutil.copy2(processing_path, destination_file)
        shutil.move(str(document_path), archived_file)
        write_document_state(
            filename,
            "classified",
            processing_id=request.processing_id,
            destinee=matching_destinee,
            destination_path=str(destination_file),
            archive_path=str(archived_file),
            sha256=calculate_file_hash(archived_file),
        )
        shutil.rmtree(processing_path.parent, ignore_errors=True)
    except HTTPException:
        raise
    except OSError as exc:
        raise HTTPException(status_code=500, detail="Unable to finalize document") from exc

    entry = append_approval_audit(
        "finalize",
        filename,
        actor or None,
        role or None,
        processing_id=request.processing_id,
        destinee=matching_destinee,
        destination_path=str(destination_file),
        archive_path=str(archived_file),
    )

    return {
        "status": "classified",
        "filename": output_filename,
        "original_filename": document_path.name,
        "destinee": matching_destinee,
        "destination_path": str(destination_file),
        "archive_path": str(archived_file),
        "audit_entry": entry,
    }


app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
