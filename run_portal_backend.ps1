param(
    [string]$PythonExe = "python",
    [string]$GrammarTeacherAskUrl = "http://127.0.0.1:8000/ask",
    [string]$GrammarTeacherHealthUrl = "http://127.0.0.1:8000/health",
    [string]$GrammarTeacherApiKey = "",
    [string]$AllowedOrigins = "http://localhost:3000",
    [string]$LogDir = "logs",
    [int]$Port = 8100,
    [switch]$Reload
)

$ErrorActionPreference = "Stop"

Write-Host "Checking Python runtime..."
& $PythonExe -c "import sys, encodings; print(sys.executable)"
if ($LASTEXITCODE -ne 0) {
    throw "The selected Python runtime is broken."
}

$resolvedApiKey = $GrammarTeacherApiKey
if ([string]::IsNullOrWhiteSpace($resolvedApiKey)) {
    $resolvedApiKey = $env:GRAMMAR_TEACHER_API_KEY
}
if ([string]::IsNullOrWhiteSpace($resolvedApiKey)) {
    throw @'
Missing GRAMMAR_TEACHER_API_KEY.

Pass a key directly:
.\run_portal_backend.ps1 -GrammarTeacherApiKey "your-key"
or set:
$env:GRAMMAR_TEACHER_API_KEY = "your-key"
'@
}

$env:GRAMMAR_TEACHER_ASK_URL = $GrammarTeacherAskUrl
$env:GRAMMAR_TEACHER_HEALTH_URL = $GrammarTeacherHealthUrl
$env:GRAMMAR_TEACHER_API_KEY = $resolvedApiKey
$env:PORTAL_ALLOWED_ORIGINS = $AllowedOrigins
$env:PORTAL_LOG_DIR = $LogDir

Write-Host "Starting portal backend at http://0.0.0.0:$Port ..."
if ($Reload) {
    & $PythonExe -m uvicorn portal_backend_template.app:app --host 0.0.0.0 --port $Port --reload
}
else {
    & $PythonExe -m uvicorn portal_backend_template.app:app --host 0.0.0.0 --port $Port
}
