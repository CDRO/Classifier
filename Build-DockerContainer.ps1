$ErrorActionPreference = "Stop"

# --- [1. Abhängigkeiten & Umgebung prüfen] ---
Write-Host "Verifying environment and dependencies..."

# Automatische Installation von Posh-SSH falls nicht vorhanden
if (-not (Get-Module -ListAvailable -Name Posh-SSH)) {
    Write-Host "Posh-SSH module not found. Installing now for current user..." -ForegroundColor Yellow
    Install-Module -Name Posh-SSH -Scope CurrentUser -Force -AllowClobber
}

$projectRoot = $PSScriptRoot
$versionFile = Join-Path $projectRoot "VERSION"
$indexPath = Join-Path $projectRoot "frontend\index.html"
$configFile = Join-Path $projectRoot "nas-config.json"
$dockerImage = "cdro/classifier"

# Validierung der Projektdateien
if (-not (Test-Path $versionFile)) { throw "VERSION file not found at $versionFile" }
if (-not (Test-Path $configFile)) { throw "Configuration file not found at $configFile. Please create it first." }

# Konfiguration einlesen
$nasConfig = Get-Content -Raw -Path $configFile | ConvertFrom-Json

$version = (Get-Content $versionFile -Raw).Trim()
if (-not $version) { throw "VERSION file is empty." }
$revision = (git -C $projectRoot rev-parse HEAD).Trim()
if (-not $revision) { throw "Unable to determine git revision." }

$sha256 = [System.Security.Cryptography.SHA256]::Create()
$hashBytes = $sha256.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($revision))
$assetVersion = [System.BitConverter]::ToString($hashBytes).Replace("-", "").ToLowerInvariant()

# --- [2. Funktionen] ---
function Ensure-IndexVersionStamp {
    if (-not (Test-Path $indexPath)) { throw "Frontend index template not found: $indexPath" }
    $content = Get-Content -Path $indexPath -Raw
    $updated = $content.Replace("__APP_VERSION__", $assetVersion)
    if ($updated -eq $content) { throw "Placeholder missing in index.html." }
    Set-Content -Path $indexPath -Value $updated -NoNewline
    Write-Host "Updated $indexPath with asset cache version $assetVersion"
}

function Build-ClassifierImage {
    Write-Host "Building Docker image for ${dockerImage}:${version}"
    & docker build --build-arg "APP_VERSION=${version}" --build-arg "APP_REVISION=${revision}" -t "${dockerImage}:${version}" -t "${dockerImage}:latest" $projectRoot
    if ($LASTEXITCODE -ne 0) { throw "Docker build failed." }
}

function Push-ClassifierImage {
    Write-Host "Pushing ${dockerImage}:${version} and latest to Docker Hub..."
    & docker push "${dockerImage}:${version}"
    & docker push "${dockerImage}:latest"
    if ($LASTEXITCODE -ne 0) { throw "Docker push failed." }
}

function Deploy-ToSynology {
    Write-Host "Connecting to Synology NAS ($($nasConfig.NasIp)) via SSH..."
    Import-Module Posh-SSH

    # SSH-Anmeldedaten vorbereiten
    $secPass = ConvertTo-SecureString $nasConfig.NasPassword -AsPlainText -Force
    $cred = New-Object System.Management.Automation.PSCredential ($nasConfig.NasUser, $secPass)
    
    # Verbindung aufbauen (akzeptiert den Host-Key automatisch)
    $session = New-SSHSession -ComputerName $nasConfig.NasIp -Credential $cred -AcceptKey

    try {
        Write-Host "Triggering Zero-Downtime Update on Synology..."
        
        # Befehlskette für den nahtlosen Wechsel via Traefik & Docker Compose
        $cmd = "cd $($nasConfig.ComposeDir) && " +
               "docker compose pull && " +
               "docker compose up -d --no-deps --scale classifier=2 && " +
               "docker compose up -d --no-deps --scale classifier=1"

        # Befehl via sudo -S ausführen, um das Passwort via STDIN zu übergeben
        $sudoCmd = "echo '$($nasConfig.NasPassword)' | sudo -S bash -c '$cmd'"

        # Ausführung auf der Synology
        $result = Invoke-SSHCommand -SSHSession $session -Command $sudoCmd
        
        if ($result.ExitStatus -ne 0) {
            Write-Error "Deployment failed: $($result.Output)"
            throw "Synology deployment script returned exit code $($result.ExitStatus)"
        }

        Write-Host "Synology Deployment successfully completed without downtime!" -ForegroundColor Green
        Write-Host $($result.Output)
    }
    finally {
        # SSH-Sitzung in jedem Fall sauber schließen
        Remove-SSHSession -SSHSession $session
    }
}

# --- [3. Ablaufsteuerung] ---
try {
    Ensure-IndexVersionStamp
    Build-ClassifierImage
    Push-ClassifierImage
    Deploy-ToSynology
    Write-Host "Release $version is successfully built, pushed and deployed." -ForegroundColor Green
}
finally {
    # Stellt sicher, dass das Frontend-Template immer zurückgesetzt wird, selbst bei Fehlern
    if (Test-Path $indexPath) {
        git -C $projectRoot checkout -- $indexPath
        Write-Host "Restored $indexPath to original state."
    }
}
