"""Native configuration API for the n8n/local classification workflow."""

import json
import os
import re
from pathlib import Path
from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

DEFAULT_DESTINEES = ["Destinee A", "Destinee B", "Destinee C"]
SOURCE_PATH = Path(os.getenv("RAW_INPUT_PATH", "/data/source"))
DESTINATION_PATH = Path(os.getenv("CLASSIFIED_OUTPUT_PATH", "/data/destination"))
CONFIG_PATH = Path(os.getenv("CLASSIFICATION_CONFIG_PATH", "/data/config/classification.json"))

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


def response_for(destinees: List[str]) -> ClassificationResponse:
    return ClassificationResponse(
        destinees=destinees,
        input_path=str(SOURCE_PATH),
        output_root=f"{DESTINATION_PATH}/",
    )


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
        DESTINATION_PATH.mkdir(parents=True, exist_ok=True)
        for destinee in config.destinees:
            (DESTINATION_PATH / destinee).mkdir(exist_ok=True)
    except OSError as exc:
        raise HTTPException(status_code=500, detail="Unable to persist classification configuration") from exc
    return response_for(config.destinees)


@app.post("/api/classification/scan")
def scan_input_directory() -> dict:
    if not SOURCE_PATH.exists() or not SOURCE_PATH.is_dir():
        raise HTTPException(status_code=503, detail="n8n input directory is unavailable")
    files = sorted(
        {"name": path.name, "path": str(path), "size": path.stat().st_size}
        for path in SOURCE_PATH.iterdir()
        if path.is_file() and path.suffix.casefold() == ".pdf" and not path.name.startswith(".")
    )
    return {"files": files, "count": len(files)}


app.mount("/", StaticFiles(directory="/app/frontend", html=True), name="frontend")
