# Document Processing Pipeline - System Specification

**Version:** 1.0  
**Date:** 2026-08-17  
**Status:** Active Specification  

---

## Executive Summary

A budget-friendly, configurable document processing pipeline with AI-assisted UI hosted on Synology NAS. n8n handles external ingestion and places incoming files in a mounted local source directory. The classifier owns local processing, first-level destinee classification, and output routing beneath configurable local folders. Lightweight local execution complements cheap cloud AI micro-services (vision/text classification), delivering a responsive user experience with strict cost controls and operational flexibility.

---

## 1. System Architecture

### 1.1 High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│ Configurable Document Source (Pluggable Backend)                     │
│ • Google Drive Folder (Primary)                                      │
│ • Local NAS Upload                                                   │
│ • SharePoint Site (future)                                           │
│ • Dropbox (future)                                                   │
└────────────────────┬─────────────────────────────────────────────────┘
                     │ (Multi-page PDF)
                     ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Synology DS923+ (Docker Container Environment)                       │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │ Frontend Layer                                                 │ │
│  │ • Native HTML, CSS, and browser JavaScript                   │ │
│  │ • Destinee Configuration UI                                  │ │
│  │ • Client-side PDF rendering & manipulation                    │ │
│  │ • Interactive split point visualization                       │ │
│  │ • Real-time thumbnail generation                              │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │ Backend Layer                                                  │ │
│  │ • FastAPI (Python 3.9+)                                       │ │
│  │ • PyMuPDF for PDF manipulation                                 │ │
│  │ • Tesseract OCR (optional, local)                              │ │
│  │ • Local embeddings computation                                 │ │
│  │ • Storage Backend Manager (abstract factory pattern)           │ │
│  │ • n8n handoff monitoring and local output routing               │ │
│  │ • API orchestration & caching                                  │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
└─────┬──────────────────────────────────────────────────────────┬────┘
      │                                                          │
      ▼                                                          ▼
    ┌────────────────────┐                    ┌──────────────────────────┐
    │ Cloud AI Services  │                    │ User Web Interface       │
    │ • Gemini 1.5 Flash │                    │ • Configure Source       │
    │ • Claude 3 Haiku   │                    │ • Configure Destination  │
    │ (Vision + Text)    │                    │ • Split point toggle     │
    └────────────────────┘                    │ • Page rotation controls │
             │                                │ • Metadata form fields   │
             ▼                                │ • Batch group review     │
    ┌────────────────────┐                    │ • One-click finalize     │
    │ Classification &   │                    └──────────────────────────┘
    │ Split Suggestions  │
    └────────────────────┘
             │
             ▼
    ┌──────────────────────────────────────────────────────────────┐
    │ Configurable Output Routing (Pluggable Backend)              │
    ├──────────────────────────────────────────────────────────────┤
    │ • Google Drive Folder (Primary)                              │
    │ • Local NAS Storage                                          │
    │ • SharePoint / Microsoft 365                                 │
    │ • Dropbox (future)                                           │
    │ • Raw originals: /data/source                                  │
    │ • Destinee output: /data/destination/<destinee>/              │
    └──────────────────────────────────────────────────────────────┘
```

### 1.2 Component Dependencies

| Component | Purpose | Technology | Resource Requirement |
|-----------|---------|-----------|----------------------|
| Frontend | User Interface + Config | Native HTML, CSS, JavaScript | Static files |
| Backend | API & Business Logic | FastAPI + Python 3.9+ | ~400MB RAM |
| PDF Engine | Document Manipulation | PyMuPDF | Native binary (~50MB) |
| OCR Engine | Text Extraction (Optional) | Tesseract OCR | ~300MB (if installed) |
| AI/Vision API | Classification & Splitting | Cloud (Gemini/Claude) | API credential |
| Storage Backend | Document Source/Destination | Pluggable (Google Drive, NAS, SharePoint) | Depends on backend |
| Backend Manager | Abstract Storage Layer | Python (ABC pattern) | ~10MB code |

---

## 2. Technical Specifications

### 2.1 Hardware Requirements

**Minimum (Functional):**
- AMD Ryzen R1600 CPU (DS923+ standard)
- 4GB RAM (NAS base)
- 100GB free disk space (raw archives)

**Recommended:**
- 8-16GB RAM upgrade (for concurrent OCR processing)
- 500GB+ SSD cache volume (for temp processing)
- 1TB+ dedicated archive volume

### 2.2 Software Stack

**Backend:**
```
Python 3.9+
├── FastAPI 0.100+
├── PyMuPDF (fitz) 1.23+
├── python-multipart (file uploads)
├── pydantic (data validation)
├── httpx (async HTTP client)
└── optional: pytesseract + tesseract-ocr
```

**Frontend:**
```
Browser runtime only
├── Native HTML
├── Native CSS
└── Native JavaScript (no npm packages or Node.js runtime)
```

**Deployment:**
```
Docker & Docker Compose
├── Official Python 3.11 image
└── Static frontend files served by the web server
```

### 2.3 AI Service Integration

**Primary Vision/Classification API:** Google Gemini 1.5 Flash
- Cost: $0.00002–$0.0001 per request
- Context Window: 1M tokens
- Capabilities: Vision, text, structured output (JSON Schema)
- Rate Limit: 100K requests/month free tier
- Optional for the first local analysis pass; configured server-side with `GEMINI_API_KEY`, `GEMINI_ENDPOINT`, and `GEMINI_TIMEOUT`. The default endpoint uses the currently supported Gemini Flash model.
- The key is sent in the `x-goog-api-key` header and is never exposed to the native frontend

**Fallback Classification API:** Anthropic Claude 3 Haiku
- Cost: $0.25/1M input tokens, $1.25/1M output tokens
- Capabilities: Vision, text, tool use
- Max Input: 200K tokens

**Local Preprocessing:**
- PyMuPDF text extraction (no API cost)
- Tesseract OCR (one-time CPU cost, no API)
- Local header detection via regex/heuristics

### 2.4 Data Flow (n8n Ingestion & Local Classification)

```
[n8n Ingestion Workflow] (external source is configured in n8n)
  ↓
[Handoff] → Write completed PDF to /data/source
    ↓
[Store Locally] → Cache to /volume1/Temp/processing/{doc_id}/
    ↓
[Archive Original] → Original remains in /data/source
    ↓
[Extract Text] → PyMuPDF (vector PDF) or Tesseract (scanned)
    ↓
[Local Feature Detection] → Blank page detection, header reading
    ↓
[API Fallback] → Send flagged boundary pages to Gemini API
    ↓
[Split Suggestion] → Return JSON with split points & document type
    ↓
[User Review] → Web UI renders thumbnails, allows manual adjustment
    ↓
[Finalize] → Backend slices PDF, applies rotation, generates output names
    ↓
[Classify Destinee] → Select one configured destinee
  ↓
[Export] → Write to /data/destination/{destinee}/
    ↓
[Cleanup] → Remove temp files from /volume1/Temp/ after successful export
```

**Architecture Boundary:** n8n owns external source fetching. The classifier web UI owns destinee configuration; no source credentials or external fetch implementation is required in the classifier.

---

## 3. API Specifications

### 3.1 Backend Endpoints

**File Management:**
- `POST /api/upload` - Upload PDF document
- `GET /api/document/{doc_id}` - Retrieve document metadata
- `GET /api/documents/{filename}` - Inspect one completed PDF from the n8n input directory
- `GET /api/documents/{filename}/file` - Serve one source PDF for browser review
- `POST /api/documents/{filename}/prepare` - Copy and inspect a PDF in processing storage
- Prepared pages include `ocr_used`; pages without extractable text are rendered and processed with local Tesseract OCR.
- `POST /api/documents/{filename}/analyze` - Extract content, detect language/topic, and suggest a filename in the document language
- Analysis results include `language` and explainable `signals` for local fallback decisions.
- `POST /api/documents/{filename}/finalize` - Copy a prepared PDF to a configured destinee with an optional output filename
- `GET /api/documents/history` - Return persisted document lifecycle history

**Document lifecycle:** `received` when n8n hands off a PDF, `in_review` after preparation, `classified` after finalization, and `failed` when preparation cannot be completed. Lifecycle state is persisted with the mounted application configuration. Finalization writes the classified copy, optionally using a reviewed `.pdf` filename, moves the original with its source name out of `/data/source` into `/data/archive/` so it no longer appears in the n8n inbox, and removes the temporary processing workspace.

**Analysis provider visibility:** The review UI displays whether Gemini is configured and which provider actually returned the current analysis. The API exposes only a boolean configuration flag and the provider name; credentials are never returned. Analysis never selects a destinee. The user must explicitly choose any configured destinee during review, allowing correction of a mistaken route.

**Local OCR:** OCR is activated per page only when native PDF text is empty. The default languages are English and German (`OCR_LANGUAGES=eng+deu`), and the review UI marks OCR-processed pages.

**Gemini availability:** A `429` quota/rate-limit response or another Gemini request failure is recorded in the mounted analysis-status file. The UI then warns that Gemini is temporarily unavailable and local fallback is active. A later valid Gemini response marks the provider available again and clears the warning.
- `GET /api/document/{doc_id}/pages` - Fetch paginated page thumbnails
- `DELETE /api/document/{doc_id}` - Remove document from processing queue

**Processing:**
- `POST /api/analyze` - Trigger AI analysis on document
- `POST /api/split` - Execute document split with user adjustments
- `POST /api/rotate` - Apply rotation to specific pages
- `GET /api/status/{task_id}` - Poll async task status

**Export:**
- `POST /api/export` - Finalize and export to destination
- `GET /api/export-status/{export_id}` - Check export progress

**Ingestion and Classification Configuration:**
- `GET /api/ingestion/status` - Report n8n handoff and input-directory status
- `GET /api/analysis/status` - Report whether Gemini is configured, without exposing its key
- `GET /api/version` - Return the version embedded in the running Docker image
- `GET /api/classification/config` - Get configured destinees and fixed paths
- `POST /api/classification/config` - Add, rename, remove, or reorder destinees
- `POST /api/classification/scan` - Scan the n8n input directory for completed PDFs

### 3.2 AI API Integration

**Gemini Request (Vision/Classification):**
```
POST https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent

Request Body:
{
  "contents": [{
    "parts": [
      {
        "text": "Analyze this document page. Identify: 1) document boundary markers, 2) document type (Invoice/Receipt/Contract/...), 3) suggested split points"
      },
      {
        "inline_data": {
          "mime_type": "image/jpeg",
          "data": "<base64_encoded_page_image>"
        }
      }
    ]
  }],
  "generationConfig": {
    "response_mime_type": "application/json",
    "response_schema": {
      "type": "object",
      "properties": {
        "document_type": {"type": "string"},
        "split_point": {"type": "boolean"},
        "confidence": {"type": "number"}
      }
    }
  }
}
```

**Expected Response:**
```json
{
  "document_type": "Invoice",
  "split_point": true,
  "confidence": 0.95,
  "vendor": "Acme Corp",
  "suggested_filename": "2026-08-17_Invoice_AcmeCorp.pdf"
}
```

---

## 3.3 Storage and Ingestion Architecture

External source integrations are deliberately outside the classifier. n8n fetches documents from email, Google Drive, or any other configured source and writes completed PDFs to the container's mounted input directory. The classifier uses local file I/O for the initial source and destination paths. This keeps source credentials and workflow orchestration in n8n while allowing the web UI to configure business-level destinees.

**Runtime directories:**
- Input: `/data/source`
- Classified output root: `/data/destination/`
- Destinee output: `/data/destination/{destinee}/`
- Processing temporary files: `/data/temp/processing/{doc_id}/`
- Processed source archive: `/data/archive/`

The existing `StorageBackend` abstraction remains available for a future external output provider, but it is not part of the initial n8n/local implementation path.

### 3.3.1 Backend Interface (Abstract Base Class)

```python
from abc import ABC, abstractmethod
from typing import BinaryIO, List, Dict

class StorageBackend(ABC):
    """Abstract base for storage source/destination backends."""
    
    @abstractmethod
    async def authenticate(self, credentials: Dict[str, str]) -> bool:
        """Authenticate with backend. Returns True if successful."""
        pass
    
    @abstractmethod
    async def list_folders(self) -> List[Dict[str, str]]:
        """List available folders. Returns [{"id": "...", "name": "..."}]"""
        pass
    
    @abstractmethod
    async def upload_file(self, folder_id: str, filename: str, file: BinaryIO) -> str:
        """Upload file to folder. Returns file_id."""
        pass
    
    @abstractmethod
    async def download_file(self, file_id: str) -> BinaryIO:
        """Download file by ID. Returns file stream."""
        pass
    
    @abstractmethod
    async def list_files(self, folder_id: str, pattern: str = "*.pdf") -> List[Dict]:
        """List files in folder. Returns [{"id": "...", "name": "...", "modified": "..."}]"""
        pass
    
    @abstractmethod
    async def delete_file(self, file_id: str) -> bool:
        """Delete file. Returns True if successful."""
        pass
    
    @abstractmethod
    async def get_storage_info(self) -> Dict:
        """Return storage info: {"used_bytes": ..., "total_bytes": ..., "account": "..."}"""
        pass
```

### 3.3.2 Implemented Backends

**Google Drive Backend:**
- Uses Google Drive API v3 via service account or OAuth2
- Supports folder hierarchies, shared drives
- Credentials stored securely in config
- Cost: Free (limited), or included in Google Workspace

**Local NAS Backend:**
- Direct file I/O to `/volume1/` paths
- No external authentication
- Fastest performance (local disk I/O)
- Useful as fallback or temporary staging

**SharePoint Backend (Future):**
- Microsoft Graph API integration
- Supports document libraries
- Azure AD authentication

**Dropbox Backend (Future):**
- Dropbox API v2
- OAuth2 authentication

### 3.3.3 Backend Configuration Management

**Classification Configuration (persisted in database):**

```json
{
  "storage_config": {
    "ingestion": {
      "provider": "n8n",
      "input_path": "/data/source"
    },
    "classification": {
      "output_root": "/data/destination/",
      "destinees": []
    }
  }
}
```

### 3.3.4 Destinee Configuration UI

Users configure first-level classification destinations via the web interface panel:

```
┌─ Classification Configuration ─────────────────────────┐
│                                                        │
│ INGESTION: n8n                                          │
│  ├─ Input: /data/source                                │
│  └─ Status: Waiting for n8n handoff                    │
│                                                        │
│ CLASSIFIED OUTPUT: /data/destination/                  │
│  ├─ Destinees: configured by the administrator         │
│  └─ [Add destinee] [Save configuration]                │
│                                                        │
└────────────────────────────────────────────────────────┘
```

---

## 4. Database & Storage Schema

### 4.1 File System Layout (n8n Input & Local Classified Output)

The NAS storage is used for:
- **Raw input** (completed PDFs handed off by n8n)
- **Classified output** (one directory per configured destinee)
- **Temporary processing** (thumbnails, renderings, and analysis state)

NAS volumes (if using local NAS as archive backend):

```
/volume1/
├── Archive/
│   ├── Originals_RAW/
│   │   ├── {timestamp}_{uuid}_original.pdf (n8n handoff)
│   │   └── metadata.json
│   └── Classified/
│       ├── {configured_destinee}/
│       └── {configured_destinee}/
├── Temp/
│   ├── processing/
│   │   └── {doc_id}/
│   │       ├── original.pdf
│   │       ├── pages/
│   │       │   ├── page_001.jpg
│   │       │   ├── page_002.jpg
│   │       │   └── ...
│   │       └── analysis.json
│   └── exports/
│       └── {export_id}/
│           └── split_pdfs/
└── Backups/
    └── (system backups, not user documents)
```

**Note:** n8n is responsible for external source access. The initial classifier implementation reads from and writes to the mounted container paths; each configured destinee maps to a directory below `/data/destination/`. Host-specific NAS paths are supplied by `docker-compose.yml`.

### 4.2 Metadata Structure

**Document Metadata (JSON):**
```json
{
  "doc_id": "550e8400-e29b-41d4-a716-446655440000",
  "original_filename": "batch_scan_20260817.pdf",
  "upload_timestamp": "2026-08-17T14:32:00Z",
  "total_pages": 50,
  "file_size_bytes": 25000000,
  "status": "analyzed",
  "analysis_result": {
    "suggested_splits": [
      {"page": 1, "confidence": 0.98, "reason": "document_start"},
      {"page": 15, "confidence": 0.92, "reason": "header_change"},
      {"page": 32, "confidence": 0.87, "reason": "blank_page_follow"}
    ],
    "detected_categories": [
      {"pages": "1-14", "type": "Invoice", "vendor": "Acme Corp"},
      {"pages": "15-31", "type": "Receipt", "vendor": "Best Store"}
    ]
  },
  "user_adjustments": {
    "splits": [1, 15, 32],
    "rotations": {"3": 90, "45": 180},
    "metadata_overrides": {
      "category_0": {"filename": "2026-08-17_Invoice_AcmeCorp_Custom.pdf"}
    }
  },
  "output_files": [
    {
      "filename": "2026-08-17_Invoice_AcmeCorp.pdf",
      "pages": "1-14",
      "destination_backend": "google_drive",
      "destination_folder_id": "9z8y7x6w5v4u3t2s1r0q",
      "destination_folder_name": "Processed Documents",
      "file_id": "external_drive_file_123",
      "export_status": "completed",
      "export_timestamp": "2026-08-17T14:35:00Z"
    }
  ],
  "source_backend": {
    "type": "google_drive",
    "folder_id": "1a2b3c4d5e6f7g8h9i0j",
    "file_id": "original_drive_file_456"
  }
}
```

---

## 5. Security & Access Control

### 5.1 Authentication

- **NAS Level:** Synology DSM user credentials (standard)
- **Application:** Optional JWT tokens for multi-user support
- **API Keys:** Encrypted storage in environment variables (Docker secrets)

### 5.2 Data Protection

- **In Transit:** TLS 1.3 for external API calls
- **At Rest:** NAS native encryption (Synology Hybrid Raid)
- **API Credentials:** Never logged; rotate keys quarterly
- **User Data:** Segregated per user folder if multi-user enabled

### 5.3 Access Boundaries

- Frontend accessible only within NAS LAN (no direct internet exposure)
- Backend API accessed via authenticated proxy (reverse proxy in container)
- Cloud API requests signed with service-specific credentials

---

## 6. Performance & Scalability

### 6.1 Expected Performance

| Operation | Dataset | Expected Duration | Cost |
|-----------|---------|-------------------|------|
| PDF Upload & Parsing | 50 pages @ 2MB each | 2-5 seconds | $0 |
| Local Text Extraction | 50 pages | 3-10 seconds | $0 |
| Gemini Vision Analysis | 50 pages (batched) | 30-60 seconds | ~$0.001-0.005 |
| User Review & Adjustment | Interactive | Variable (user time) | $0 |
| Split & Finalize | 50 pages, 3 splits | 5-15 seconds | $0 |
| **Total per batch** | **50 pages** | **~2 minutes** | **~$0.005** |

### 6.2 Scalability Constraints

- **NAS CPU:** Can process 2-3 concurrent uploads on R1600 without OCR
- **Memory Limits:** 4GB stock; upgrades enable OCR batching
- **Concurrent Users:** 2-3 simultaneous sessions (upgrade to 8GB for more)
- **API Rate Limits:** Gemini free tier: 100K req/month ≈ 2000 batches/month

---

## 7. Error Handling & Recovery

### 7.1 Failure Scenarios

| Scenario | Detection | Recovery |
|----------|-----------|----------|
| PDF corruption | PyMuPDF parse error | Return 400; offer re-upload |
| API timeout | HTTP timeout after 30s | Retry with exponential backoff (3x) |
| OCR failure (scanned PDF) | Tesseract return code | Fall back to Gemini vision API |
| Split boundary conflict | Validation error | Present UI alert; request user clarification |
| Export destination unreachable | Network error | Queue for retry; notify user |

### 7.2 Logging & Monitoring

- All API calls logged with timestamp, request size, response time
- Cloud API failures logged but not sensitive credential data
- Export status persisted in metadata.json for audit trail

---

## 8. Compliance & Data Retention

### 8.1 Data Retention Policy

- **Raw Archives:** Indefinite (immutable, timestamped, archived to cold storage after 90 days)
- **Processed Documents:** Retained per user preference (configurable)
- **Temporary Processing Files:** Auto-deleted after 30 days
- **API Logs:** Retained for 90 days (comply with cloud provider terms)

### 8.2 Regulatory Compliance

- GDPR: Right to delete user data (implement data purge endpoint)
- CCPA: Data export capability for user download
- Document Sensitivity: Optional encryption for sensitive doc types

---

## 9. Future Extensions

### 9.1 Planned Features

1. **OCR Fallback:** Tesseract for image-only pages with German and English language data
2. **Image Preprocessing:** Deskew, denoise, contrast, orientation, and grayscale preparation
3. **Language-Aware Local Analysis:** Page-level language detection and matching rules
4. **Richer Local Classification:** Categories, entities, signals, and confidence explanations
5. **Document Identity:** SHA-256 duplicate detection independent of filename
6. **Page Rotation:** Per-page 90, 180, and 270 degree rotation in the review workflow
7. **Document Splitting:** User-controlled boundaries and multiple output PDFs
8. **Multi-User Workflow:** Role-based access (Reviewer, Approver, Admin)
9. **Webhook Export:** Trigger external systems via HTTP callbacks
10. **Advanced Batch Processing:** Schedule recurring document ingestion from n8n
11. **BI Dashboard:** Monthly cost reports and processing metrics
12. **Additional Storage Backends:** Dropbox, Azure Blob, and S3 support

### 9.2 Extensibility Points

- Pluggable storage backends (implement `StorageBackend` ABC for new providers)
- Custom AI provider integration (LLaMA local, text-only APIs)
- User-defined split point heuristics (regex rules, ML classifiers)
- Custom credential providers (HashiCorp Vault, AWS Secrets Manager)

---

## 10. Deployment & Rollback

### 10.1 Versioning Strategy

- **Semantic Versioning:** Major.Minor.Patch (e.g., 1.2.3)
- **Docker Tags:** `latest`, `stable`, `v1.2.3` on Docker Hub
- **Configuration:** Externalized in `.env` for version independence

### 10.2 Zero-Downtime Updates

- Blue-green deployment using Docker Compose network aliases
- Database migrations run in init container before service start
- API versioning supports old clients during transition period

---

## Appendix A: Glossary

- **Split Point:** Logical boundary between documents in a batch scan
- **OCR:** Optical Character Recognition (text extraction from images)
- **PyMuPDF:** Python library for PDF manipulation (fitz module)
- **AIaaS:** AI as a Service (cloud-based vision/text APIs)
- **NAS:** Network Attached Storage (Synology device)
- **Batch Scan:** Multi-page PDF from scanner containing mixed documents

---

## Appendix B: References

- PyMuPDF Documentation: https://pymupdf.readthedocs.io/
- FastAPI Guide: https://fastapi.tiangolo.com/
- Google Gemini API: https://ai.google.dev/
- Anthropic Claude: https://www.anthropic.com/
- Docker Compose: https://docs.docker.com/compose/
