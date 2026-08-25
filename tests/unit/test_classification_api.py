"""Focused tests for the n8n handoff and destinee configuration API."""

import importlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def load_api(monkeypatch, tmp_path):
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    archive = tmp_path / "archive"
    dismissed = tmp_path / "dismissed"
    temp = tmp_path / "temp"
    config = tmp_path / "config.json"
    documents = tmp_path / "documents.json"
    analysis_status = tmp_path / "analysis-status.json"
    source.mkdir()
    monkeypatch.setenv("RAW_INPUT_PATH", str(source))
    monkeypatch.setenv("CLASSIFIED_OUTPUT_PATH", str(destination))
    monkeypatch.setenv("PROCESSED_ARCHIVE_PATH", str(archive))
    monkeypatch.setenv("DISMISSED_ARCHIVE_PATH", str(dismissed))
    monkeypatch.setenv("CLASSIFICATION_CONFIG_PATH", str(config))
    monkeypatch.setenv("DOCUMENTS_STATUS_PATH", str(documents))
    monkeypatch.setenv("ANALYSIS_STATUS_PATH", str(analysis_status))
    monkeypatch.setenv("TEMP_PATH", str(temp))
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    import app.main as main
    return importlib.reload(main), source, destination


def test_index_links_to_configuration_page():
    index_html = Path("frontend/index.html").read_text(encoding="utf-8")
    assert 'href="config.html"' in index_html


def test_index_does_not_load_config_script():
    index_html = Path("frontend/index.html").read_text(encoding="utf-8")
    assert 'src="config.js' not in index_html


def test_config_page_implements_live_configuration_interface():
    config_js = Path("frontend/config.js").read_text(encoding="utf-8")
    assert "fetch(`${API_BASE_URL}/api/classification/config`" in config_js
    assert "document.querySelector(\"#destinee-form\")?.addEventListener(\"submit\"" in config_js


def test_config_page_clears_stale_destinee_state_after_delete_and_save():
    config_js = Path("frontend/config.js").read_text(encoding="utf-8")
    assert "buildValidDestinationRouteMap" in config_js
    assert "localStorage.removeItem(STORAGE_KEY)" in config_js
    assert "readDestinationRouteRows" in config_js


def test_config_page_rebuilds_route_state_from_current_destinees():
    config_js = Path("frontend/config.js").read_text(encoding="utf-8")
    assert "renderDestinationRoutes(validDestinees, nextRoutes)" in config_js
    assert "const validDestinees = sanitizeDestineeList(destinees);" in config_js


def test_config_page_exposes_source_and_destination_configuration_fields():
    config_html = Path("frontend/config.html").read_text(encoding="utf-8")
    assert 'id="destinee-list"' in config_html
    assert 'id="source-root-list"' in config_html
    assert 'id="destination-route-list"' in config_html

    config_js = Path("frontend/config.js").read_text(encoding="utf-8")
    assert "source_roots" in config_js
    assert "destination_roots" in config_js
    assert "buildDefaultDestinationRoutes" in config_js


def test_default_source_root_is_accepted_even_when_absent(monkeypatch, tmp_path):
    monkeypatch.setenv("RAW_INPUT_PATH", "/data/source")
    monkeypatch.setenv("CLASSIFIED_OUTPUT_PATH", str(tmp_path / "destination"))
    monkeypatch.setenv("CLASSIFICATION_CONFIG_PATH", str(tmp_path / "classification.json"))
    monkeypatch.setenv("DOCUMENTS_STATUS_PATH", str(tmp_path / "documents.json"))
    monkeypatch.setenv("ANALYSIS_STATUS_PATH", str(tmp_path / "analysis-status.json"))
    monkeypatch.setenv("TEMP_PATH", str(tmp_path / "temp"))
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    import app.main as main
    main = importlib.reload(main)

    response = TestClient(main.app).get("/api/classification/config")

    assert response.status_code == 200
    assert response.json()["source_roots"] == ["/data/source"]


def test_api_allows_browser_requests_from_port_3001(monkeypatch, tmp_path):
    main, _, _ = load_api(monkeypatch, tmp_path)
    client = TestClient(main.app)

    response = client.options(
        "/api/classification/config",
        headers={
            "Origin": "http://127.0.0.1:3001",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://127.0.0.1:3001"


def test_get_default_classification_config(monkeypatch, tmp_path):
    main, _, _ = load_api(monkeypatch, tmp_path)
    response = TestClient(main.app).get("/api/classification/config")

    assert response.status_code == 200
    assert response.json()["destinees"] == []
    assert response.json()["output_root"].endswith("destination/")


def test_legacy_api_config_alias_is_supported(monkeypatch, tmp_path):
    main, _, _ = load_api(monkeypatch, tmp_path)
    client = TestClient(main.app)

    get_response = client.get("/api/config")
    assert get_response.status_code == 200
    assert get_response.json()["output_root"].endswith("destination/")

    post_response = client.post(
        "/api/config",
        json={"destinees": ["Finance", "Legal"]},
    )
    assert post_response.status_code == 200
    assert post_response.json()["destinees"] == ["Finance", "Legal"]


def test_update_config_creates_destinee_directories(monkeypatch, tmp_path):
    main, _, destination = load_api(monkeypatch, tmp_path)
    response = TestClient(main.app).post(
        "/api/classification/config",
        json={"destinees": ["Destinee A", "Shared"]},
    )

    assert response.status_code == 200
    assert (destination / "Destinee A").is_dir()
    assert (destination / "Shared").is_dir()


def test_configuration_accepts_multiple_source_roots(monkeypatch, tmp_path):
    main, _, _ = load_api(monkeypatch, tmp_path)
    client = TestClient(main.app)
    source_a = tmp_path / "source-a"
    source_b = tmp_path / "source-b"
    source_a.mkdir()
    source_b.mkdir()

    response = client.post(
        "/api/classification/config",
        json={
            "destinees": ["Finance"],
            "source_roots": [str(source_a), str(source_b)],
        },
    )

    assert response.status_code == 200
    assert response.json()["source_roots"] == [str(source_a), str(source_b)]


def test_configuration_accepts_multiple_destination_routes(monkeypatch, tmp_path):
    main, _, _ = load_api(monkeypatch, tmp_path)
    client = TestClient(main.app)

    response = client.post(
        "/api/classification/config",
        json={
            "destinees": ["Finance", "Legal"],
            "destination_roots": {
                "Finance": str(tmp_path / "finance-out"),
                "Legal": str(tmp_path / "legal-out"),
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["destination_roots"] == {
        "Finance": str(tmp_path / "finance-out"),
        "Legal": str(tmp_path / "legal-out"),
    }


def test_destination_routes_default_to_standard_output_for_unmapped_destinees(monkeypatch, tmp_path):
    main, _, _ = load_api(monkeypatch, tmp_path)
    client = TestClient(main.app)

    response = client.post(
        "/api/classification/config",
        json={
            "destinees": ["Finance", "Legal"],
            "destination_roots": {"Finance": str(tmp_path / "finance-out")},
        },
    )

    assert response.status_code == 200
    assert response.json()["destination_roots"] == {"Finance": str(tmp_path / "finance-out")}
    legal_route = client.post("/api/classification/route", json={"destinee": "Legal", "filename": "invoice.pdf"})
    assert legal_route.status_code == 200
    root_path = Path(legal_route.json()["root_path"])
    assert root_path.name == "Legal"
    assert "destination" in root_path.parent.name.lower()


def test_destination_route_names_must_match_configured_destinees(monkeypatch, tmp_path):
    main, _, _ = load_api(monkeypatch, tmp_path)
    client = TestClient(main.app)

    response = client.post(
        "/api/classification/config",
        json={
            "destinees": ["Finance"],
            "destination_roots": {"Unknown": str(tmp_path / "shadow-out")},
        },
    )

    assert response.status_code == 422


def test_route_planner_uses_configured_destination_root(monkeypatch, tmp_path):
    main, _, _ = load_api(monkeypatch, tmp_path)
    client = TestClient(main.app)
    finance_root = tmp_path / "finance-root"
    finance_root.mkdir()

    client.post(
        "/api/classification/config",
        json={
            "destinees": ["Finance"],
            "destination_roots": {"Finance": str(finance_root)},
        },
    )

    response = client.post(
        "/api/classification/route",
        json={"destinee": "Finance", "filename": "invoice.pdf"},
    )

    assert response.status_code == 200
    assert response.json()["destination_path"] == str(finance_root / "invoice.pdf")
    assert response.json()["resolved_destinee"] == "Finance"


def test_route_planner_rejects_unknown_destinee(monkeypatch, tmp_path):
    main, _, _ = load_api(monkeypatch, tmp_path)
    client = TestClient(main.app)

    response = client.post(
        "/api/classification/route",
        json={"destinee": "Unknown", "filename": "invoice.pdf"},
    )

    assert response.status_code == 400
    assert "not configured" in response.json()["detail"].lower()


def test_valid_nas_source_root_is_accepted(monkeypatch, tmp_path):
    main, _, _ = load_api(monkeypatch, tmp_path)
    client = TestClient(main.app)
    source_root = tmp_path / "nas-shared"
    source_root.mkdir()

    response = client.post(
        "/api/classification/config",
        json={
            "destinees": ["Finance"],
            "source_roots": [str(source_root)],
        },
    )

    assert response.status_code == 200
    assert response.json()["source_roots"] == [str(source_root)]


def test_invalid_unreachable_source_root_is_rejected(monkeypatch, tmp_path):
    main, _, _ = load_api(monkeypatch, tmp_path)
    client = TestClient(main.app)
    invalid_root = tmp_path / "missing-network-share"

    response = client.post(
        "/api/classification/config",
        json={
            "destinees": ["Finance"],
            "source_roots": [str(invalid_root)],
        },
    )

    assert response.status_code == 422


def test_scan_input_directory_uses_configured_source_roots(monkeypatch, tmp_path):
    main, _, _ = load_api(monkeypatch, tmp_path)
    source_a = tmp_path / "source-a"
    source_b = tmp_path / "source-b"
    source_a.mkdir()
    source_b.mkdir()
    (source_a / "invoice.pdf").write_bytes(b"pdf-a")
    (source_b / "receipt.pdf").write_bytes(b"pdf-b")

    response = TestClient(main.app).post(
        "/api/classification/config",
        json={"destinees": ["Finance"], "source_roots": [str(source_a), str(source_b)]},
    )
    assert response.status_code == 200

    scan_response = TestClient(main.app).post("/api/classification/scan")
    assert scan_response.status_code == 200
    names = {file["name"] for file in scan_response.json()["files"]}
    assert {"invoice.pdf", "receipt.pdf"}.issubset(names)


def test_update_config_rejects_path_separator(monkeypatch, tmp_path):
    main, _, _ = load_api(monkeypatch, tmp_path)
    response = TestClient(main.app).post(
        "/api/classification/config",
        json={"destinees": ["../outside"]},
    )

    assert response.status_code == 422


def test_configuration_interface_is_separate_from_work_interface(monkeypatch, tmp_path):
    load_api(monkeypatch, tmp_path)
    config_html = Path("frontend/config.html")
    index_html = Path("frontend/index.html")

    assert config_html.exists()
    assert "destinee-form" in config_html.read_text(encoding="utf-8")
    assert "config.js" in config_html.read_text(encoding="utf-8")
    assert "config.js" not in index_html.read_text(encoding="utf-8")


def test_mark_document_private_schedules_cleanup_and_removes_logs(monkeypatch, tmp_path):
    main, source, destination = load_api(monkeypatch, tmp_path)
    client = TestClient(main.app)
    (source / "invoice.pdf").write_bytes(b"prepared pdf")

    response = client.post(
        "/api/documents/invoice.pdf/private",
        json={"private": True, "delete_after_minutes": 60},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "private"
    assert main.read_document_states()["invoice.pdf"]["private"] is True

    destination_dir = destination / "Finance"
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination_file = destination_dir / "invoice.pdf"
    destination_file.write_bytes(b"prepared pdf")

    main.write_document_state(
        "invoice.pdf",
        "private",
        private=True,
        source_path=str(source / "invoice.pdf"),
        destination_path=str(destination_file),
        delete_after=(datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
    )
    main.APPROVAL_AUDIT_PATH.write_text('{"entries":[{"filename":"invoice.pdf","action":"finalize"}]}', encoding="utf-8")
    main.JOB_STATUS_PATH.write_text('{"job-1": {"filename": "invoice.pdf", "status": "queued"}}', encoding="utf-8")

    removed = main.cleanup_private_documents(datetime.now(timezone.utc))

    assert "invoice.pdf" in removed
    assert not (source / "invoice.pdf").exists()
    assert not destination_file.exists()
    assert main.read_approval_audit()["entries"] == []
    assert "job-1" not in main.read_job_store()


@pytest.mark.asyncio
async def test_startup_event_schedules_private_retention_worker(monkeypatch):
    import app.main as main

    created = {}
    fake_task = object()

    def fake_create_task(coro):
        created["coro"] = coro
        return fake_task

    monkeypatch.setattr(main.asyncio, "create_task", fake_create_task)
    main._cleanup_task = None

    await main.startup_event()

    assert main._cleanup_task is fake_task
    assert created["coro"] is not None


def test_scan_returns_completed_pdfs_only(monkeypatch, tmp_path):
    main, source, _ = load_api(monkeypatch, tmp_path)
    (source / "invoice.pdf").write_bytes(b"pdf")
    (source / "partial.tmp").write_bytes(b"partial")
    (source / ".hidden.pdf").write_bytes(b"hidden")

    response = TestClient(main.app).post("/api/classification/scan")

    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert response.json()["files"][0]["name"] == "invoice.pdf"


def test_get_document_returns_metadata(monkeypatch, tmp_path):
    main, source, _ = load_api(monkeypatch, tmp_path)
    document = source / "invoice.pdf"
    document.write_bytes(b"pdf")

    response = TestClient(main.app).get("/api/documents/invoice.pdf")

    assert response.status_code == 200
    assert response.json()["name"] == "invoice.pdf"
    assert response.json()["size"] == 3


def test_get_document_rejects_path_traversal(monkeypatch, tmp_path):
    main, source, _ = load_api(monkeypatch, tmp_path)
    (tmp_path / "outside.pdf").write_bytes(b"pdf")

    response = TestClient(main.app).get("/api/documents/..%2Foutside.pdf")

    assert response.status_code == 404


def test_prepare_marks_readable_pdf_for_local_processing(monkeypatch, tmp_path):
    main, source, _ = load_api(monkeypatch, tmp_path)
    document = source / "invoice.pdf"
    with __import__("pymupdf").open() as pdf:
        page = pdf.new_page()
        page.insert_text((72, 72), "Invoice Amount Due VAT")
        pdf.save(document)

    response = TestClient(main.app).post("/api/documents/invoice.pdf/prepare")

    assert response.status_code == 200
    payload = response.json()
    assert payload["readable"] is True
    assert payload["route"] == "local-preprocessing"
    assert payload["queue_status"] == "ready_for_review"
    assert payload["processing_strategy"] == "local-rule-engine"
    assert main.read_document_states()["invoice.pdf"]["processing_strategy"] == "local-rule-engine"


def test_prepare_marks_blank_pdf_for_ocr_fallback(monkeypatch, tmp_path):
    main, source, _ = load_api(monkeypatch, tmp_path)
    document = source / "scan-001.pdf"
    with __import__("pymupdf").open() as pdf:
        pdf.new_page()
        pdf.save(document)

    response = TestClient(main.app).post("/api/documents/scan-001.pdf/prepare")

    assert response.status_code == 200
    payload = response.json()
    assert payload["readable"] is False
    assert payload["route"] == "ocr-fallback"
    assert payload["queue_status"] == "awaiting_ocr"
    assert payload["processing_strategy"] == "ocr-fallback"
    assert main.read_document_states()["scan-001.pdf"]["processing_strategy"] == "ocr-fallback"


def test_prepare_reports_quality_and_provider_recommendation(monkeypatch, tmp_path):
    main, source, _ = load_api(monkeypatch, tmp_path)
    document = source / "invoice.pdf"
    with __import__("pymupdf").open() as pdf:
        page = pdf.new_page()
        page.insert_text((72, 72), "Invoice due for tax and payment")
        pdf.save(document)

    response = TestClient(main.app).post("/api/documents/invoice.pdf/prepare")

    assert response.status_code == 200
    payload = response.json()
    assert 0.0 <= payload["quality_score"] <= 1.0
    assert payload["recommended_provider"] in {"local", "gemini"}
    assert payload["route"] in {"local-preprocessing", "ocr-fallback"}


def test_prepare_uses_local_rule_engine_for_invoice_intent(monkeypatch, tmp_path):
    main, source, _ = load_api(monkeypatch, tmp_path)
    client = TestClient(main.app)
    client.post("/api/classification/config", json={"destinees": ["Finance", "Legal", "Operations"]})
    document = source / "invoice.pdf"
    with __import__("pymupdf").open() as pdf:
        page = pdf.new_page()
        page.insert_text((72, 72), "Invoice Amount Due VAT payment")
        pdf.save(document)

    response = client.post("/api/documents/invoice.pdf/prepare")

    assert response.status_code == 200
    payload = response.json()
    assert payload["processing_strategy"] == "local-rule-engine"
    assert payload["local_classification"]["intent"] == "invoice"
    assert payload["local_classification"]["destinee"] == "Finance"
    assert payload["local_classification"]["confidence"] >= 0.75


def test_prepare_routes_low_quality_text_through_gemini_enrichment(monkeypatch, tmp_path):
    main, source, _ = load_api(monkeypatch, tmp_path)
    document = source / "low-quality.pdf"
    with __import__("pymupdf").open() as pdf:
        page = pdf.new_page()
        page.insert_text((72, 72), "x x x x x x x x x x x x")
        pdf.save(document)

    response = TestClient(main.app).post("/api/documents/low-quality.pdf/prepare")

    assert response.status_code == 200
    payload = response.json()
    assert payload["readable"] is True
    assert payload["processing_strategy"] == "gemini-enrichment"
    assert payload["recommended_provider"] == "gemini"
    assert main.read_document_states()["low-quality.pdf"]["processing_strategy"] == "gemini-enrichment"


def test_prepare_reports_benchmark_metadata_for_each_processing_strategy(monkeypatch, tmp_path):
    main, source, _ = load_api(monkeypatch, tmp_path)

    readable_pdf = source / "invoice.pdf"
    with __import__("pymupdf").open() as pdf:
        page = pdf.new_page()
        page.insert_text((72, 72), "Invoice Amount Due VAT")
        pdf.save(readable_pdf)

    blank_pdf = source / "scan.pdf"
    with __import__("pymupdf").open() as pdf:
        pdf.new_page()
        pdf.save(blank_pdf)

    readable = TestClient(main.app).post("/api/documents/invoice.pdf/prepare").json()
    blank = TestClient(main.app).post("/api/documents/scan.pdf/prepare").json()

    assert readable["processing_profile"]["provider"] == "local"
    assert readable["processing_profile"]["estimated_cost_usd"] == 0.0
    assert readable["processing_profile"]["median_latency_ms"] >= 100
    assert blank["processing_profile"]["provider"] == "tesseract"
    assert blank["processing_profile"]["estimated_cost_usd"] == 0.0


def test_prepare_async_returns_queued_job_and_persists_status(monkeypatch, tmp_path):
    main, source, _ = load_api(monkeypatch, tmp_path)
    document = source / "invoice.pdf"
    with __import__("pymupdf").open() as pdf:
        page = pdf.new_page()
        page.insert_text((72, 72), "Invoice Amount Due VAT")
        pdf.save(document)

    response = TestClient(main.app).post("/api/documents/invoice.pdf/prepare?async=true")

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "queued"
    assert payload["job_id"]
    job = TestClient(main.app).get(f"/api/jobs/{payload['job_id']}").json()
    assert job["filename"] == "invoice.pdf"
    assert job["status"] in {"queued", "processing", "ready", "failed"}


def test_queue_summary_and_retry_flow_exposes_hardening_status(monkeypatch, tmp_path):
    main, source, _ = load_api(monkeypatch, tmp_path)
    document = source / "invoice.pdf"
    with __import__("pymupdf").open() as pdf:
        page = pdf.new_page()
        page.insert_text((72, 72), "Invoice Amount Due VAT")
        pdf.save(document)

    client = TestClient(main.app)
    queued = client.post("/api/documents/invoice.pdf/prepare?async=true").json()
    summary = client.get("/api/jobs/summary").json()

    assert summary["total_jobs"] >= 1
    assert summary["ready"] >= 1
    retry_response = client.post(f"/api/jobs/{queued['job_id']}/retry")
    assert retry_response.status_code == 200
    retried_job = client.get(f"/api/jobs/{queued['job_id']}").json()
    assert retried_job["status"] == "queued"
    assert retried_job["retry_count"] >= 1


def test_admin_dashboard_summary_exposes_health_metrics(monkeypatch, tmp_path):
    main, source, _ = load_api(monkeypatch, tmp_path)
    document = source / "invoice.pdf"
    with __import__("pymupdf").open() as pdf:
        page = pdf.new_page()
        page.insert_text((72, 72), "Invoice Amount Due VAT")
        pdf.save(document)

    client = TestClient(main.app)
    client.post("/api/documents/invoice.pdf/prepare?async=true")
    summary = client.get("/api/jobs/summary").json()

    assert summary["status_breakdown"]["ready"] >= 1
    assert "average_latency_ms" in summary
    assert "failure_rate" in summary
    assert "local_resolution_rate" in summary
    assert "ai_resolution_rate" in summary
    assert summary["jobs"][0]["filename"] == "invoice.pdf"
    assert "quality_score" in summary["jobs"][0]


def test_queue_summary_counts_ready_for_review_as_ready(monkeypatch, tmp_path):
    main, source, _ = load_api(monkeypatch, tmp_path)
    document = source / "invoice.pdf"
    with __import__("pymupdf").open() as pdf:
        page = pdf.new_page()
        page.insert_text((72, 72), "Invoice Amount Due VAT")
        pdf.save(document)

    client = TestClient(main.app)
    queued = client.post("/api/documents/invoice.pdf/prepare?async=true").json()
    jobs = main.read_job_store()
    queued_job = jobs[queued["job_id"]]
    queued_job["status"] = "queued"
    queued_job["queue_status"] = "ready_for_review"
    main.JOB_STATUS_PATH.write_text(__import__("json").dumps(jobs, indent=2), encoding="utf-8")

    summary = client.get("/api/jobs/summary").json()

    assert summary["status_breakdown"]["ready"] >= 1
    assert summary["status_breakdown"]["queued"] == 0


def test_scan_input_directory_exposes_queue_status_for_ui(monkeypatch, tmp_path):
    main, source, _ = load_api(monkeypatch, tmp_path)
    document = source / "invoice.pdf"
    with __import__("pymupdf").open() as pdf:
        page = pdf.new_page()
        page.insert_text((72, 72), "Invoice Amount Due VAT")
        pdf.save(document)

    main.write_document_state("invoice.pdf", "in_review", queue_status="ready_for_review", processing_id="abc123")

    result = main.scan_input_directory()
    file_entry = next(item for item in result["files"] if item["name"] == "invoice.pdf")

    assert file_entry["queue_status"] == "ready_for_review"
    assert file_entry["status"] == "in_review"


def test_background_prewarm_scheduler_prepares_new_pdfs(monkeypatch, tmp_path):
    main, source, _ = load_api(monkeypatch, tmp_path)
    document = source / "invoice.pdf"
    with __import__("pymupdf").open() as pdf:
        page = pdf.new_page()
        page.insert_text((72, 72), "Invoice Amount Due VAT")
        pdf.save(document)

    processed = main.prewarm_pending_documents()

    assert processed == 1
    state = main.read_document_states().get("invoice.pdf", {})
    assert state.get("status") == "in_review"
    assert state.get("processing_id")
    assert state.get("suggested_filename", "").endswith(".pdf")


def test_finalize_prepared_document_creates_destinee_file(monkeypatch, tmp_path):
    main, source, destination = load_api(monkeypatch, tmp_path)
    document = source / "invoice.pdf"
    document.write_bytes(b"prepared pdf")
    client = TestClient(main.app)
    prepared = client.post("/api/documents/invoice.pdf/prepare").json()

    response = client.post(
        "/api/documents/invoice.pdf/finalize",
        json={"processing_id": prepared["processing_id"], "destinee": "Destinee A"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "classified"
    assert (destination / "Destinee A" / "invoice.pdf").read_bytes() == b"prepared pdf"


def test_finalize_respects_configured_route_override_and_default_fallback(monkeypatch, tmp_path):
    main, source, destination = load_api(monkeypatch, tmp_path)
    client = TestClient(main.app)
    custom_root = tmp_path / "custom-route"
    custom_root.mkdir()

    client.post(
        "/api/classification/config",
        json={
            "destinees": ["Finance", "Legal"],
            "source_roots": [str(source)],
            "destination_roots": {"Finance": str(custom_root)},
        },
    )

    finance_document = source / "finance.pdf"
    finance_document.write_bytes(b"finance pdf")
    finance_prepared = client.post("/api/documents/finance.pdf/prepare").json()

    finance_response = client.post(
        "/api/documents/finance.pdf/finalize",
        json={"processing_id": finance_prepared["processing_id"], "destinee": "Finance"},
    )

    assert finance_response.status_code == 200
    assert finance_response.json()["destination_path"] == str(custom_root / "finance.pdf")
    assert (custom_root / "finance.pdf").read_bytes() == b"finance pdf"

    legal_document = source / "legal.pdf"
    legal_document.write_bytes(b"legal pdf")
    legal_prepared = client.post("/api/documents/legal.pdf/prepare").json()

    legal_response = client.post(
        "/api/documents/legal.pdf/finalize",
        json={"processing_id": legal_prepared["processing_id"], "destinee": "Legal"},
    )

    assert legal_response.status_code == 200
    assert legal_response.json()["destination_path"] == str(destination / "Legal" / "legal.pdf")
    assert (destination / "Legal" / "legal.pdf").read_bytes() == b"legal pdf"


def test_finalize_writes_to_destinee_root_not_source_subfolder(monkeypatch, tmp_path):
    main, source, destination = load_api(monkeypatch, tmp_path)
    nested_source = source / "nested"
    nested_source.mkdir()
    document = nested_source / "invoice.pdf"
    document.write_bytes(b"nested pdf")

    client = TestClient(main.app)
    client.post("/api/classification/config", json={"destinees": ["Finance"], "source_roots": [str(source)]})
    prepared = client.post("/api/documents/nested/invoice.pdf/prepare").json()

    response = client.post(
        "/api/documents/nested/invoice.pdf/finalize",
        json={"processing_id": prepared["processing_id"], "destinee": "Finance"},
    )

    assert response.status_code == 200
    assert response.json()["destination_path"] == str(destination / "Finance" / "invoice.pdf")
    assert (destination / "Finance" / "invoice.pdf").read_bytes() == b"nested pdf"
    assert not (destination / "Finance" / "nested" / "invoice.pdf").exists()


def test_approval_roles_are_enforced_and_audited(monkeypatch, tmp_path):
    main, source, _ = load_api(monkeypatch, tmp_path)
    (source / "invoice.pdf").write_bytes(b"prepared pdf")
    client = TestClient(main.app)
    client.post("/api/classification/config", json={"destinees": ["Destinee A"]})
    prepared = client.post("/api/documents/invoice.pdf/prepare").json()

    blocked = client.post(
        "/api/documents/invoice.pdf/finalize",
        json={"processing_id": prepared["processing_id"], "destinee": "Destinee A", "actor": "reviewer-1", "role": "reviewer"},
    )
    assert blocked.status_code == 403

    allowed = client.post(
        "/api/documents/invoice.pdf/finalize",
        json={"processing_id": prepared["processing_id"], "destinee": "Destinee A", "actor": "approver-1", "role": "approver"},
    )
    assert allowed.status_code == 200

    audit = client.get("/api/approval/audit").json()
    assert any(entry["action"] == "finalize" and entry["actor"] == "approver-1" for entry in audit["entries"])


def test_finalize_rejects_unknown_destinee(monkeypatch, tmp_path):
    main, source, _ = load_api(monkeypatch, tmp_path)
    (source / "invoice.pdf").write_bytes(b"prepared pdf")
    client = TestClient(main.app)
    client.post("/api/classification/config", json={"destinees": ["Destinee A"]})
    prepared = client.post("/api/documents/invoice.pdf/prepare").json()

    response = client.post(
        "/api/documents/invoice.pdf/finalize",
        json={"processing_id": prepared["processing_id"], "destinee": "Unknown"},
    )

    assert response.status_code == 400


def test_finalize_rejects_unsafe_output_filename(monkeypatch, tmp_path):
    main, source, _ = load_api(monkeypatch, tmp_path)
    (source / "invoice.pdf").write_bytes(b"prepared pdf")
    client = TestClient(main.app)
    prepared = client.post("/api/documents/invoice.pdf/prepare").json()

    response = client.post(
        "/api/documents/invoice.pdf/finalize",
        json={
            "processing_id": prepared["processing_id"],
            "destinee": "Destinee A",
            "output_filename": "../outside.pdf",
        },
    )

    assert response.status_code == 422


def test_analyze_document_suggests_invoice_filename(monkeypatch, tmp_path):
    main, source, _ = load_api(monkeypatch, tmp_path)
    (source / "scan-001.pdf").write_bytes(b"placeholder")
    client = TestClient(main.app)

    from pymupdf import open as open_pdf

    pdf = open_pdf()
    page = pdf.new_page()
    page.insert_text((72, 72), "Invoice Amount Due VAT")
    pdf.save(source / "scan-001.pdf")
    pdf.close()
    prepared = client.post("/api/documents/scan-001.pdf/prepare").json()

    response = client.post(
        "/api/documents/scan-001.pdf/analyze",
        params={"processing_id": prepared["processing_id"]},
    )

    assert response.status_code == 200
    assert response.json()["topic"] == "Invoice"
    assert response.json()["suggested_filename"] == "undated_Invoice_scan-001.pdf"


def test_analyze_document_uses_cached_gemini_proposal(monkeypatch, tmp_path):
    main, source, _ = load_api(monkeypatch, tmp_path)
    (source / "scan-001.pdf").write_bytes(b"placeholder")
    client = TestClient(main.app)

    from pymupdf import open as open_pdf

    pdf = open_pdf()
    page = pdf.new_page()
    page.insert_text((72, 72), "Invoice Amount Due VAT")
    pdf.save(source / "scan-001.pdf")
    pdf.close()

    prepared = client.post("/api/documents/scan-001.pdf/prepare").json()
    calls = {"count": 0}

    def fake_gemini(text, filename, pdf_obj=None, layout=None):
        calls["count"] += 1
        base = main.analyze_text(text, filename)
        return {
            **base,
            "category": "Invoice",
            "language": "en",
            "confidence": 0.99,
            "date": "2026-08-24",
            "summary": "Invoice due for payment.",
            "suggested_filename": "invoice_cached.pdf",
            "analysis_source": "gemini",
            "signals": ["Gemini analyzed document content"],
        }

    monkeypatch.setattr(main, "analyze_with_gemini", fake_gemini)
    first_response = client.post(
        "/api/documents/scan-001.pdf/analyze",
        params={"processing_id": prepared["processing_id"]},
    )

    assert first_response.status_code == 200
    assert first_response.json()["suggested_filename"] == "invoice_cached.pdf"
    assert calls["count"] == 1

    second_prepared = client.post("/api/documents/scan-001.pdf/prepare").json()

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("Gemini should not be called again for a cached filename")

    monkeypatch.setattr(main, "analyze_with_gemini", fail_if_called)
    second_response = client.post(
        "/api/documents/scan-001.pdf/analyze",
        params={"processing_id": second_prepared["processing_id"]},
    )

    assert second_response.status_code == 200
    assert second_response.json()["suggested_filename"] == "invoice_cached.pdf"


def test_prepare_does_not_run_ocr_for_blank_pages(monkeypatch, tmp_path):
    main, source, _ = load_api(monkeypatch, tmp_path)
    (source / "blank.pdf").write_bytes(b"placeholder")
    client = TestClient(main.app)

    from pymupdf import open as open_pdf

    pdf = open_pdf()
    pdf.new_page()
    pdf.save(source / "blank.pdf")
    pdf.close()

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("OCR should not run during prepare")

    monkeypatch.setattr(main.subprocess, "run", fail_if_called)
    prepared = client.post("/api/documents/blank.pdf/prepare").json()

    assert prepared["page_count"] == 1
    assert prepared["pages"][0]["text"] == ""
    assert prepared["ocr_used"] is False


def test_reorder_pages_updates_processing_order(monkeypatch, tmp_path):
    main, source, _ = load_api(monkeypatch, tmp_path)
    (source / "reorder.pdf").write_bytes(b"placeholder")
    client = TestClient(main.app)

    from pymupdf import open as open_pdf

    pdf = open_pdf()
    for text in ["First page", "Second page", "Third page"]:
        page = pdf.new_page()
        page.insert_text((72, 72), text)
    pdf.save(source / "reorder.pdf")
    pdf.close()

    prepared = client.post("/api/documents/reorder.pdf/prepare").json()
    response = client.post(
        "/api/documents/reorder.pdf/reorder-pages",
        json={"processing_id": prepared["processing_id"], "page_order": [3, 1, 2]},
    )

    assert response.status_code == 200
    with main.fitz.open(main.TEMP_PATH / "processing" / prepared["processing_id"] / "original.pdf") as reordered:
        pages = [page.get_text().strip() for page in reordered]
    assert pages == ["Third page", "First page", "Second page"]


def test_split_document_creates_ordered_parts(monkeypatch, tmp_path):
    main, source, _ = load_api(monkeypatch, tmp_path)
    (source / "split.pdf").write_bytes(b"placeholder")
    client = TestClient(main.app)

    from pymupdf import open as open_pdf

    pdf = open_pdf()
    for text in ["First page", "Second page", "Third page"]:
        page = pdf.new_page()
        page.insert_text((72, 72), text)
    pdf.save(source / "split.pdf")
    pdf.close()

    prepared = client.post("/api/documents/split.pdf/prepare").json()
    response = client.post(
        "/api/documents/split.pdf/split",
        json={"processing_id": prepared["processing_id"], "split_pages": [2]},
    )

    assert response.status_code == 200
    assert response.json()["part_count"] == 2
    assert [part["start_page"] for part in response.json()["parts"]] == [1, 2]


def test_merge_documents_creates_single_output(monkeypatch, tmp_path):
    main, source, destination = load_api(monkeypatch, tmp_path)
    client = TestClient(main.app)

    from pymupdf import open as open_pdf

    for name, text in [("first.pdf", "Invoice first page"), ("second.pdf", "Invoice second page")]:
        pdf = open_pdf()
        page = pdf.new_page()
        page.insert_text((72, 72), text)
        pdf.save(source / name)
        pdf.close()

    response = client.post(
        "/api/documents/merge",
        json={
            "documents": ["first.pdf", "second.pdf"],
            "destinee": "Destinee A",
            "output_filename": "merged-invoice.pdf",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "classified"
    assert (destination / "Destinee A" / "merged-invoice.pdf").exists()
    assert payload["filename"] == "merged-invoice.pdf"
