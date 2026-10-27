$ErrorActionPreference = "Stop"

Write-Host "`nZIP-to-Workspace companion setup`n" -ForegroundColor Cyan
$extensionId = (Read-Host "Chrome Extension ID from chrome://extensions").Trim()
if ($extensionId -notmatch '^[a-p]{32}$') {
    throw "Invalid Chrome Extension ID. It must be 32 lowercase letters from a through p."
}

$defaultWorkspace = Join-Path $env:USERPROFILE "AI-Workspace"
$workspaceInput = Read-Host "Workspace directory [Enter for $defaultWorkspace]"
if ([string]::IsNullOrWhiteSpace($workspaceInput)) {
    $workspace = $defaultWorkspace
} else {
    $workspace = [Environment]::ExpandEnvironmentVariables($workspaceInput.Trim().Trim('"'))
}
$workspace = [System.IO.Path]::GetFullPath($workspace)
New-Item -ItemType Directory -Force -Path $workspace | Out-Null

$pythonExe = $null
try {
    $candidate = (& py -3 -c "import sys; print(sys.executable)" 2>$null | Select-Object -Last 1)
    if ($candidate) { $pythonExe = $candidate.Trim() }
} catch {}
if (-not $pythonExe -or -not (Test-Path -LiteralPath $pythonExe)) {
    try {
        $candidate = (& python -c "import sys; print(sys.executable)" 2>$null | Select-Object -Last 1)
        if ($candidate) { $pythonExe = $candidate.Trim() }
    } catch {}
}
if (-not $pythonExe -or -not (Test-Path -LiteralPath $pythonExe)) {
    throw "Python 3 was not found. Install Python 3.10 or newer, then run setup again."
}
try {
    & $pythonExe -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" 2>$null
    if ($LASTEXITCODE -ne 0) { throw "Python 3.10 or newer is required." }
} catch {
    throw "Python 3.10 or newer is required. Install a supported Python version and run setup again."
}
# Native messaging requires a process that reads/writes stdin/stdout; do not use pythonw.exe.

$sourceHost = Join-Path $PSScriptRoot "host.py"
if (-not (Test-Path -LiteralPath $sourceHost)) { throw "host.py was not found beside setup.ps1." }
$appDir = Join-Path $env:LOCALAPPDATA "AI-Download-to-Workspace"
New-Item -ItemType Directory -Force -Path $appDir | Out-Null
$installedHost = Join-Path $appDir "host.py"
Copy-Item -LiteralPath $sourceHost -Destination $installedHost -Force

$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
$config = @{ extract_dir = $workspace } | ConvertTo-Json
[System.IO.File]::WriteAllText((Join-Path $appDir "config.json"), $config, $utf8NoBom)

$manifestPath = Join-Path $appDir "com.aidownload.workspace.json"
$manifest = @{
    name = "com.aidownload.workspace"
    description = "ZIP-to-Workspace local companion"
    path = $pythonExe
    type = "stdio"
    allowed_origins = @("chrome-extension://$extensionId/")
    arguments = @($installedHost)
} | ConvertTo-Json -Depth 5
[System.IO.File]::WriteAllText($manifestPath, $manifest, $utf8NoBom)

$registryPath = "HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.aidownload.workspace"
New-Item -Path $registryPath -Force | Out-Null
Set-Item -Path $registryPath -Value $manifestPath

Write-Host "`nSetup completed." -ForegroundColor Green
Write-Host "Workspace: $workspace"
Write-Host "Python:    $pythonExe"
Write-Host "Host:      $installedHost"
Write-Host "Manifest:  $manifestPath"
Write-Host "`nRestart Chrome before testing." -ForegroundColor Cyan
