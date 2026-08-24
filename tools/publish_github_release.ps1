# Publish the portable zip already built by build_windows.ps1 to GitHub Releases.
# powershell -ExecutionPolicy Bypass -File tools\publish_github_release.ps1

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

$version = (Get-Content -Raw "VERSION").Trim()
$zip = Join-Path $PWD "release\BMTVoiceStudio-$version-Windows-x64-Portable.zip"
if (-not (Test-Path $zip)) {
    throw "Missing $zip. Run build_windows.ps1 first."
}

$channel = Get-Content -Raw "bmt_voice_studio\update\channel.py"
$repo = ""
if ($channel -match "GITHUB_REPOSITORY = '([^']+)'") { $repo = $Matches[1] }
if (-not $repo -and $channel -match 'GITHUB_REPOSITORY = "([^"]+)"') { $repo = $Matches[1] }
if (-not $repo) { throw "GitHub repo is empty. Run tools\connect_github.ps1 first." }

$ghPath = "$env:ProgramFiles\GitHub CLI\gh.exe"
if (-not (Test-Path $ghPath)) {
    $cmd = Get-Command gh -ErrorAction SilentlyContinue
    if ($cmd) { $ghPath = $cmd.Source }
}
if (-not (Test-Path $ghPath)) { throw "GitHub CLI (gh) is not installed." }

Write-Host "==> Publishing v$version to $repo" -ForegroundColor Cyan
$sha = "$zip.sha256"
if (-not (Test-Path $sha)) {
    $hash = (Get-FileHash -Algorithm SHA256 -Path $zip).Hash.ToLower()
    Set-Content -Path $sha -Value "$hash  $(Split-Path $zip -Leaf)" -Encoding ASCII
}
$notesFile = Join-Path $PWD "release\v$version-notes.txt"
$notesArgs = @()
if (Test-Path $notesFile) {
    $notesArgs = @("--notes-file", $notesFile)
} else {
    $notesArgs = @("--notes", "Portable Windows update. Open Help, Check for Updates. If download freezes, use Open zip in browser, then Choose update zip.")
}
$ErrorActionPreference = "Continue"
$view = & $ghPath release view "v$version" --repo $repo 2>&1
$ErrorActionPreference = "Stop"
if ($LASTEXITCODE -eq 0) {
    Write-Host "Release v$version already exists - uploading zip." -ForegroundColor Yellow
    & $ghPath release upload "v$version" $zip $sha --repo $repo --clobber
} else {
    & $ghPath release create "v$version" $zip $sha --repo $repo --title "BMT Voice Studio $version" --latest @notesArgs
}
if ($LASTEXITCODE -ne 0) { throw "GitHub release failed." }

Write-Host "Published: https://github.com/$repo/releases/tag/v$version" -ForegroundColor Green
