# Deployment & Management User Manual

**Version:** 1.0  
**Date:** 2026-08-17  
**Audience:** System Administrators, DevOps Engineers, End Users

---

## Table of Contents

1. [Pre-Deployment Checklist](#1-pre-deployment-checklist)
2. [Hardware Setup](#2-hardware-setup)
3. [Installation Guide](#3-installation-guide)
4. [Configuration & Environment](#4-configuration--environment)
5. [Initial Startup & Verification](#5-initial-startup--verification)
6. [User Access & Authentication](#6-user-access--authentication)
7. [Daily Operations](#7-daily-operations)
8. [Monitoring & Alerting](#8-monitoring--alerting)
9. [Backup & Recovery](#9-backup--recovery)
10. [Troubleshooting Guide](#10-troubleshooting-guide)
11. [Maintenance & Updates](#11-maintenance--updates)
12. [Security Management](#12-security-management)

---

## 1. Pre-Deployment Checklist

Before deploying the Document Processing Pipeline to production, verify the following:

### 1.1 Infrastructure Requirements

- [ ] **Synology NAS Model:** DS923+ (or compatible)
  - [ ] Running DSM 7.1+ (current version)
  - [ ] Internet connectivity (for cloud AI APIs)
  - [ ] 50GB free disk space minimum (for application + temp files)
  - [ ] RAM upgrade (8GB-16GB recommended)

- [ ] **Network Requirements:**
  - [ ] NAS connected to LAN via Ethernet
  - [ ] Outbound HTTPS access to cloud APIs (Gemini, Claude, etc.)
  - [ ] Firewall rules allow NAS-to-internet (port 443 outbound)
  - [ ] Optional: VPN configured for remote access

### 1.2 Cloud API Setup

- [ ] **Google Gemini API:**
  - [ ] Account created at [Google AI Studio](https://aistudio.google.com)
  - [ ] API key generated and securely stored
  - [ ] Free tier quota verified (100K requests/month)
  - [ ] Billing account optional (if exceeding quota expected)

- [ ] **Anthropic Claude API (optional fallback):**
  - [ ] Account created at [Anthropic Console](https://console.anthropic.com)
  - [ ] API key generated
  - [ ] Payment method added (pay-per-use model)

### 1.3 Storage Preparation

- [ ] **Synology Volume Setup:**
  ```
  # Via DSM → Storage Manager → Create Volume (if new storage)
  Volume 1 (system): /volume1/
  ├── Archive/
  │   ├── Originals_RAW/          # n8n input handoff and raw originals
  │   └── Classified/             # First classification by destinee
  ├── Temp/                       # Processing cache
  └── Backups/                    # Nightly backups
  ```
  - [ ] Archive volume has 1TB+ capacity
  - [ ] Archive volume readable/writable by Docker container
  - [ ] Temp volume has 50GB free (for concurrent processing)

### 1.4 Administrator Access

- [ ] Administrator has SSH access to NAS
- [ ] Synology Container Manager installed (via Package Center)
- [ ] Docker images can be pulled (Docker Hub access)
- [ ] NAS web interface accessible via https://nas.local:5000 or IP

---

## 2. Hardware Setup

### 2.1 RAM Upgrade (Recommended)

The DS923+ ships with 4GB RAM; upgrade to 8GB-16GB for better concurrency:

```
1. Power off NAS: Menu → Power → Shut Down
2. Remove power cable (wait 30 seconds)
3. Open case: Remove 4 screws on rear panel
4. Locate SODIMM slot (inside, left side)
5. Push retention clips outward to eject existing module
6. Insert new DDR4 SODIMM (gently, single notch aligns)
7. Press down until retention clips click
8. Reassemble case
9. Power on and verify: DSM → Control Panel → Info → Memory
```

**Compatible Modules:**
- Kingston DDR4 3200MHz SODIMM, 8GB (KCP432SD8/8)
- Crucial DDR4 3200MHz SODIMM, 16GB (CT16G4SFD832A)

### 2.2 Storage Expansion (Optional)

If 50GB is insufficient, expand storage via eSATA:

```
1. Connect eSATA expansion unit to NAS rear port
2. Power on expansion unit
3. In DSM, go to Control Panel → Storage Manager
4. Create new volume on expansion unit
5. Format as ext4 (default)
6. Mount point: /volume2/ (auto-assigned)
```

### 2.3 Network Configuration

```
DSM Web Interface → Control Panel → Network:

1. IPv4 Settings
   ├── IP Address: 192.168.1.100 (static)
   ├── Netmask: 255.255.255.0
   ├── Gateway: 192.168.1.1
   └── DNS: 8.8.8.8, 8.8.4.4

2. Internet Access
   └── Verify outbound to api.gemini.google.com (443)
       and api.anthropic.com (443)
```

---

## 3. Installation Guide

### 3.1 Prerequisites

- SSH client (Windows: PuTTY/WSL2, Mac/Linux: built-in)
- Docker image file (or Docker Hub account)
- Environment configuration file (.env)

### 3.2 Step 1: Install Container Manager

Via DSM Package Center:

```
1. Open Package Center
2. Search: "Container Manager"
3. Install (requires DSM 7.1+)
4. Launch and accept terms
```

### 3.3 Step 2: Prepare Application Directory

SSH into NAS:

```bash
# Connect via SSH
ssh admin@192.168.1.100
# Enter password when prompted

# Create application structure
sudo mkdir -p /volume1/docker/classifier
cd /volume1/docker/classifier

# Create subdirectories
sudo mkdir -p {config,logs,data,backups}

# Set permissions (for Docker daemon)
sudo chmod 755 /volume1/docker/classifier
sudo chmod 755 /volume1/docker/classifier/{config,logs,data,backups}
```

### 3.4 Step 3: Configure Environment

Download `.env` template and customize:

```bash
# Copy template
sudo vi /volume1/docker/classifier/config/.env
```

**`.env` Configuration:**

```ini
# Application Settings
DEBUG=false
ENVIRONMENT=production
LOG_LEVEL=INFO

# API Keys (KEEP SECURE - use Docker Secrets in production)
GEMINI_API_KEY=your-gemini-api-key-here
CLAUDE_API_KEY=your-claude-api-key-here (optional)

# Optional Gemini content analysis
# Leave GEMINI_API_KEY empty to use local keyword analysis only.
GEMINI_ENDPOINT=https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent
GEMINI_TIMEOUT=20

# Local container paths (host mappings belong in docker-compose.yml)
TEMP_PATH=/data/temp
RAW_INPUT_PATH=/data/source
CLASSIFIED_OUTPUT_PATH=/data/destination

# FastAPI Configuration
API_HOST=0.0.0.0
API_PORT=8000
API_WORKERS=4

# Database (Storage configuration & metadata)
# DATABASE_URL=postgresql://user:password@localhost:5432/classifier
# (Optional: if using PostgreSQL; otherwise SQLite is default)

# Ingestion
# External source fetching is configured in n8n.
# The classifier watches RAW_INPUT_PATH; source credentials are not stored here.
```

**Important:** The application uses `/data/source` and `/data/destination` by default. Host-specific folders are mapped later in `docker-compose.yml`; destinee names are configured in the web interface.

#### 3.4.1 Configure Gemini Content Analysis

Gemini is optional. Without `GEMINI_API_KEY`, the application uses the local classifier and does not make external analysis requests.

1. Open [Google AI Studio](https://aistudio.google.com/app/apikey).
2. Sign in to the Google account that will own the API key.
3. Select an existing Google Cloud project or create a dedicated project.
4. Click **Create API key** and copy the key once. Do not commit it to Git or put it in frontend files.
5. Store the key in the server-side `docker.env` or, preferably, Docker Secrets:

  ```ini
  GEMINI_API_KEY=replace-with-your-key
  GEMINI_ENDPOINT=https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent
  GEMINI_TIMEOUT=20
  ```

6. Ensure the backend container has outbound HTTPS access to `generativelanguage.googleapis.com`.
7. Restart the classifier container so the server reads the new environment values:

  ```bash
  sudo docker-compose restart classifier-backend
  ```

8. Place a completed PDF in `/data/source`, select it in the web interface, and inspect the analysis result.
9. Confirm the result contains `analysis_source: "gemini"` in the API response or that the review summary reflects the Gemini result.

**Interface verification:** Open the application and select a PDF from the document inbox. The review panel displays an analysis-provider badge:
- `Analysis provider: Gemini configured` means the running container received a Gemini key.
- `Analysis provider: Gemini` means Gemini returned the analysis for the selected document.
- `Analysis provider: Local fallback` means local analysis produced the result, usually because Gemini is not configured or the request failed.

The server-only status endpoint can also be checked without revealing the key:

```bash
curl http://localhost:3000/api/analysis/status
```

The expected configured response includes `"gemini_configured": true`. This confirms configuration, while `analysis_source` in the document analysis response confirms actual use.

If configuration reports `true` but analysis falls back to local, check the model endpoint first. A model can appear in the model list but still be unavailable to a new API key. The endpoint must refer to a model that both exists and supports `generateContent`; for the current configured key, `gemini-3.6-flash:generateContent` returned `200 OK` and produced `analysis_source: "gemini"`.

**Endpoint override:** Keep the default endpoint unless using a compatible proxy or model deployment. `GEMINI_ENDPOINT` must be the complete `generateContent` URL. The API key is sent in the `x-goog-api-key` header and is never sent to the browser.

**Failure behavior:** If Gemini times out, returns an error, or returns invalid JSON, the classifier records no secret data and falls back to local analysis. Check backend logs for the failure and confirm the local result has `analysis_source: "local"`.

**Key rotation:** Create a replacement key in Google AI Studio, update the server-side secret, restart the backend, verify one document, and revoke the old key.

**Save and exit:** Press `Ctrl+O`, `Enter`, `Ctrl+X`

### 3.5 Step 4: Deploy Docker Compose

Create `docker-compose.yml` in `/volume1/docker/classifier/`:

```bash
sudo vi /volume1/docker/classifier/docker-compose.yml
```

**docker-compose.yml:**

```yaml
version: '3.8'

services:
  classifier-backend:
    image: classifier:latest  # Replace with your image tag
    container_name: classifier-backend
    restart: always
    
    ports:
      - "8000:8000"
    
    environment:
      - DEBUG=${DEBUG:-false}
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
      - GEMINI_API_KEY=${GEMINI_API_KEY}
      - CLAUDE_API_KEY=${CLAUDE_API_KEY}
      - ARCHIVE_PATH=${ARCHIVE_PATH}
      - DOCUMENTS_PATH=${DOCUMENTS_PATH}
      - TEMP_PATH=${TEMP_PATH}
    
    volumes:
      - /volume1/Archive:/volume1/Archive
      - /volume1/Archive:/volume1/Archive
      - /volume1/Temp:/volume1/Temp
      - /volume1/docker/classifier/logs:/app/logs
      - /volume1/docker/classifier/config:/config
    
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
    
    networks:
      - classifier-net

  classifier-frontend:
    image: classifier-frontend:latest
    container_name: classifier-frontend
    restart: always
    
    ports:
      - "3000:3000"
    
    environment:
      - API_URL=http://localhost:8000
      - NODE_ENV=production
    
    depends_on:
      - classifier-backend
    
    networks:
      - classifier-net
    
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:3000"]
      interval: 30s
      timeout: 10s
      retries: 3

networks:
  classifier-net:
    driver: bridge
```

### 3.6 Step 5: Start Services

```bash
cd /volume1/docker/classifier

# Start services (pulls images if needed, may take 2-5 minutes)
sudo docker-compose up -d

# Verify services are running
sudo docker-compose ps

# Expected output:
# NAME                      STATUS
# classifier-backend        Up 2 minutes (healthy)
# classifier-frontend       Up 1 minute (healthy)
```

### 3.7 Step 6: Verify Installation

```bash
# Check backend logs
sudo docker-compose logs classifier-backend --tail=50

# Test API endpoint
curl -s http://localhost:8000/health | jq .

# Expected response:
# {
#   "status": "healthy",
#   "checks": {
#     "pdf_engine": "ok",
#     "ai_api": "ok",
#     "storage": "ok"
#   }
# }

# Test frontend
curl -s http://localhost:3000 | head -20
```

---

## 4. Configuration & Environment

### 4.1 Adjusting Performance Settings

Edit `.env` and restart:

```bash
# Increase API workers for high concurrency
API_WORKERS=8

# Adjust Tesseract OCR timeout (seconds)
OCR_TIMEOUT=60

# Limit concurrent PDF processing
MAX_CONCURRENT_JOBS=3

# Restart to apply
sudo docker-compose restart classifier-backend
```

### 4.2 Configuring Ingestion and Destinees

The external document source is configured in n8n. The classifier web interface configures the first-level destinees and writes classified files beneath `/data/destination/`. Map this path to NAS storage in `docker-compose.yml`.

**Access Classification Configuration:**
1. Navigate to http://192.168.1.100:3000
2. Click "Settings" (gear icon)
3. Select "Classification Configuration"
4. Add, rename, remove, and order destinees

#### 4.2.1 n8n Ingestion Handoff

Configure the n8n workflow to:

1. Fetch PDFs from the desired external source.
2. Write each PDF to `/data/source` through the shared Docker volume.
3. Preserve the original filename and avoid writing partial files. Use a temporary filename and rename after the write completes.
4. Let the classifier detect completed PDFs in that directory.

The classifier does not fetch email or Google Drive files itself. n8n owns those credentials, retries, and source-specific logic.

#### 4.2.2 Destinee Configuration

1. Open **Settings → Classification Configuration**.
2. Confirm the fixed paths shown for input and classified output.
3. Add the initial destinees: `Destinee A`, `Destinee B`, and `Destinee C`.
4. Save the configuration.
5. The application creates or uses `/data/destination/<destinee>/` for each configured value.
6. New destinees can be added in the UI without changing n8n or container configuration.

#### 4.2.3 Google Drive Setup (n8n Responsibility)

To use Google Drive as an ingestion source, configure it in n8n rather than in the classifier:

**Step 1: Create Google Cloud Service Account**

```bash
# Visit: https://console.cloud.google.com/iam-admin/serviceaccounts
# 1. Create new project (e.g., "Document Classifier")
# 2. Enable Google Drive API:
#    APIs & Services → Library → search "Google Drive API" → Enable
# 3. Create Service Account:
#    Create Service Account → Name: "classifier-service"
# 4. Create Key (JSON format):
#    Keys → Add Key → JSON → Download JSON file
# 5. Share Google Drive folder with service account email:
#    In Google Drive, right-click folder → Share
#    → Paste service account email (from JSON key file)
#    → Grant "Editor" permission
```

**Step 2: Configure n8n Credentials**

```bash
# Store the service account credential in n8n's credential store.
# Do not add Google credentials to the classifier .env or web UI.

# Or via SSH:
ssh admin@192.168.1.100
sudo nano /volume1/docker/classifier/config/gd-service-account.json
# Paste the JSON content
```

**Step 3: Configure the n8n Workflow**

1. Select the Google Drive node and n8n credential.
2. Select the source folder, for example `Document Inbox`.
3. Configure the output node to write into the shared `Originals_RAW` mount.
4. Test that a complete PDF appears in `/data/source`.
5. Configure destinees separately in the classifier web UI.

#### 4.2.4 Local NAS Paths

Local NAS storage is always available as a fallback:

```
Input: /data/source (immutable originals)
Temp: /volume1/Temp (processing cache)
```

To use the local classified output:
1. Open Classification Configuration.
2. Confirm output root: `/data/destination/`
3. Save the configured destinees.
4. The application creates one folder below the output root per destinee.

#### 4.2.5 SharePoint Integration (Future n8n Source)

Future support for Microsoft SharePoint:
- Requires Azure AD app registration
- OAuth2 authentication
- Document library selection via web UI

---

## 5. Initial Startup & Verification

### 5.1 Ingestion and Classification Configuration & First Boot

**First time setup:**

1. Wait for backend to start (30-40 seconds)
2. Navigate to http://192.168.1.100:3000
3. Go to Settings → Classification Configuration
4. Confirm input: `/data/source`
5. Confirm output root: `/data/destination/`
6. Configure the initial destinees: `Destinee A`, `Destinee B`, `Destinee C`
7. Save configuration

**Startup logs:**

```bash
# Check that the n8n handoff and local paths initialized successfully
sudo docker-compose logs classifier-backend | grep -Ei "n8n|Originals_RAW|Classified"

# Expected output:
# [2026-08-24 14:30:00] n8n ingestion monitor initialized
# [2026-08-24 14:30:01] Raw input ready: /data/source
# [2026-08-24 14:30:02] Classified output ready: /data/destination/
```

### 5.2 Health Check Dashboard

```bash
# Monitor container health
watch sudo docker-compose ps

# Real-time log monitoring
sudo docker-compose logs --follow classifier-backend

# Metrics endpoint (if enabled)
curl http://localhost:8000/metrics | grep pdf_processing
```

### 5.3 API Smoke Tests

```bash
# Test health endpoint (includes n8n handoff status)
curl -X GET http://localhost:8000/health | jq .

# Expected response should include:
# {
#   "status": "healthy",
#   "checks": {
#     "pdf_engine": "ok",
#     "ai_api": "ok",
#     "ingestion": "ready",
#     "raw_input": "/data/source",
#     "classified_output": "/data/destination/"
#   }
# }

# Test classification configuration endpoint
curl -X GET http://localhost:8000/api/classification/config | jq .

# Test n8n handoff status
curl -X GET http://localhost:8000/api/ingestion/status | jq .
```

### 5.4 Frontend Verification

Navigate to: `http://192.168.1.100:3000`

**Expected UI sections:**
- **Classification Configuration** (Settings → Classification): Shows n8n status, fixed paths, and destinees
- **Upload Area:** Drag-and-drop or click to upload PDFs from configured source
- **Document Processing History:** Lists recent uploads and their status
- **Settings Panel:** Configure storage, user preferences, credentials

**First-time checklist:**
- [ ] n8n handoff status is visible
- [ ] Classification Configuration shows all destinees
- [ ] Upload area displays (ready to receive documents)
- [ ] Settings accessible and functional

---

## 6. User Access & Authentication

### 6.1 Multi-User Setup (Optional)

Edit `docker-compose.yml` to enable JWT authentication:

```yaml
environment:
  - ENABLE_AUTH=true
  - JWT_SECRET=${JWT_SECRET}
  - JWT_EXPIRATION_HOURS=24
```

Generate secure secret:

```bash
# Generate 32-character random secret
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# Add to .env
JWT_SECRET=your-generated-secret-here

# Restart
sudo docker-compose restart classifier-backend
```

### 6.2 Create Users

API endpoint to create users:

```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "alice@company.com",
    "password": "SecurePassword123!",
    "role": "reviewer"
  }'

# Response:
# {
#   "user_id": "uuid",
#   "username": "alice@company.com",
#   "role": "reviewer"
# }
```

### 6.3 User Roles

| Role | Permissions |
|------|-------------|
| **Admin** | Full access; manage users, system config |
| **Processor** | Upload docs, view results, export |
| **Reviewer** | View only, approve documents before export |

---

## 7. Daily Operations

### 7.1 Process Documents (From n8n Handoff)

Documents are ingested by n8n and handed off as completed PDFs in `/data/source`.

**Via n8n:**
1. Navigate to http://192.168.1.100:3000
2. Confirm the n8n handoff status is healthy
3. Wait for the PDF to appear in the raw input directory
4. Review the analysis and detected destinee
5. Finalize; output is written to `/data/destination/<destinee>/`

**Via API (Upload to Configured Source Backend):**

```bash
#!/bin/bash
# scripts/upload_and_process.sh

PDF_FILE=$1
API_KEY=$2

echo "Uploading $PDF_FILE..."

# Upload
DOC_ID=$(curl -s -X POST http://localhost:8000/api/upload \
  -H "Authorization: Bearer $API_KEY" \
  -F "file=@$PDF_FILE" | jq -r '.doc_id')

echo "Document ID: $DOC_ID"

# Trigger analysis
TASK_ID=$(curl -s -X POST http://localhost:8000/api/analyze \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"doc_id\": \"$DOC_ID\"}" | jq -r '.task_id')

echo "Analysis Task ID: $TASK_ID"

# Poll status
for i in {1..60}; do
  STATUS=$(curl -s -X GET http://localhost:8000/api/status/$TASK_ID \
    -H "Authorization: Bearer $API_KEY" | jq -r '.status')
  
  if [ "$STATUS" = "completed" ]; then
    echo "Analysis complete!"
    break
  fi
  
  echo "Status: $STATUS (attempt $i/60)"
  sleep 5
done
```

### 7.2 Monitor Processing Queue

```bash
# SSH into NAS
ssh admin@192.168.1.100

# View active tasks
curl http://localhost:8000/api/tasks/active

# View processing stats
curl http://localhost:8000/api/stats/daily | jq .

# Example response:
# {
#   "date": "2026-08-17",
#   "total_uploads": 12,
#   "total_pages": 452,
#   "average_processing_time_seconds": 45,
#   "api_cost": "$0.45",
#   "exports_completed": 11,
#   "errors": 1
# }
```

### 7.3 Rotate Logs

Logs auto-rotate via Docker (10MB max size, 3 files retained).

Manual cleanup:

```bash
# Remove logs older than 7 days
find /volume1/docker/classifier/logs -name "*.log" -mtime +7 -delete

# View current disk usage
du -sh /volume1/docker/classifier/logs
```

---

## 8. Monitoring & Alerting

### 8.1 Prometheus Metrics

If enabled (`PROMETHEUS_METRICS=true`), access metrics:

```
http://localhost:8000/metrics
```

Key metrics:

```
# PDF processing
pdf_processing_duration_seconds_bucket
pdf_processing_errors_total

# API calls
http_requests_total
http_request_duration_seconds_bucket

# AI API usage
gemini_requests_total
claude_requests_total
ai_request_cost_usd_total

# Storage
archive_usage_bytes
documents_usage_bytes
temp_usage_bytes
```

### 8.2 Set Up Prometheus Dashboard (Optional)

Create `docker-compose.yml` addition:

```yaml
prometheus:
  image: prom/prometheus:latest
  container_name: prometheus
  restart: always
  
  volumes:
    - /volume1/docker/classifier/config/prometheus.yml:/etc/prometheus/prometheus.yml
    - /volume1/docker/classifier/data/prometheus:/prometheus
  
  ports:
    - "9090:9090"
  
  networks:
    - classifier-net
```

### 8.3 Sentry Error Tracking (Optional)

If `SENTRY_DSN` configured, errors auto-report to Sentry:

1. Create account at [sentry.io](https://sentry.io)
2. Create project for this app
3. Copy DSN
4. Add to `.env`: `SENTRY_DSN=https://...@sentry.io/...`
5. Restart: `sudo docker-compose restart classifier-backend`

All unhandled exceptions now visible at sentry.io dashboard.

### 8.4 Email Alerts (Optional)

Configure email notifications for errors:

```bash
# Add to .env
ALERT_EMAIL=admin@company.com
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=alerts@company.com
SMTP_PASSWORD=your-app-password
```

---

## 9. Backup & Recovery

### 9.1 Automated Daily Backups

Create cron job:

```bash
# SSH into NAS
ssh admin@192.168.1.100

# Edit crontab
sudo crontab -e

# Add this line (backup at 2 AM daily)
0 2 * * * /volume1/docker/classifier/scripts/backup.sh

# Save (Ctrl+O, Enter, Ctrl+X)
```

**Backup Script:**

```bash
#!/bin/bash
# /volume1/docker/classifier/scripts/backup.sh

BACKUP_DIR="/volume1/Backups/classifier"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/backup_$TIMESTAMP.tar.gz"

mkdir -p $BACKUP_DIR

echo "[$(date)] Starting backup..."

# Backup config, logs, and metadata
tar -czf $BACKUP_FILE \
  /volume1/docker/classifier/config \
  /volume1/docker/classifier/logs \
  /data/source \
  --exclude="*.tar.gz"

# Keep only last 7 backups
find $BACKUP_DIR -name "backup_*.tar.gz" -mtime +7 -delete

echo "[$(date)] Backup complete: $BACKUP_FILE"
```

### 9.2 Manual Backup

```bash
# Full backup to NAS storage
sudo docker-compose exec classifier-backend \
  tar -czf /volume1/Backups/manual_backup_$(date +%Y%m%d).tar.gz \
  /volume1/Archive/

# Backup to external USB
# Insert USB, mount via DSM, then:
sudo cp /volume1/Backups/manual_backup_*.tar.gz /media/usb/
```

### 9.3 Disaster Recovery

If system fails completely:

```bash
# 1. Reinstall DSM (via Synology boot ISO if hardware issue)
# 2. Re-install Docker & Container Manager (per section 3.2)
# 3. Restore application directory
cd /volume1/docker/classifier
sudo tar -xzf /media/usb/backup_20260810.tar.gz

# 4. Restore archived documents
sudo tar -xzf /media/usb/backup_20260810.tar.gz \
  --strip-components=1 -C /volume1/

# 5. Restart services
sudo docker-compose up -d

# 6. Verify data integrity
curl http://localhost:8000/api/stats/monthly
```

---

## 10. Troubleshooting Guide

### 10.1 Backend Service Not Starting

```bash
# Check logs
sudo docker-compose logs classifier-backend | tail -50

# Common issues:
# 1. Port 8000 already in use
#    Fix: sudo lsof -i :8000; kill <PID>
# 2. API key invalid/missing
#    Fix: Verify GEMINI_API_KEY in .env
# 3. Storage path permissions
#    Fix: sudo chmod 755 /volume1/Archive
```

### 10.2 Frontend Cannot Connect to Backend

```bash
# Verify backend is running
curl http://localhost:8000/health

# Check Docker network
sudo docker network inspect classifier-net

# If frontend shows "Cannot connect to API":
# 1. Verify API_URL in docker-compose.yml
# 2. Restart frontend:
sudo docker-compose restart classifier-frontend
```

### 10.3 PDF Upload Fails

```bash
# Check available disk space
df -h /volume1/

# If full (<10% free):
# 1. Clear old temp files
sudo rm -rf /volume1/Temp/processing/*

# 2. Review old classified output
sudo find /data/destination -maxdepth 2 -type f -mtime +365

# 3. Check file permissions
sudo chmod 755 /data /data/source /data/destination
```

### 10.4 n8n Handoff or Classified Output Issues

```bash
# Check the n8n handoff status
curl -X GET http://localhost:8000/api/ingestion/status | jq .

# Check the classifier paths
ls -la /data/source
ls -la /data/destination

# If no PDF arrives:
# 1. Check the n8n workflow execution and source credentials.
# 2. Confirm n8n writes to the shared Originals_RAW mount.
# 3. Confirm files are renamed from temporary names only after writing completes.
# 4. Check that the container has read/write permission on Archive.
# 5. Confirm destinee configuration in Settings → Classification Configuration.
```

### 10.5 AI API Calls Timing Out

```bash
# Check internet connectivity
ping 8.8.8.8

# Verify API key is active (test via curl)
curl -X POST https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent \
  -H "x-goog-api-key: $GEMINI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"contents": [{"parts": [{"text": "Hello"}]}]}'

# If quota exceeded:
# 1. Check https://ai.google.dev
# 2. Upgrade to paid tier if needed
# 3. Add fallback to Claude in .env
```

### 10.6 High CPU/Memory Usage

```bash
# Monitor resource usage
sudo docker stats --no-stream

# If excessive:
# 1. Reduce API_WORKERS in .env (default: 4)
# 2. Reduce MAX_CONCURRENT_JOBS
# 3. Increase OCR timeout to avoid retries
# 4. Restart:
sudo docker-compose restart classifier-backend
```

### 10.7 Log Viewing

```bash
# Real-time logs
sudo docker-compose logs -f classifier-backend

# Last 100 lines
sudo docker-compose logs --tail=100

# Specific service
sudo docker-compose logs classifier-frontend

# Filter by keyword
sudo docker-compose logs | grep ERROR
```

---

## 11. Maintenance & Updates

### 11.1 Check for Updates

```bash
# SSH into NAS
ssh admin@192.168.1.100

# Pull latest image (from Docker Hub or private registry)
sudo docker pull classifier:latest

# Compare versions
sudo docker images | grep classifier
```

### 11.2 Update Procedure (Blue-Green Deployment)

```bash
#!/bin/bash
# scripts/update.sh

VERSION=$1  # e.g., v1.3.0

cd /volume1/docker/classifier

echo "Updating to $VERSION..."

# 1. Pull new image
sudo docker pull classifier:$VERSION

# 2. Create new compose file with new version
sudo cp docker-compose.yml docker-compose.yml.backup
sed -i "s/classifier:latest/classifier:$VERSION/g" docker-compose.yml

# 3. Start new containers (old ones still running)
sudo docker-compose up -d --no-deps --build classifier-backend

# 4. Wait for health check
sleep 30
HEALTH=$(curl -s http://localhost:8000/health | jq -r '.status')

if [ "$HEALTH" != "healthy" ]; then
  echo "Health check failed! Rolling back..."
  sudo cp docker-compose.yml.backup docker-compose.yml
  sudo docker-compose up -d --no-deps --build classifier-backend
  exit 1
fi

# 5. Update frontend
sudo docker-compose up -d --no-deps --build classifier-frontend

echo "Update to $VERSION complete!"
```

### 11.3 Database Migrations (If Using PostgreSQL)

```bash
# Run migration
sudo docker-compose exec classifier-backend \
  python -m alembic upgrade head

# View migration history
sudo docker-compose exec classifier-backend \
  python -m alembic history
```

### 11.4 Dependency Updates

```bash
# Update Python dependencies
sudo docker-compose exec classifier-backend \
  pip install --upgrade -r requirements.txt

# The frontend is static native HTML/CSS/JavaScript.
# There are no Node.js or npm dependencies to install.

# Rebuild images with new dependencies
sudo docker-compose build --no-cache
sudo docker-compose up -d
```

---

## 12. Security Management

### 12.1 Change API Keys Quarterly

```bash
# 1. Generate new Gemini key at https://aistudio.google.com
# 2. Update .env
sudo nano /volume1/docker/classifier/config/.env
# GEMINI_API_KEY=new-key-here

# 3. Restart service
sudo docker-compose restart classifier-backend

# 4. Verify new key works
curl -s http://localhost:8000/health | jq .
```

### 12.2 Secure Environment Variables (Docker Secrets)

For production, use Docker Secrets instead of .env:

```bash
# Create secret
echo "your-api-key" | sudo docker secret create gemini_api_key -

# Reference in docker-compose.yml
services:
  classifier-backend:
    secrets:
      - gemini_api_key
    environment:
      GEMINI_API_KEY_FILE: /run/secrets/gemini_api_key

secrets:
  gemini_api_key:
    external: true
```

### 12.3 Network Security

```bash
# Restrict API access to LAN only
sudo iptables -A INPUT -p tcp --dport 8000 -s 192.168.1.0/24 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 8000 -j DROP

# Save firewall rules (Synology)
# Go to DSM → Security → Firewall → Edit Rules
```

### 12.4 Regular Security Audits

```bash
# Monthly: Check for vulnerable dependencies
pip install safety
sudo docker-compose exec classifier-backend safety check

# Quarterly: Audit logs for suspicious activity
grep -i ERROR /volume1/docker/classifier/logs/*.log | grep -i "auth"

# Annually: Penetration testing (hire security firm)
```

---

## Appendix A: Quick Reference Commands

```bash
# Service Management
sudo docker-compose ps                          # Status
sudo docker-compose up -d                       # Start
sudo docker-compose down                        # Stop
sudo docker-compose restart classifier-backend  # Restart

# Logs & Debugging
sudo docker-compose logs -f classifier-backend  # Live logs
sudo docker-compose logs --tail=100             # Last 100 lines
sudo docker exec classifier-backend bash        # Shell access

# Storage & Backups
du -sh /volume1/Archive                         # Archive size
du -sh /data/destination                       # Classified output size
tar -czf backup.tar.gz /volume1/Archive         # Manual backup

# API Testing
curl http://localhost:8000/health               # Health check
curl http://localhost:3000                      # Frontend test

# System Monitoring
free -h                                         # Memory usage
df -h                                           # Disk usage
sudo docker stats                               # Container stats
```

---

## Appendix B: Common Configuration Scenarios

### Scenario 1: High-Volume Processing (500+ docs/day)

```ini
API_WORKERS=8
MAX_CONCURRENT_JOBS=5
OCR_ENABLED=false  # Skip OCR to reduce CPU
CACHE_THUMBNAILS=true
```

Upgrade NAS RAM to 16GB.

### Scenario 2: Google Drive Source & Destination (Most Common)

**Setup Steps:**

1. Create Google Cloud service account
   - Visit https://console.cloud.google.com
   - IAM & Admin → Service Accounts → Create Service Account
   - Name: `classifier-service`, skip optional steps
   - Go to Keys → Add Key → JSON → Download

2. Enable Google Drive API
   - Enabled APIs & services → Enable APIs and Services
   - Search "Google Drive API" → Enable

3. Configure the n8n workflow
  - Select the Google Drive source folder, for example "Document Inbox"
  - Configure n8n to write completed PDFs to `/data/source`
  - Keep Google credentials in n8n, not in the classifier

4. Configure in classifier
  - Settings → Classification Configuration
  - Add or edit destinees: `Destinee A`, `Destinee B`, `Destinee C`
  - Save configuration

5. Verify (first boot)
   - Restart backend: `sudo docker-compose restart classifier-backend`
  - Check logs: `sudo docker-compose logs classifier-backend | grep "Raw input ready"`
  - Should see: `Raw input ready: /data/source`

**Performance:** 
- Recommended for < 100 docs/day
- API quota: 10M free requests/day
- Cost: Free tier, or $0.00-0.10 per 1M requests if exceeding quota

### Scenario 2b: Secure/Air-Gapped Deployment

```ini
ENABLE_AUTH=true
JWT_SECRET=long-random-string
ALLOW_EXTERNAL_API_CALLS=false  # Local OCR only
```

**Storage:** Use the local n8n handoff and classified output paths only.

```bash
# Create local storage directories on NAS
sudo mkdir -p /data/source
sudo mkdir -p /data/destination
sudo chmod 755 /data/source /data/destination
```

### Scenario 3: Multi-User Collaborative Workflow

```ini
ENABLE_MULTI_USER=true
ENABLE_AUTH=true
REVIEWER_APPROVAL_REQUIRED=true
AUDIT_LOG_ENABLED=true
```

**Storage:** Use Google Drive backend with shared Team Drive
- Source: Shared team folder "Inbox"
- Destination: Shared team folder "Processed"
- Archive: Local NAS `/volume1/Archive` (optional, for compliance)

---

## Appendix C: Support & Escalation

**Issues:** File bug reports with logs at [GitHub Issues](https://github.com/project/issues)

**Contact:** support@company.com

**Escalation Path:**
1. Level 1: Consult this manual & troubleshooting section
2. Level 2: Post on community forum with `docker-compose logs` output
3. Level 3: Contact engineering team with full system info (`curl /api/system-info`)

