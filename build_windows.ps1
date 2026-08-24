# BMT Voice Studio Windows production build + portable release package
# Creates:
#   dist\BMTVoiceStudio-<VERSION>\BMTVoiceStudio.exe
#   release\BMTVoiceStudio-<VERSION>-Windows-x64-Portable\
#   release\BMTVoiceStudio-<VERSION>-Windows-x64-Portable.zip
#   release\BMTVoiceStudio-<VERSION>-Windows-x64-Portable.zip.sha256

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$version = (Get-Content -Raw "VERSION").Trim()
$portableName = "BMTVoiceStudio-$version-Windows-x64-Portable"
$specName = "BMTVoiceStudio-$version.spec"
if (-not (Test-Path $specName)) {
    Write-Error "Missing $specName - copy the previous .spec and bump the version name."
    exit 1
}

Write-Host "==> Creating virtual environment (.venv)" -ForegroundColor Cyan
if (-not (Test-Path ".venv")) {
    py -3.12 -m venv .venv
}
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

Write-Host "==> Installing dependencies" -ForegroundColor Cyan
& $py -m pip install --upgrade pip
& $py -m pip install -r requirements.txt
& $py -m pip install -e ".[dev]"

Write-Host "==> Running tests" -ForegroundColor Cyan
& $py -m pytest -q
if ($LASTEXITCODE -ne 0) {
    Write-Error "Tests failed - aborting build."
    exit $LASTEXITCODE
}

Write-Host "==> Stamping build identity" -ForegroundColor Cyan
& $py tools\stamp_build.py

Write-Host "==> Building with PyInstaller (one-folder)" -ForegroundColor Cyan
& $py -m PyInstaller --noconfirm --clean $specName
if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller failed."
    exit $LASTEXITCODE
}

$distDir = Join-Path $PSScriptRoot "dist\BMTVoiceStudio-$version"
$exe = Join-Path $distDir "BMTVoiceStudio.exe"
if (-not (Test-Path $exe)) {
    Write-Error "Build finished but EXE was not found: $exe"
    exit 1
}

Copy-Item -Force "THIRD_PARTY_NOTICES.txt" (Join-Path $distDir "THIRD_PARTY_NOTICES.txt")
Copy-Item -Force "VERSION" (Join-Path $distDir "VERSION")

Write-Host "==> Scrubbing packaged tree" -ForegroundColor Cyan
Get-ChildItem -Path $distDir -Recurse -Force -ErrorAction SilentlyContinue |
    Where-Object {
        $_.Name -in @(".git", ".pytest_cache", "__pycache__", ".env", "credentials.json") -or
        $_.Name -like "*.pyc" -or
        $_.Name -like "*.ssh*" -or
        $_.FullName -match "\\qa_screenshots\\" -or
        $_.FullName -match "\\agent-transcripts\\"
    } |
    ForEach-Object {
        if ($_.PSIsContainer) { Remove-Item -Recurse -Force $_.FullName -ErrorAction SilentlyContinue }
        else { Remove-Item -Force $_.FullName -ErrorAction SilentlyContinue }
    }

$releaseRoot = Join-Path $PSScriptRoot "release\$portableName"
if (Test-Path $releaseRoot) {
    Remove-Item -Recurse -Force $releaseRoot
}
New-Item -ItemType Directory -Path $releaseRoot -Force | Out-Null
Copy-Item -Recurse -Force $distDir (Join-Path $releaseRoot "BMTVoiceStudio")

$readmePath = Join-Path $releaseRoot "README.txt"
@(
    "BMT Voice Studio $version"
    "Windows 10/11 x64"
    ""
    "How to use:"
    "1. Copy/extract the BMTVoiceStudio folder anywhere."
    "2. Open BMTVoiceStudio.exe."
    "3. Internet connection is required for neural voice generation."
    "4. Generated files are saved under Documents\BMT Voice Studio\Exports by default."
    "5. Later versions: Help > Check for Updates (no new setup share)."
    ""
    "Do not install Python. Keep the whole BMTVoiceStudio folder - do not move the EXE alone."
) | Set-Content -Path $readmePath -Encoding UTF8

$testCount = & $py -c "import pathlib; print(sum(1 for p in pathlib.Path('tests').glob('test_*.py')))"
$commit = ""
try { $commit = (git rev-parse --short HEAD 2>$null) } catch { $commit = "" }

$buildTs = & $py -c "from bmt_voice_studio.build_info import BUILD_TIMESTAMP; print(BUILD_TIMESTAMP)"

$manifest = @{
    product_name = "BMT Voice Studio"
    version = $version
    build_timestamp = $buildTs
    platform = "Windows"
    architecture = "x64"
    packaging_mode = "pyinstaller-onedir"
    executable_relative_path = "BMTVoiceStudio/BMTVoiceStudio.exe"
    approved_languages = @("en", "fr", "sw", "pt")
    provider = "Edge TTS"
    piper_production_policy = "forbidden_for_approved_daily"
    edge_provider_required = $true
    voice_configuration = @{
        en = @{ locale = "en-NG"; male_voice = "en-NG-AbeoNeural"; female_voice = "en-NG-EzinneNeural"; rate = "-10%"; pitch = "-3Hz"; volume = "+0%"; pause_ms = 500; low_pass_hz = 7000 }
        fr = @{ locale = "fr-FR"; male_voice = "fr-FR-HenriNeural"; female_voice = "fr-FR-DeniseNeural"; rate = "-8%"; pitch = "-1Hz"; volume = "+5%"; pause_ms = 500; low_pass_hz = $null }
        sw = @{ target_region = "Congo/DRC"; target_locale = "sw-CD"; fallback_locale = "sw-TZ"; male_voice = "sw-TZ-DaudiNeural"; female_voice = "sw-TZ-RehemaNeural"; rate = "-10%"; pitch = "-3Hz"; volume = "+5%"; pause_ms = 500; low_pass_hz = 7000; approved_fallback = $true }
        pt = @{ target_region = "Angola"; target_locale = "pt-AO"; fallback_locale = "pt-BR"; male_voice = "pt-BR-AntonioNeural"; female_voice = "pt-BR-FranciscaNeural"; rate = "-10%"; pitch = "-3Hz"; volume = "+5%"; pause_ms = 500; low_pass_hz = 7000; approved_fallback = $true }
    }
    audio_delivery = @{
        wav = @{ channels = 1; sample_rate_hz = 44100 }
        mp3 = @{ bitrate_kbps = 192 }
        pause_ms = 500
    }
    test_module_count = [int]$testCount
    build_commit = $commit
}
$manifestPath = Join-Path $releaseRoot "RELEASE_MANIFEST.json"
$manifest | ConvertTo-Json -Depth 6 | Set-Content -Path $manifestPath -Encoding UTF8

$zipPath = Join-Path $PSScriptRoot "release\$portableName.zip"
if (Test-Path $zipPath) { Remove-Item -Force $zipPath }
Compress-Archive -Path $releaseRoot -DestinationPath $zipPath -Force

$hash = (Get-FileHash -Algorithm SHA256 -Path $zipPath).Hash.ToLower()
$setContent = "$hash  $portableName.zip"
Set-Content -Path (Join-Path $PSScriptRoot "release\$portableName.zip.sha256") -Value $setContent -Encoding ASCII
Set-Content -Path (Join-Path $releaseRoot "SHA256SUMS.txt") -Value $setContent -Encoding ASCII

$sumsPath = Join-Path $PSScriptRoot "release\SHA256SUMS.txt"
Add-Content -Path $sumsPath -Value $setContent

Write-Host "==> Refreshing Desktop shortcut + portable zip" -ForegroundColor Cyan
$desktopRoots = @(
    [Environment]::GetFolderPath("Desktop"),
    (Join-Path $env:USERPROFILE "Desktop"),
    (Join-Path $env:USERPROFILE "OneDrive\Desktop")
) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -Unique
foreach ($desktop in $desktopRoots) {
    Get-ChildItem -Path $desktop -Filter "BMT Voice Studio*.lnk" -ErrorAction SilentlyContinue |
        Remove-Item -Force -ErrorAction SilentlyContinue
    Get-ChildItem -Path $desktop -Filter "BMTVoiceStudio-*-Windows-x64-Portable.zip" -ErrorAction SilentlyContinue |
        Remove-Item -Force -ErrorAction SilentlyContinue

    $lnkPath = Join-Path $desktop "BMT Voice Studio.lnk"
    $ws = New-Object -ComObject WScript.Shell
    $sc = $ws.CreateShortcut($lnkPath)
    $sc.TargetPath = $exe
    $sc.WorkingDirectory = $distDir
    $sc.Description = "BMT Voice Studio $version"
    $sc.IconLocation = "$exe,0"
    $sc.Save()

    Copy-Item -Force $zipPath (Join-Path $desktop "$portableName.zip")
    Write-Host "  Desktop shortcut: $lnkPath"
    Write-Host "  Desktop zip: $(Join-Path $desktop "$portableName.zip")"
}

Write-Host ""
Write-Host "Build complete:" -ForegroundColor Green
Write-Host "  EXE: $exe"
Write-Host "  Portable: $releaseRoot"
Write-Host "  ZIP: $zipPath"
Write-Host "  SHA256: $hash"
Write-Host "Distribute the entire BMTVoiceStudio folder (or the portable ZIP)."
