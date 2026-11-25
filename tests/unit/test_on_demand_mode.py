"""On-demand mode (issue #53): no background polling, an idle signal for the host, wake notice."""

import asyncio
import importlib
from pathlib import Path

from fastapi.testclient import TestClient


def load_api(monkeypatch, tmp_path, scan_seconds=None):
    for name in ("source", "destination", "archive", "dismissed", "temp"):
        (tmp_path / name).mkdir(exist_ok=True)
    monkeypatch.setenv("RAW_INPUT_PATH", str(tmp_path / "source"))
    monkeypatch.setenv("CLASSIFIED_OUTPUT_PATH", str(tmp_path / "destination"))
    monkeypatch.setenv("PROCESSED_ARCHIVE_PATH", str(tmp_path / "archive"))
    monkeypatch.setenv("DISMISSED_ARCHIVE_PATH", str(tmp_path / "dismissed"))
    monkeypatch.setenv("CLASSIFICATION_CONFIG_PATH", str(tmp_path / "config.json"))
    monkeypatch.setenv("DOCUMENTS_STATUS_PATH", str(tmp_path / "documents.json"))
    monkeypatch.setenv("ANALYSIS_STATUS_PATH", str(tmp_path / "analysis-status.json"))
    monkeypatch.setenv("TEMP_PATH", str(tmp_path / "temp"))
    monkeypatch.setenv("NOTIFICATION_SUBSCRIPTIONS_PATH", str(tmp_path / "notifications.json"))
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    if scan_seconds is None:
        monkeypatch.delenv("BACKGROUND_SCAN_SECONDS", raising=False)
    else:
        monkeypatch.setenv("BACKGROUND_SCAN_SECONDS", str(scan_seconds))
    import app.main as main
    return importlib.reload(main)


def test_default_is_on_demand_mode(monkeypatch, tmp_path):
    main = load_api(monkeypatch, tmp_path)
    assert main.BACKGROUND_SCAN_SECONDS == 0


def test_readme_has_an_upgrade_note_for_the_new_default():
    readme = Path("README.md").read_text(encoding="utf-8")
    assert "## Upgrading" in readme
    assert "BACKGROUND_SCAN_SECONDS=30" in readme
    assert "https://classifier.example.com/api/classification/prewarm" in readme


def test_on_demand_mode_runs_one_prewarm_pass_and_stops(monkeypatch, tmp_path):
    main = load_api(monkeypatch, tmp_path, scan_seconds=0)
    calls = []
    monkeypatch.setattr(main, "prewarm_pending_documents", lambda: calls.append(1) or 0)

    # Returns by itself instead of looping; a hang here fails the test via the timeout.
    asyncio.run(asyncio.wait_for(main.prewarm_worker(), timeout=5))

    assert calls == [1]


def test_polling_mode_keeps_scanning(monkeypatch, tmp_path):
    main = load_api(monkeypatch, tmp_path, scan_seconds=30)
    calls = []
    monkeypatch.setattr(main, "prewarm_pending_documents", lambda: calls.append(1) or 0)

    async def run_briefly():
        task = asyncio.create_task(main.prewarm_worker())
        await asyncio.sleep(0.05)
        assert not task.done(), "the polling worker must keep running"
        task.cancel()

    asyncio.run(run_briefly())
    assert calls == [1]


def test_activity_reports_idle_and_does_not_count_itself(monkeypatch, tmp_path):
    main = load_api(monkeypatch, tmp_path, scan_seconds=0)
    client = TestClient(main.app)

    first = client.get("/api/activity").json()
    assert first["busy"] is False
    assert first["in_flight"] == 0
    assert first["background_scan_seconds"] == 0
    assert first["next_private_deletion"] is None

    # Polling the probe must not reset the idle clock.
    main._last_activity -= 120
    again = client.get("/api/activity").json()
    assert again["idle_seconds"] >= 120


def test_other_requests_reset_the_idle_clock(monkeypatch, tmp_path):
    main = load_api(monkeypatch, tmp_path, scan_seconds=0)
    client = TestClient(main.app)
    main._last_activity -= 600

    client.get("/api/ingestion/status")

    assert client.get("/api/activity").json()["idle_seconds"] < 5


def test_activity_is_busy_while_work_runs(monkeypatch, tmp_path):
    main = load_api(monkeypatch, tmp_path, scan_seconds=0)
    client = TestClient(main.app)

    with main.tracked_activity():
        assert client.get("/api/activity").json()["busy"] is True
    assert client.get("/api/activity").json()["busy"] is False


def test_next_private_deletion_is_the_earliest_pending_one(monkeypatch, tmp_path):
    main = load_api(monkeypatch, tmp_path, scan_seconds=0)
    monkeypatch.setattr(main, "read_document_states", lambda: {
        "late.pdf": {"private": True, "delete_after": "2026-12-01T10:00:00+00:00"},
        "early.pdf": {"private": True, "delete_after": "2026-11-30T08:00:00+00:00"},
        "public.pdf": {"private": False, "delete_after": "2026-11-29T00:00:00+00:00"},
        "broken.pdf": {"private": True, "delete_after": "not a date"},
        "odd": "not a dict",
    })

    assert TestClient(main.app).get("/api/activity").json()["next_private_deletion"] == "2026-11-30T08:00:00+00:00"


def test_frontend_shows_a_wake_notice_for_slow_requests():
    notice_js = Path("frontend/wake-notice.js").read_text(encoding="utf-8")
    assert "WAKE_NOTICE_DELAY_MS" in notice_js
    for page, script in (("frontend/index.html", "app.js"), ("frontend/config.html", "config.js")):
        html = Path(page).read_text(encoding="utf-8")
        assert 'id="wake-notice"' in html, page
        # The wrapper has to wrap fetch before the page script makes its first request.
        assert html.index("wake-notice.js") < html.index(script), page


def test_prewarm_pass_does_not_block_the_event_loop(monkeypatch, tmp_path):
    """A long prewarm pass (OCR, Gemini) must not stop the server from answering, e.g. the health check."""
    import time

    main = load_api(monkeypatch, tmp_path, scan_seconds=0)
    monkeypatch.setattr(main, "prewarm_pending_documents", lambda: time.sleep(1.0) or 0)

    async def scenario():
        task = asyncio.create_task(main.prewarm_worker())
        started = time.monotonic()
        await asyncio.sleep(0.05)              # meanwhile the 1 s pass runs; a request would wait here
        waited = time.monotonic() - started
        await task
        return waited

    assert asyncio.run(scenario()) < 0.5
