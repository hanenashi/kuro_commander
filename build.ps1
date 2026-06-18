$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$requiredFiles = @("kuro.py", "adb.exe", "AdbWinApi.dll", "AdbWinUsbApi.dll")
foreach ($file in $requiredFiles) {
    if (-not (Test-Path -LiteralPath $file)) {
        throw "Required build file is missing: $file"
    }
}

python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name KuroCommander `
    --version-file version_info.txt `
    --add-binary "adb.exe;." `
    --add-binary "AdbWinApi.dll;." `
    --add-binary "AdbWinUsbApi.dll;." `
    kuro.py

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

Write-Host "Built: $PSScriptRoot\dist\KuroCommander.exe"
