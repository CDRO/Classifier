$ErrorActionPreference = "Stop"

$projectRoot = $PSScriptRoot
$versionFile = Join-Path $projectRoot "VERSION"
$indexPath = Join-Path $projectRoot "frontend\index.html"
if (-not (Test-Path $versionFile)) {
    throw "VERSION file not found at $versionFile"
}

$version = (Get-Content $versionFile -Raw).Trim()
if (-not $version) {
    throw "VERSION file is empty. Set the release version first."
}

$revision = (git -C $projectRoot rev-parse HEAD).Trim()
if (-not $revision) {
    throw "Unable to determine the current git revision."
}

$sha256 = [System.Security.Cryptography.SHA256]::Create()
$hashBytes = $sha256.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($revision))
$assetVersion = [System.BitConverter]::ToString($hashBytes).Replace("-", "").ToLowerInvariant()
$dockerImage = "cdro/classifier"

function Ensure-IndexVersionStamp {
    if (-not (Test-Path $indexPath)) {
        throw "Frontend index template not found: $indexPath"
    }

    $content = Get-Content -Path $indexPath -Raw
    $updated = $content.Replace("__APP_VERSION__", $assetVersion)
    if ($updated -eq $content) {
        throw "Frontend index template is missing the __APP_VERSION__ placeholder."
    }

    Set-Content -Path $indexPath -Value $updated -NoNewline
    Write-Host "Updated $indexPath with asset cache version $assetVersion"
}

function Build-ClassifierImage {
    Write-Host "Building Docker image for ${dockerImage}:${version}"
    & docker build --build-arg "APP_VERSION=${version}" --build-arg "APP_REVISION=${revision}" -t "${dockerImage}:${version}" -t "${dockerImage}:latest" $projectRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Docker build failed for version $version"
    }
}

function Push-ClassifierImage {
    Write-Host "Pushing ${dockerImage}:${version}"
    & docker push "${dockerImage}:${version}"
    if ($LASTEXITCODE -ne 0) {
        throw "Docker push failed for ${dockerImage}:${version}"
    }

    Write-Host "Pushing ${dockerImage}:latest"
    & docker push "${dockerImage}:latest"
    if ($LASTEXITCODE -ne 0) {
        throw "Docker push failed for ${dockerImage}:latest"
    }
}

Ensure-IndexVersionStamp
Build-ClassifierImage
Push-ClassifierImage
Write-Host "Release $version is built and pushed to Docker Hub."
# Checkout frontend/index.html back to the original state to avoid committing the version stamp
git -C $projectRoot checkout -- $indexPath
Write-Host "Restored $indexPath to original state."
