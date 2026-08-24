# Check if Docker Desktop is running
$DockerProcess = Get-Process -Name "Docker Desktop" -ErrorAction SilentlyContinue

if (-not $DockerProcess) {
    Write-Host "Launching Docker Desktop..." -ForegroundColor Yellow
    Start-Process -FilePath "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    
    # Loop until 'docker ps' executes successfully without error
    while ($true) {
        & docker ps > $null 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Docker Engine is fully ready!" -ForegroundColor Green
            break
        }
        Write-Host "Waiting for Docker Engine to initialize..." -ForegroundColor Cyan
        Start-Sleep -Seconds 3
    }
} else {
    Write-Host "Docker Desktop is already running." -ForegroundColor Green
}