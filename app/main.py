"""Native configuration API for the n8n/local classification workflow."""

import json
import base64
import hashlib
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import quote

import httpx
import pymupdf as fitz
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

DEFAULT_DESTINEES: List[str] = []
APP_VERSION = os.getenv("APP_VERSION", "dev")
APP_REVISION = os.getenv("APP_REVISION", "unknown")
SOURCE_PATH = Path(os.getenv("RAW_INPUT_PATH", "/data/source"))
DESTINATION_PATH = Path(os.getenv("CLASSIFIED_OUTPUT_PATH", "/data/destination"))
ARCHIVE_PATH = Path(os.getenv("PROCESSED_ARCHIVE_PATH", "/data/archive"))
DISMISSED_PATH = Path(os.getenv("DISMISSED_ARCHIVE_PATH", "/data/archive/dismissed"))
CONFIG_PATH = Path(os.getenv("CLASSIFICATION_CONFIG_PATH", "/data/config/classification.json"))
DOCUMENTS_PATH = Path(os.getenv("DOCUMENTS_STATUS_PATH", "/data/config/documents.json"))
ANALYSIS_STATUS_PATH = Path(os.getenv("ANALYSIS_STATUS_PATH", "/data/config/analysis-status.json"))
TEMP_PATH = Path(os.getenv("TEMP_PATH", "/data/temp"))
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_ENDPOINT = os.getenv(
    "GEMINI_ENDPOINT",
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent",
)
GEMINI_TIMEOUT = float(os.getenv("GEMINI_TIMEOUT", "20"))
OCR_LANGUAGES = os.getenv("OCR_LANGUAGES", "eng+deu")
OCR_RENDER_SCALE = float(os.getenv("OCR_RENDER_SCALE", "2"))

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


class ClassificationResponse(ClassificationConfig):
    """Configuration response including immutable runtime paths."""

    input_path: str
    output_root: str


class FinalizeRequest(BaseModel):
    """Request to route a prepared document to one configured destinee."""

    processing_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-f0-9]+$")
    destinee: str = Field(min_length=1, max_length=80)
    output_filename: Optional[str] = Field(default=None, max_length=180)

    @field_validator("output_filename")
    @classmethod
    def validate_output_filename(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        cleaned = value.strip()
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


app = FastAPI(title="Document Classifier API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/")
@app.get("/index.html")
def serve_index() -> Response:
    """Serve the handcrafted frontend with a cache-busting version stamp."""
    index_path = Path("/app/frontend/index.html")
    content = index_path.read_text(encoding="utf-8").replace("__APP_VERSION__", APP_VERSION)
    return Response(content=content, media_type="text/html", headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"})


def read_config() -> List[str]:
    if not CONFIG_PATH.exists():
        return list(DEFAULT_DESTINEES)
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return ClassificationConfig.model_validate(data).destinees
    except (OSError, json.JSONDecodeError, ValueError):
        return list(DEFAULT_DESTINEES)


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
    states[filename] = {"status": status, **details}
    DOCUMENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOCUMENTS_PATH.write_text(json.dumps(states, indent=2), encoding="utf-8")


def normalize_relative_document_path(filename: str) -> Path:
    relative_path = Path(filename.replace("\\", "/"))
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise HTTPException(status_code=404, detail="Document not found")
    if not relative_path.name or relative_path.name in {"", ".", ".."}:
        raise HTTPException(status_code=404, detail="Document not found")
    return relative_path


def resolve_source_document(filename: str) -> Path:
    relative_path = normalize_relative_document_path(filename)
    document_path = (SOURCE_PATH / relative_path).resolve()
    source_root = SOURCE_PATH.resolve()
    if not document_path.is_relative_to(source_root):
        raise HTTPException(status_code=404, detail="Document not found")
    if not document_path.is_file() or document_path.suffix.casefold() != ".pdf":
        raise HTTPException(status_code=404, detail="Document not found")
    return document_path


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


def extract_page_text(page: object) -> tuple[str, bool]:
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


def response_for(destinees: List[str]) -> ClassificationResponse:
    ensure_destinee_directories(destinees)
    return ClassificationResponse(
        destinees=destinees,
        input_path=str(SOURCE_PATH),
        output_root=f"{DESTINATION_PATH}/",
    )


def ensure_destinee_directories(destinees: List[str]) -> None:
    DESTINATION_PATH.mkdir(parents=True, exist_ok=True)
    for destinee in destinees:
        (DESTINATION_PATH / destinee).mkdir(exist_ok=True)


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
    return {
        "provider": "n8n",
        "input_path": str(SOURCE_PATH),
        "ready": SOURCE_PATH.exists() and SOURCE_PATH.is_dir(),
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


@app.get("/api/classification/config", response_model=ClassificationResponse)
def get_classification_config() -> ClassificationResponse:
    return response_for(read_config())


@app.post("/api/classification/config", response_model=ClassificationResponse)
def update_classification_config(config: ClassificationConfig) -> ClassificationResponse:
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(config.model_dump_json(indent=2), encoding="utf-8")
        ensure_destinee_directories(config.destinees)
    except OSError as exc:
        raise HTTPException(status_code=500, detail="Unable to persist classification configuration") from exc
    return response_for(config.destinees)


@app.post("/api/classification/scan")
def scan_input_directory() -> dict:
    if not SOURCE_PATH.exists() or not SOURCE_PATH.is_dir():
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
    for path in SOURCE_PATH.rglob("*.pdf"):
        if not path.is_file():
            continue
        relative_path = path.relative_to(SOURCE_PATH)
        if any(part.startswith(".") for part in relative_path.parts):
            continue
        pdfs.append((relative_path, path))
    for relative_path, path in pdfs:
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
        for relative_path, path in pdfs
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


@app.post("/api/documents/{filename:path}/prepare")
def prepare_document(filename: str) -> dict:
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
        with fitz.open(processing_path) as pdf:
            pages = []
            for page_number, page in enumerate(pdf):
                page_text, ocr_used = extract_page_text(page)
                pages.append(
                    {"page": page_number + 1, "text": page_text[:2000], "ocr_used": ocr_used}
                )
        write_document_state(
            filename,
            "in_review",
            processing_id=processing_id,
            sha256=calculate_file_hash(processing_path),
        )
    except (OSError, fitz.FileDataError) as exc:
        try:
            write_document_state(document_path.name, "failed", error="Unable to prepare PDF")
        except OSError:
            pass
        shutil.rmtree(processing_directory, ignore_errors=True)
        raise HTTPException(status_code=422, detail="Unable to prepare PDF for processing") from exc

    relative_source_path = document_path.relative_to(SOURCE_PATH)
    return {
        "processing_id": processing_id,
        "original_name": document_path.name,
        "source_path": relative_source_path.as_posix(),
        "source_directory": relative_source_path.parent.as_posix() if relative_source_path.parent != Path(".") else "root",
        "processing_path": str(processing_path),
        "page_count": len(pages),
        "pages": pages,
        "ocr_used": any(page["ocr_used"] for page in pages),
        "status": "in_review",
    }


@app.post("/api/documents/{filename:path}/analyze")
def analyze_document(filename: str, processing_id: str) -> dict:
    """Analyze extracted PDF text and suggest a descriptive output filename."""
    processing_path = (TEMP_PATH / "processing" / processing_id / "original.pdf").resolve()
    processing_root = (TEMP_PATH / "processing").resolve()
    if processing_path.parent.parent != processing_root or not processing_path.is_file():
        raise HTTPException(status_code=404, detail="Prepared document not found")
    try:
        with fitz.open(processing_path) as pdf:
            text = "\n".join(extract_page_text(page)[0] for page in pdf)
            layout = extract_layout_metadata(pdf)
            result = analyze_with_gemini(text, filename, pdf, layout) or analyze_text(text, filename)
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
        raise HTTPException(status_code=400, detail="Destinee is not configured")

    processing_path = (TEMP_PATH / "processing" / request.processing_id / "original.pdf").resolve()
    processing_root = (TEMP_PATH / "processing").resolve()
    if processing_path.parent.parent != processing_root or not processing_path.is_file():
        raise HTTPException(status_code=404, detail="Prepared document not found")

    relative_path = Path(filename)
    destination_directory = DESTINATION_PATH / matching_destinee / relative_path.parent
    output_filename = request.output_filename or relative_path.name
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

    return {
        "status": "classified",
        "filename": output_filename,
        "original_filename": document_path.name,
        "destinee": matching_destinee,
        "destination_path": str(destination_file),
        "archive_path": str(archived_file),
    }


app.mount("/", StaticFiles(directory="/app/frontend", html=True), name="frontend")
