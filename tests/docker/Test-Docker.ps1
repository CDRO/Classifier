$ErrorActionPreference = "Stop"

$image = "classifier-integration-test"
$container = "classifier-integration-$([guid]::NewGuid().ToString('N').Substring(0, 12))"
$testRoot = Join-Path ([System.IO.Path]::GetTempPath()) $container
$sourcePath = Join-Path $testRoot "source"
$destinationPath = Join-Path $testRoot "destination"
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
    New-Item -ItemType Directory -Path $sourcePath, $destinationPath, $configPath, $tempPath | Out-Null
    Set-Content -Path (Join-Path $sourcePath "handoff.pdf") -Value "%PDF-1.4"
    Set-Content -Path (Join-Path $sourcePath "handoff.tmp") -Value "incomplete"

    docker build -t $image .
    if ($LASTEXITCODE -ne 0) {
        throw "Docker image build failed."
    }

    $portProbe.Start()
    $port = $portProbe.LocalEndpoint.Port
    $portProbe.Stop()

    docker run -d --name $container -p "${port}:3000" `
        -v "${sourcePath}:/data/source" `
        -v "${destinationPath}:/data/destination" `
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
    Assert-Equal $configResponse.destinees.Count 3 "Default destinee count mismatch"

    docker exec $container python -c "import pymupdf; pdf=pymupdf.open(); pdf.new_page(); pdf.save('/data/source/handoff.pdf')"
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create valid PDF fixture in the test container."
    }

    $payload = @{ destinees = @("Destinee A", "Destinee B", "Destinee C", "Shared") } | ConvertTo-Json
    $updated = Invoke-RestMethod -Uri "$baseUrl/api/classification/config" -Method Post `
        -ContentType "application/json" -Body $payload
    Assert-Equal $updated.destinees.Count 4 "Updated destinee count mismatch"

    $scan = Invoke-RestMethod -Uri "$baseUrl/api/classification/scan" -Method Post
    Assert-Equal $scan.count 1 "Completed PDF scan count mismatch"
    Assert-Equal $scan.files[0].name "handoff.pdf" "Scanned filename mismatch"

    $document = Invoke-RestMethod -Uri "$baseUrl/api/documents/handoff.pdf" -Method Get
    Assert-Equal $document.name "handoff.pdf" "Document metadata name mismatch"
    if ($document.size -le 0) {
        throw "Document metadata did not report a positive file size."
    }

    $prepared = Invoke-RestMethod -Uri "$baseUrl/api/documents/handoff.pdf/prepare" -Method Post
    Assert-Equal $prepared.original_name "handoff.pdf" "Prepared filename mismatch"
    Assert-Equal $prepared.page_count 1 "Prepared page count mismatch"
    if (-not (Test-Path (Join-Path $tempPath "processing\$($prepared.processing_id)\original.pdf"))) {
        throw "Prepared PDF was not written to processing storage."
    }

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
