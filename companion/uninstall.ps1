$ErrorActionPreference = "Stop"
$registryPath = "HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.aidownload.workspace"
$appDir = Join-Path $env:LOCALAPPDATA "AI-Download-to-Workspace"
$manifestPath = Join-Path $appDir "com.aidownload.workspace.json"

if (Test-Path -LiteralPath $registryPath) {
    $registeredManifest = (Get-Item -LiteralPath $registryPath).GetValue("")
    if ($registeredManifest -and [string]::Equals([string]$registeredManifest, $manifestPath, [System.StringComparison]::OrdinalIgnoreCase)) {
        Remove-Item -LiteralPath $registryPath -Recurse -Force
        Write-Host "Removed ZIP-to-Workspace Chrome native-messaging registration." -ForegroundColor Green
    } else {
        Write-Warning "The Chrome registration points to a different manifest; it was left untouched."
    }
}
if (Test-Path -LiteralPath $appDir) {
    Remove-Item -LiteralPath $appDir -Recurse -Force
    Write-Host "Removed companion files, configuration, and log. Your workspace folder was not deleted." -ForegroundColor Green
}
Write-Host "Uninstall complete. Remove the extension separately from chrome://extensions."
