"""Focused tests for the n8n handoff and destinee configuration API."""

import importlib

from fastapi.testclient import TestClient


def load_api(monkeypatch, tmp_path):
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    config = tmp_path / "config.json"
    source.mkdir()
    monkeypatch.setenv("RAW_INPUT_PATH", str(source))
    monkeypatch.setenv("CLASSIFIED_OUTPUT_PATH", str(destination))
    monkeypatch.setenv("CLASSIFICATION_CONFIG_PATH", str(config))
    import app.main as main
    return importlib.reload(main), source, destination


def test_get_default_classification_config(monkeypatch, tmp_path):
    main, _, _ = load_api(monkeypatch, tmp_path)
    response = TestClient(main.app).get("/api/classification/config")

    assert response.status_code == 200
    assert response.json()["destinees"] == ["Destinee A", "Destinee B", "Destinee C"]
    assert response.json()["output_root"].endswith("destination/")


def test_update_config_creates_destinee_directories(monkeypatch, tmp_path):
    main, _, destination = load_api(monkeypatch, tmp_path)
    response = TestClient(main.app).post(
        "/api/classification/config",
        json={"destinees": ["Destinee A", "Shared"]},
    )

    assert response.status_code == 200
    assert (destination / "Destinee A").is_dir()
    assert (destination / "Shared").is_dir()


def test_update_config_rejects_path_separator(monkeypatch, tmp_path):
    main, _, _ = load_api(monkeypatch, tmp_path)
    response = TestClient(main.app).post(
        "/api/classification/config",
        json={"destinees": ["../outside"]},
    )

    assert response.status_code == 422


def test_scan_returns_completed_pdfs_only(monkeypatch, tmp_path):
    main, source, _ = load_api(monkeypatch, tmp_path)
    (source / "invoice.pdf").write_bytes(b"pdf")
    (source / "partial.tmp").write_bytes(b"partial")
    (source / ".hidden.pdf").write_bytes(b"hidden")

    response = TestClient(main.app).post("/api/classification/scan")

    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert response.json()["files"][0]["name"] == "invoice.pdf"
