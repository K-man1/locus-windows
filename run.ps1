# Locus launcher for Windows
# Finds a Chromium browser, launches it with the debug port, then starts the tray app.

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

$VenvDir = ".venv"
$PythonExe = "$VenvDir\Scripts\python.exe"
$PipExe    = "$VenvDir\Scripts\pip.exe"

# ── Check Python 3.10+ ────────────────────────────────────────────────────────
$PythonVersion = python --version 2>&1
if ($PythonVersion -notmatch "3\.(1[0-9]|[2-9][0-9])") {
    Write-Error "Python 3.10+ required. Got: $PythonVersion"
    exit 1
}

# ── Create venv if needed ─────────────────────────────────────────────────────
if (-not (Test-Path $VenvDir)) {
    Write-Host "Creating virtual environment..."
    python -m venv $VenvDir
}

# ── Install deps if needed ────────────────────────────────────────────────────
$TestImport = & $PythonExe -c "import pystray" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing dependencies..."
    & $PipExe install -r requirements.txt
}

# ── Create AppData dir if needed ──────────────────────────────────────────────
$AppData = Join-Path $env:APPDATA "Locus"
if (-not (Test-Path $AppData)) {
    New-Item -ItemType Directory -Path $AppData -Force | Out-Null
}

# ── Copy example config if no config exists ───────────────────────────────────
$ConfigPath = Join-Path $AppData "config.json"
if (-not (Test-Path $ConfigPath)) {
    Copy-Item "config.example.json" $ConfigPath
    Write-Host "Created default config at $ConfigPath"
    Write-Host "Edit it to set your override_code and optional integrations."
}

# ── Find and launch a Chromium browser with debug port ────────────────────────
$Browsers = @(
    @{Name = "Chrome";   Path = "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"},
    @{Name = "Edge";     Path = "$env:LOCALAPPDATA\Microsoft\Edge\Application\msedge.exe"},
    @{Name = "Brave";    Path = "$env:LOCALAPPDATA\BraveSoftware\Brave-Browser\Application\brave.exe"},
    @{Name = "Vivaldi";  Path = "$env:LOCALAPPDATA\Vivaldi\Application\vivaldi.exe"}
)

$BrowserLaunched = $false
foreach ($Browser in $Browsers) {
    if (Test-Path $Browser.Path) {
        Write-Host "Launching $($Browser.Name) with debug port 9222..."
        Start-Process $Browser.Path "--remote-debugging-port=9222 --remote-allow-origins=*"
        $BrowserLaunched = $true
        Start-Sleep -Milliseconds 1500
        break
    }
}

if (-not $BrowserLaunched) {
    Write-Host "Warning: No supported browser found. Website blocking will not work."
    Write-Host "Launch your browser manually with: --remote-debugging-port=9222 --remote-allow-origins=*"
}

# ── Start Locus ───────────────────────────────────────────────────────────────
Write-Host "Starting Locus..."
& $PythonExe locus_app.py
