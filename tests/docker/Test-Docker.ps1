$ErrorActionPreference = "Stop"

$image = "classifier-integration-test"
$container = "classifier-integration-$([guid]::NewGuid().ToString('N').Substring(0, 12))"
$testRoot = Join-Path ([System.IO.Path]::GetTempPath()) $container
$sourcePath = Join-Path $testRoot "source"
$destinationPath = Join-Path $testRoot "destination"
$archivePath = Join-Path $testRoot "archive"
$configPath = Join-Path $testRoot "config"
$tempPath = Join-Path $testRoot "temp"
$portProbe = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)

function Assert-Equal {
    param(
        [object]$Actual,
        [object]$Expected,
        [string]$Message
    )
    if ($Actual -ne $Expected) {
        throw "$Message. Expected '$Expected', got '$Actual'."
    }
}

try {
    New-Item -ItemType Directory -Path $sourcePath, $destinationPath, $archivePath, $configPath, $tempPath | Out-Null
    Set-Content -Path (Join-Path $sourcePath "handoff.pdf") -Value "%PDF-1.4"
    Set-Content -Path (Join-Path $sourcePath "handoff.tmp") -Value "incomplete"

    docker build --build-arg APP_VERSION=0.0.0-test --build-arg APP_REVISION=integration-test -t $image .
    if ($LASTEXITCODE -ne 0) {
        throw "Docker image build failed."
    }

    $portProbe.Start()
    $port = $portProbe.LocalEndpoint.Port
    $portProbe.Stop()

    docker run -d --name $container -p "${port}:3000" `
        -v "${sourcePath}:/data/source" `
        -v "${destinationPath}:/data/destination" `
        -v "${archivePath}:/data/archive" `
        -v "${configPath}:/data/config" `
        -v "${tempPath}:/data/temp" `
        $image | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker container failed to start."
    }

    $baseUrl = "http://127.0.0.1:$port"

    $configResponse = $null
    for ($attempt = 1; $attempt -le 40; $attempt++) {
        try {
            $configResponse = Invoke-RestMethod -Uri "$baseUrl/api/classification/config" -Method Get
            break
        } catch {
            if ($attempt -eq 40) {
                throw "Container API did not become ready."
            }
            Start-Sleep -Milliseconds 100
        }
    }

    Assert-Equal $configResponse.input_path "/data/source" "Input path mismatch"
    Assert-Equal $configResponse.output_root "/data/destination/" "Output path mismatch"
    Assert-Equal $configResponse.destinees.Count 0 "Default destinee count mismatch"

    $analysisStatus = Invoke-RestMethod -Uri "$baseUrl/api/analysis/status" -Method Get
    Assert-Equal $analysisStatus.gemini_configured $false "Unexpected Gemini configuration in isolated test"
    Assert-Equal $analysisStatus.fallback "local" "Analysis fallback mismatch"
    Assert-Equal $analysisStatus.available $false "Unexpected Gemini availability in isolated test"

    $version = Invoke-RestMethod -Uri "$baseUrl/api/version" -Method Get
    Assert-Equal $version.version "0.0.0-test" "Container version mismatch"
    Assert-Equal $version.revision "integration-test" "Container revision mismatch"

    docker exec $container python -c "import pymupdf; pdf=pymupdf.open(); page=pdf.new_page(); page.insert_text((72,72), 'Invoice Amount Due VAT'); pdf.save('/data/source/handoff.pdf')"
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create valid PDF fixture in the test container."
    }
    $tesseractVersion = docker exec $container tesseract --version
    if ($LASTEXITCODE -ne 0) {
        throw "Tesseract OCR is not available in the image."
    }
    $tesseractVersion | Select-Object -First 1 | Write-Output
    docker exec $container sh -c "cp /data/source/handoff.pdf /data/source/second.pdf"
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create second scan fixture."
    }

    $payload = @{ destinees = @("Destinee A", "Destinee B", "Shared") } | ConvertTo-Json
    $updated = Invoke-RestMethod -Uri "$baseUrl/api/classification/config" -Method Post `
        -ContentType "application/json" -Body $payload
    Assert-Equal $updated.destinees.Count 3 "Updated destinee count mismatch"

    $scan = Invoke-RestMethod -Uri "$baseUrl/api/classification/scan" -Method Post
    Assert-Equal $scan.count 2 "Completed PDF scan count mismatch"
    Assert-Equal $scan.files[0].name "handoff.pdf" "Scanned filename mismatch"
    Assert-Equal $scan.files[1].name "second.pdf" "Sorted scanned filename mismatch"
    Assert-Equal $scan.files[0].status "received" "Initial document status mismatch"
    Remove-Item -Force (Join-Path $sourcePath "second.pdf")

    $history = Invoke-RestMethod -Uri "$baseUrl/api/documents/history" -Method Get
    Assert-Equal $history.count 2 "History count mismatch"
    Assert-Equal $history.documents[0].name "handoff.pdf" "History document name mismatch"
    Assert-Equal $history.documents[0].status "received" "History status mismatch"

    $document = Invoke-RestMethod -Uri "$baseUrl/api/documents/handoff.pdf" -Method Get
    Assert-Equal $document.name "handoff.pdf" "Document metadata name mismatch"
    if ($document.size -le 0) {
        throw "Document metadata did not report a positive file size."
    }

    $fileResponse = Invoke-WebRequest -UseBasicParsing -Uri "$baseUrl/api/documents/handoff.pdf/file"
    Assert-Equal $fileResponse.StatusCode 200 "PDF file response status mismatch"
    Assert-Equal $fileResponse.Headers["Content-Type"] "application/pdf" "PDF content type mismatch"
    if ($fileResponse.Headers["Content-Disposition"] -notmatch '^inline') {
        throw "PDF response is not configured for inline browser rendering."
    }

    $prepared = Invoke-RestMethod -Uri "$baseUrl/api/documents/handoff.pdf/prepare" -Method Post
    Assert-Equal $prepared.original_name "handoff.pdf" "Prepared filename mismatch"
    Assert-Equal $prepared.page_count 1 "Prepared page count mismatch"
    Assert-Equal $prepared.status "in_review" "Prepared document status mismatch"
    Assert-Equal $prepared.ocr_used $false "Unexpected OCR usage for text PDF"
    $rotated = Invoke-RestMethod -Uri "$baseUrl/api/documents/handoff.pdf/rotate" -Method Post `
        -ContentType "application/json" -Body (@{ processing_id = $prepared.processing_id; page = 1; rotation = 90 } | ConvertTo-Json)
    Assert-Equal $rotated.rotation 90 "Page rotation mismatch"
    $preparedFile = Invoke-WebRequest -UseBasicParsing -Uri "$baseUrl/api/processing/$($prepared.processing_id)/file"
    Assert-Equal $preparedFile.StatusCode 200 "Prepared file response status mismatch"
    $analysis = Invoke-RestMethod -Uri "$baseUrl/api/documents/handoff.pdf/analyze?processing_id=$($prepared.processing_id)" -Method Post
    Assert-Equal $analysis.topic "Invoice" "Content topic mismatch"
    Assert-Equal $analysis.category "Invoice" "Content category mismatch"
    Assert-Equal $analysis.analysis_source "local" "Unexpected analysis source"
    if (-not $analysis.signals -or $analysis.signals.Count -lt 1) {
        throw "Local analysis signals were not returned."
    }
    if (-not $analysis.title -or -not $analysis.summary) {
        throw "Rich content analysis fields were not returned."
    }
    if ($analysis.suggested_filename -notmatch '^undated_Invoice_handoff\.pdf$') {
        throw "Unexpected suggested filename: $($analysis.suggested_filename)"
    }
    if (-not (Test-Path (Join-Path $tempPath "processing\$($prepared.processing_id)\original.pdf"))) {
        throw "Prepared PDF was not written to processing storage."
    }

    $finalizePayload = @{
        processing_id = $prepared.processing_id
        destinee = "Shared"
        output_filename = "renamed-handoff.pdf"
    } | ConvertTo-Json
    $finalized = Invoke-RestMethod -Uri "$baseUrl/api/documents/handoff.pdf/finalize" -Method Post `
        -ContentType "application/json" -Body $finalizePayload
    Assert-Equal $finalized.status "classified" "Finalization status mismatch"
    Assert-Equal $finalized.destinee "Shared" "Finalization destinee mismatch"
    if (-not (Test-Path (Join-Path $destinationPath "Shared\renamed-handoff.pdf"))) {
        throw "Finalized PDF was not written to the destinee folder."
    }
    if (Test-Path (Join-Path $sourcePath "handoff.pdf")) {
        throw "Finalized PDF still appears in the n8n inbox."
    }
    if (-not (Test-Path (Join-Path $archivePath "handoff.pdf"))) {
        throw "Finalized PDF was not moved to the processed archive."
    }
    if (Test-Path (Join-Path $tempPath "processing\$($prepared.processing_id)")) {
        throw "Temporary processing workspace was not cleaned up."
    }
    $inboxAfterFinalize = Invoke-RestMethod -Uri "$baseUrl/api/classification/scan" -Method Post
    Assert-Equal $inboxAfterFinalize.count 0 "Processed PDF remained in inbox scan"
    $classifiedState = Invoke-RestMethod -Uri "$baseUrl/api/documents/handoff.pdf" -Method Get
    Assert-Equal $classifiedState.status "classified" "Final document status mismatch"
    Assert-Equal $classifiedState.archive_path "/data/archive/handoff.pdf" "Archive path mismatch"
    Assert-Equal $classifiedState.destination_path "/data/destination/Shared/renamed-handoff.pdf" "Renamed destination path mismatch"

    docker exec $container sh -c "cp /data/archive/handoff.pdf /data/source/dismissed.pdf"
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create dismissal fixture."
    }
    $dismissPayload = @{ reason = "Not relevant" } | ConvertTo-Json
    $dismissed = Invoke-RestMethod -Uri "$baseUrl/api/documents/dismissed.pdf/dismiss" -Method Post `
        -ContentType "application/json" -Body $dismissPayload
    Assert-Equal $dismissed.status "dismissed" "Dismissal status mismatch"
    if ((Test-Path (Join-Path $sourcePath "dismissed.pdf")) -or -not (Test-Path (Join-Path $archivePath "dismissed\dismissed.pdf"))) {
        throw "Dismissed PDF was not moved to the dismissed archive."
    }

    docker exec $container sh -c "cp /data/archive/handoff.pdf /data/source/redelivered.pdf"
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create duplicate source fixture."
    }
    $duplicateScan = Invoke-RestMethod -Uri "$baseUrl/api/classification/scan" -Method Post
    Assert-Equal $duplicateScan.count 1 "Duplicate scan count mismatch"
    Assert-Equal $duplicateScan.files[0].status "duplicate" "Duplicate document status mismatch"
    Remove-Item -Force (Join-Path $sourcePath "redelivered.pdf")

    try {
        Invoke-RestMethod -Uri "$baseUrl/api/documents/..%2Fincomplete.pdf" -Method Get | Out-Null
        throw "Path traversal request was accepted."
    } catch {
        if ($_.Exception.Response.StatusCode.value__ -ne 404) {
            throw "Path traversal returned an unexpected status."
        }
    }

    if (-not (Test-Path (Join-Path $destinationPath "Shared"))) {
        throw "Mounted destination did not receive the new destinee folder."
    }

    Write-Output "Docker integration test passed."
} finally {
    docker rm -f $container 2>$null | Out-Null
    Remove-Item -Recurse -Force $testRoot -ErrorAction SilentlyContinue
}
