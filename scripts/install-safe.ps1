param([string]$PythonVersion = "3.12", [switch]$SkipDory)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed (exit $LASTEXITCODE)." }
}

Get-Command py -ErrorAction Stop | Out-Null
Get-Command npm.cmd -ErrorAction Stop | Out-Null
if (!(Test-Path ".venv\Scripts\python.exe")) {
    Invoke-Checked "py" @("-$PythonVersion", "-m", "venv", ".venv")
}
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
Invoke-Checked $pythonExe @("-m", "pip", "install", "--upgrade", "pip")
$oldVersion = $env:SETUPTOOLS_SCM_PRETEND_VERSION_FOR_ASREVIEW
try {
    # The fork may not contain upstream's release tags.
    $env:SETUPTOOLS_SCM_PRETEND_VERSION_FOR_ASREVIEW = "3.0.8+safe.1"
    Invoke-Checked $pythonExe @("-m", "pip", "install", "-e", ".")
} finally {
    $env:SETUPTOOLS_SCM_PRETEND_VERSION_FOR_ASREVIEW = $oldVersion
}
if (!$SkipDory) {
    Invoke-Checked $pythonExe @("-m", "pip", "install", "asreview-dory")
}

$oldCypress = $env:CYPRESS_INSTALL_BINARY
$oldHusky = $env:HUSKY
try {
    $env:CYPRESS_INSTALL_BINARY = "0"
    $env:HUSKY = "0"
    Set-Location (Join-Path $repoRoot "asreview\webapp")
    Invoke-Checked "npm.cmd" @("ci", "--no-audit", "--no-fund")
    Invoke-Checked "npm.cmd" @("run", "build")
} finally {
    Set-Location $repoRoot
    $env:CYPRESS_INSTALL_BINARY = $oldCypress
    $env:HUSKY = $oldHusky
}

Write-Host "Installed ASReview with SAFE stopping. Start it with:"
Write-Host '.\.venv\Scripts\asreview.exe lab'
