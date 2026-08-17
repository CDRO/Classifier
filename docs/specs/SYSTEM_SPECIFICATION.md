# Document Processing Pipeline - System Specification

**Version:** 1.0  
**Date:** 2026-08-17  
**Status:** Active Specification  

---

## Executive Summary

A budget-friendly, local-first document processing pipeline with AI-assisted UI hosted on Synology NAS. The system separates lightweight local execution (UI, PDF processing, splitting) from cheap cloud AI micro-services (vision/text classification), delivering a responsive user experience while maintaining strict cost controls.

---

## 1. System Architecture

### 1.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ Document Source                                                 │
│ (Scanner / File Upload)                                        │
└────────────────────┬────────────────────────────────────────────┘
                     │ (Multi-page PDF)
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ Synology DS923+ (Docker Container Environment)                 │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Frontend Layer                                           │  │
│  │ • React / Next.js Web Application                       │  │
│  │ • Client-side PDF rendering & manipulation              │  │
│  │ • Interactive split point visualization                 │  │
│  │ • Real-time thumbnail generation                        │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Backend Layer                                            │  │
│  │ • FastAPI (Python 3.9+)                                 │  │
│  │ • PyMuPDF for PDF manipulation                           │  │
│  │ • Tesseract OCR (optional, local)                        │  │
│  │ • Local embeddings computation                           │  │
│  │ • API orchestration & caching                            │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
└────────────┬──────────────────────────────────────────────┬─────┘
             │                                              │
             ▼                                              ▼
    ┌────────────────────┐                  ┌──────────────────────────┐
    │ Cloud AI Services  │                  │ User Web Interface       │
    │ • Gemini 1.5 Flash │                  │ • Split point toggle     │
    │ • Claude 3 Haiku   │                  │ • Page rotation controls │
    │ (Vision + Text)    │                  │ • Metadata form fields   │
    └────────────────────┘                  │ • Batch group review     │
             │                              │ • One-click finalize     │
             ▼                              └──────────────────────────┘
    ┌────────────────────┐
    │ Classification &   │
    │ Split Suggestions  │
    └────────────────────┘
             │
             ▼
    ┌────────────────────────────────────┐
    │ Final Output Routing               │
    ├────────────────────────────────────┤
    │ • Local NAS Storage                │
    │ • SharePoint / Microsoft 365       │
    │ • Google Drive (optional)          │
    │ • Archive raw originals            │
    └────────────────────────────────────┘
```

### 1.2 Component Dependencies

| Component | Purpose | Technology | Resource Requirement |
|-----------|---------|-----------|----------------------|
| Frontend | User Interface | React/Next.js + TypeScript | ~200MB RAM |
| Backend | API & Business Logic | FastAPI + Python 3.9+ | ~400MB RAM |
| PDF Engine | Document Manipulation | PyMuPDF | Native binary (~50MB) |
| OCR Engine | Text Extraction (Optional) | Tesseract OCR | ~300MB (if installed) |
| AI/Vision API | Classification & Splitting | Cloud (Gemini/Claude) | API credential |
| Storage | Document Archive | NAS /volume1/ paths | Persistent disk |

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
Node.js 18+
├── React 18+
├── Next.js 14+
├── TypeScript 5+
├── pdf-lib (client-side PDF manipulation)
├── axios (API client)
└── tailwindcss (styling)
```

**Deployment:**
```
Docker & Docker Compose
├── Official Python 3.11 image
├── Node.js 18 build stage
└── Multi-stage build for size optimization
```

### 2.3 AI Service Integration

**Primary Vision/Classification API:** Google Gemini 1.5 Flash
- Cost: $0.00002–$0.0001 per request
- Context Window: 1M tokens
- Capabilities: Vision, text, structured output (JSON Schema)
- Rate Limit: 100K requests/month free tier

**Fallback Classification API:** Anthropic Claude 3 Haiku
- Cost: $0.25/1M input tokens, $1.25/1M output tokens
- Capabilities: Vision, text, tool use
- Max Input: 200K tokens

**Local Preprocessing:**
- PyMuPDF text extraction (no API cost)
- Tesseract OCR (one-time CPU cost, no API)
- Local header detection via regex/heuristics

### 2.4 Data Flow

```
User Upload
    ↓
[Receive PDF] → Store in /volume1/Archive/Originals_RAW/
    ↓
[Extract Text] → PyMuPDF (vector PDF) or Tesseract (scanned)
    ↓
[Local Feature Detection] → Blank page detection, header reading
    ↓
[API Fallback] → Send flagged boundary pages to Gemini
    ↓
[Split Suggestion] → Return JSON with split points & document type
    ↓
[User Review] → Web UI renders thumbnails, allows manual adjustment
    ↓
[Finalize] → Backend slices PDF, applies rotation, generates output names
    ↓
[Export] → Save to /volume1/Documents/ (or SharePoint/Drive)
```

---

## 3. API Specifications

### 3.1 Backend Endpoints

**File Management:**
- `POST /api/upload` - Upload PDF document
- `GET /api/document/{doc_id}` - Retrieve document metadata
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

### 3.2 AI API Integration

**Gemini Request (Vision/Classification):**
```
POST https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent

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

## 4. Database & Storage Schema

### 4.1 File System Layout

```
/volume1/
├── Archive/
│   └── Originals_RAW/
│       ├── {timestamp}_{uuid}_original.pdf (immutable)
│       └── metadata.json
├── Documents/
│   ├── Invoices/
│   │   ├── 2026/
│   │   │   └── 2026-08-17_Invoice_VendorName.pdf
│   │   └── 2025/
│   ├── Receipts/
│   ├── Contracts/
│   └── [Other Categories]/
└── Temp/
    ├── processing/
    │   └── {doc_id}/
    │       ├── original.pdf
    │       ├── pages/
    │       │   ├── page_001.jpg
    │       │   ├── page_002.jpg
    │       │   └── ...
    │       └── analysis.json
    └── exports/
```

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
      "destination": "local_nas"
    }
  ]
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

1. **Multi-User Workflow:** Role-based access (Reviewer, Approver, Admin)
2. **OCR Post-Processing:** Layout reconstruction for rotated/split pages
3. **Webhook Export:** Trigger external systems via HTTP callbacks
4. **Advanced Batch Processing:** Schedule recurring document ingestion
5. **BI Dashboard:** Monthly cost reports, processing metrics

### 9.2 Extensibility Points

- Pluggable storage backends (S3, Azure Blob, Dropbox)
- Custom AI provider integration (LLaMA local, text-only APIs)
- User-defined split point heuristics (regex rules, ML classifiers)

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
