# Build locusd.exe and Locus.exe using PyInstaller
$VenvDir = ".venv"
$PythonExe = "$VenvDir\Scripts\python.exe"

Write-Host "Building Locus for Windows..."
& $PythonExe -m PyInstaller locusd.spec --noconfirm
& $PythonExe -m PyInstaller tray_app.spec --noconfirm
Write-Host "Done. Binaries in dist\"
