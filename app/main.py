"""Native configuration API for the n8n/local classification workflow."""

import json
import os
import re
import shutil
import uuid
from pathlib import Path
from typing import List
from urllib.parse import quote

import pymupdf as fitz
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

DEFAULT_DESTINEES = ["Destinee A", "Destinee B", "Destinee C"]
SOURCE_PATH = Path(os.getenv("RAW_INPUT_PATH", "/data/source"))
DESTINATION_PATH = Path(os.getenv("CLASSIFIED_OUTPUT_PATH", "/data/destination"))
ARCHIVE_PATH = Path(os.getenv("PROCESSED_ARCHIVE_PATH", "/data/archive"))
CONFIG_PATH = Path(os.getenv("CLASSIFICATION_CONFIG_PATH", "/data/config/classification.json"))
DOCUMENTS_PATH = Path(os.getenv("DOCUMENTS_STATUS_PATH", "/data/config/documents.json"))
TEMP_PATH = Path(os.getenv("TEMP_PATH", "/data/temp"))

_DESTINEE_PATTERN = re.compile(r"^[^/\\\x00]+$")


class ClassificationConfig(BaseModel):
    """User-editable first-level classification configuration."""

    destinees: List[str] = Field(min_length=1, max_length=50)

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


app = FastAPI(title="Document Classifier API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


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


@app.get("/api/ingestion/status")
def ingestion_status() -> dict:
    return {
        "provider": "n8n",
        "input_path": str(SOURCE_PATH),
        "ready": SOURCE_PATH.exists() and SOURCE_PATH.is_dir(),
    }


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
    for path in SOURCE_PATH.iterdir():
        if path.is_file() and path.suffix.casefold() == ".pdf" and not path.name.startswith("."):
            states.setdefault(path.name, {"status": "received"})
    DOCUMENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOCUMENTS_PATH.write_text(json.dumps(states, indent=2), encoding="utf-8")
    files = sorted(
        {
            "name": path.name,
            "path": str(path),
            "size": path.stat().st_size,
            "status": states.get(path.name, {}).get("status", "received"),
        }
        for path in SOURCE_PATH.iterdir()
        if path.is_file() and path.suffix.casefold() == ".pdf" and not path.name.startswith(".")
    )
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


@app.get("/api/documents/{filename}")
def get_document(filename: str) -> dict:
    """Return metadata for one completed PDF in the n8n input directory."""
    document_path = (SOURCE_PATH / filename).resolve()
    source_root = SOURCE_PATH.resolve()
    if document_path.parent != source_root:
        raise HTTPException(status_code=404, detail="Document not found")
    if not document_path.is_file() or document_path.suffix.casefold() != ".pdf":
        archived_path = (ARCHIVE_PATH / filename).resolve()
        if (
            archived_path.parent != ARCHIVE_PATH.resolve()
            or not archived_path.is_file()
            or archived_path.suffix.casefold() != ".pdf"
        ):
            raise HTTPException(status_code=404, detail="Document not found")
        document_path = archived_path
    try:
        metadata = document_path.stat()
    except OSError as exc:
        raise HTTPException(status_code=404, detail="Document not found") from exc
    state = read_document_states().get(filename, {})
    return {
        "name": document_path.name,
        "path": str(document_path),
        "size": metadata.st_size,
        "modified": metadata.st_mtime,
        "status": state.get("status", "received"),
        **{key: value for key, value in state.items() if key != "status"},
    }


@app.get("/api/documents/{filename}/file")
def serve_document(filename: str):
    """Serve one source PDF for browser review without exposing other paths."""
    document_path = (SOURCE_PATH / filename).resolve()
    if document_path.parent != SOURCE_PATH.resolve() or not document_path.is_file() or document_path.suffix.casefold() != ".pdf":
        raise HTTPException(status_code=404, detail="Document not found")
    return FileResponse(
        document_path,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(document_path.name)}"
        },
    )


@app.post("/api/documents/{filename}/prepare")
def prepare_document(filename: str) -> dict:
    """Copy a source PDF into processing storage and return page metadata."""
    document_path = (SOURCE_PATH / filename).resolve()
    source_root = SOURCE_PATH.resolve()
    if document_path.parent != source_root or not document_path.is_file() or document_path.suffix.casefold() != ".pdf":
        raise HTTPException(status_code=404, detail="Document not found")

    processing_id = uuid.uuid4().hex
    processing_directory = TEMP_PATH / "processing" / processing_id
    processing_path = processing_directory / "original.pdf"
    try:
        processing_directory.mkdir(parents=True, exist_ok=False)
        shutil.copy2(document_path, processing_path)
        with fitz.open(processing_path) as pdf:
            pages = [
                {"page": page_number + 1, "text": page.get_text()[:2000]}
                for page_number, page in enumerate(pdf)
            ]
        write_document_state(
            document_path.name,
            "in_review",
            processing_id=processing_id,
        )
    except (OSError, fitz.FileDataError) as exc:
        try:
            write_document_state(document_path.name, "failed", error="Unable to prepare PDF")
        except OSError:
            pass
        shutil.rmtree(processing_directory, ignore_errors=True)
        raise HTTPException(status_code=422, detail="Unable to prepare PDF for processing") from exc

    return {
        "processing_id": processing_id,
        "original_name": document_path.name,
        "processing_path": str(processing_path),
        "page_count": len(pages),
        "pages": pages,
        "status": "in_review",
    }


@app.post("/api/documents/{filename}/finalize")
def finalize_document(filename: str, request: FinalizeRequest) -> dict:
    """Route a prepared PDF to a configured destinee without overwriting files."""
    document_path = (SOURCE_PATH / filename).resolve()
    if document_path.parent != SOURCE_PATH.resolve() or document_path.suffix.casefold() != ".pdf":
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

    destination_directory = DESTINATION_PATH / matching_destinee
    destination_file = destination_directory / document_path.name
    archived_file = ARCHIVE_PATH / document_path.name
    try:
        destination_directory.mkdir(parents=True, exist_ok=True)
        ARCHIVE_PATH.mkdir(parents=True, exist_ok=True)
        if archived_file.exists():
            raise HTTPException(status_code=409, detail="An archived document with this name already exists")
        if destination_file.exists():
            raise HTTPException(status_code=409, detail="A document with this name already exists")
        shutil.copy2(processing_path, destination_file)
        shutil.move(str(document_path), archived_file)
        write_document_state(
            document_path.name,
            "classified",
            processing_id=request.processing_id,
            destinee=matching_destinee,
            destination_path=str(destination_file),
            archive_path=str(archived_file),
        )
        shutil.rmtree(processing_path.parent, ignore_errors=True)
    except HTTPException:
        raise
    except OSError as exc:
        raise HTTPException(status_code=500, detail="Unable to finalize document") from exc

    return {
        "status": "classified",
        "filename": document_path.name,
        "destinee": matching_destinee,
        "destination_path": str(destination_file),
        "archive_path": str(archived_file),
    }


app.mount("/", StaticFiles(directory="/app/frontend", html=True), name="frontend")
