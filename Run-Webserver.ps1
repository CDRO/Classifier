& "$PSScriptRoot\Start-DockerDesktop.ps1"

$projectRoot = $PSScriptRoot
$imageName = $((Split-Path $projectRoot -Leaf).ToLower())
function Build-ClassifierImage {
    Write-Host "Building image..."
    Write-Host $imageName
    docker build -t $imageName $projectRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Docker build failed with exit code $LASTEXITCODE"
    }
}

function Start-ClassifierContainer {
    Write-Host "Starting container..."
    docker run -d --name $imageName -p 3000:3000 -v "$projectRoot/log:/var/log/$imageName/" -v "$projectRoot/app/data:/data/config/" -v "$projectRoot/data/Originals_RAW:/data/source" -v "$projectRoot/data/Destination:/data/destination" -v "$projectRoot/data/Archive:/data/archive" --env-file "$projectRoot/docker.env" $imageName | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker run failed with exit code $LASTEXITCODE"
    }
}

function Stop-ClassifierContainer {
    Write-Host "Stopping container if it exists..."
    docker rm -f $imageName | Out-Null
}

Write-Host "Press Ctrl+R to stop, remove the old container, rebuild, and restart. Press Ctrl+C to quit."

while ($true) {
    try {
        Stop-ClassifierContainer
    } catch {
        # ignore if the container does not exist
    }

    try {
        Build-ClassifierImage
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
        Start-ClassifierContainer
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
                Stop-ClassifierContainer
                break
            }
        }
        Start-Sleep -Milliseconds 200
    }
}