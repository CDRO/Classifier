& "$PSScriptRoot\Start-DockerDesktop.ps1"

function Build-Image {
    Write-Host "Building image..."
    docker build -t (Split-Path $PWD -Leaf).ToLower() .
    if ($LASTEXITCODE -ne 0) {
        throw "Docker build failed with exit code $LASTEXITCODE"
    }
}

function Start-Container {
    Write-Host "Starting container..."
    # Adapt paths to your needs
    docker run -d --name (Split-Path $PWD -Leaf).ToLower() -p 3000:3000 -v "$(Get-Location)/log:/var/log/$((Split-Path $PWD -Leaf).ToLower())/" -v "$(Get-Location)/app/data:/data/config/" -v "$(Get-Location)/data/Originals_RAW:/data/source" -v "$(Get-Location)/data/Destination:/data/destination" --env-file docker.env (Split-Path $PWD -Leaf).ToLower() | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker run failed with exit code $LASTEXITCODE"
    }
}

function Stop-Container {
    Write-Host "Stopping container if it exists..."
    docker rm -f (Split-Path $PWD -Leaf).ToLower() | Out-Null
}

Write-Host "Press Ctrl+R to stop, remove the old container, rebuild, and restart. Press Ctrl+C to quit."

while ($true) {
    try {
        Stop-Container
    } catch {
        # ignore if the container does not exist
    }

    try {
        Build-Image
    } catch {
        Write-Host "Build failed. Press Ctrl+R to retry."
        while ($true) {
            if ([Console]::KeyAvailable) {
                $key = [Console]::ReadKey($true)
                if ($key.Modifiers -band [ConsoleModifiers]::Control -and $key.Key -eq 'R') {
                    break
                }
            }
            Start-Sleep -Milliseconds 200
        }
        continue
    }

    try {
        Start-Container
    } catch {
        Write-Host "Failed to start container: $($_.Exception.Message)"
        Start-Sleep -Seconds 2
        continue
    }

    Write-Host "Server started. Press Ctrl+R to rebuild and restart. Press Ctrl+C to quit."
    while ($true) {
        if ([Console]::KeyAvailable) {
            $key = [Console]::ReadKey($true)
            if ($key.Modifiers -band [ConsoleModifiers]::Control -and $key.Key -eq 'R') {
                Stop-Container
                break
            }
        }
        Start-Sleep -Milliseconds 200
    }
}