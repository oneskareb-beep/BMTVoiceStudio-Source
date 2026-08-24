# Connect this PC to GitHub and create the public Releases repo other users check.
# Run once:
#   powershell -ExecutionPolicy Bypass -File tools\connect_github.ps1

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

function Get-Gh {
    $candidates = @(
        "gh",
        "$env:ProgramFiles\GitHub CLI\gh.exe",
        "$env:LocalAppData\Programs\GitHub CLI\gh.exe"
    )
    foreach ($c in $candidates) {
        if ($c -eq "gh") {
            $cmd = Get-Command gh -ErrorAction SilentlyContinue
            if ($cmd) { return $cmd.Source }
        } elseif (Test-Path $c) {
            return $c
        }
    }
    return $null
}

$gh = Get-Gh
if (-not $gh) {
    Write-Host "GitHub CLI is not installed. Installing with winget..." -ForegroundColor Cyan
    winget install --id GitHub.cli -e --source winget --accept-package-agreements --accept-source-agreements
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    $gh = Get-Gh
}
if (-not $gh) {
    throw "GitHub CLI (gh) is still missing. Close this window, reopen PowerShell, and run this script again."
}

Write-Host "==> GitHub account" -ForegroundColor Cyan
& $gh auth status 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "A browser window will open. Sign in to GitHub, then return here." -ForegroundColor Yellow
    & $gh auth login --hostname github.com --git-protocol https --web
    if ($LASTEXITCODE -ne 0) { throw "GitHub login did not finish." }
}

$login = (& $gh api user --jq .login).Trim()
if (-not $login) { throw "Could not read the GitHub username." }
$repoName = "BMTVoiceStudio"
$full = "$login/$repoName"

Write-Host "==> Public repo $full (this is what every user will check)" -ForegroundColor Cyan
$exists = $true
& $gh repo view $full 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    $exists = $false
    & $gh repo create $repoName --public --description "BMT Voice Studio portable updates. Users: Help → Check for Updates." --disable-wiki
    if ($LASTEXITCODE -ne 0) { throw "Could not create $full. Create it on github.com and re-run." }
}

$channel = Join-Path $PWD "bmt_voice_studio\update\channel.py"
if (-not (Test-Path $channel)) { throw "channel.py not found: $channel" }
$text = [System.IO.File]::ReadAllText($channel)
$updated = [regex]::Replace($text, 'GITHUB_REPOSITORY = ".*"', "GITHUB_REPOSITORY = `"$full`"")
$utf8 = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($channel, $updated, $utf8)

Write-Host ""
Write-Host "Connected." -ForegroundColor Green
Write-Host "Repo: https://github.com/$full"
Write-Host "Users check: https://api.github.com/repos/$full/releases/latest"
Write-Host ""
Write-Host "After you build a newer portable zip, publish it with:"
Write-Host "  powershell -ExecutionPolicy Bypass -File tools\publish_github_release.ps1"
if ($exists) {
    Write-Host "(Repo already existed — channel URL was still written into the app.)"
}
