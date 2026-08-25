"""Focused tests for the n8n handoff and destinee configuration API."""

import importlib

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


def test_get_default_classification_config(monkeypatch, tmp_path):
    main, _, _ = load_api(monkeypatch, tmp_path)
    response = TestClient(main.app).get("/api/classification/config")

    assert response.status_code == 200
    assert response.json()["destinees"] == []
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
