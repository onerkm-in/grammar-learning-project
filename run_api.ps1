param(
    [string]$PythonExe = "python",
    [string]$IndexPath = "build/grammar_teacher/chunks.jsonl",
    [string]$ApiKey = "",
    [int]$RateLimitPerMinute = 60,
    [string]$LogDir = "logs",
    [string]$Host = "0.0.0.0",
    [int]$Port = 8000,
    [switch]$Reload
)

$ErrorActionPreference = "Stop"

Write-Host "Checking Python runtime..."
& $PythonExe -c "import sys, encodings; print(sys.executable)"
if ($LASTEXITCODE -ne 0) {
    throw @'
The selected Python runtime is broken or points to an incomplete embedded install.

Common fix:
1. Remove the current .venv
2. Install a normal Python from python.org
3. Recreate the virtual environment

If you already have multiple Python installations, pass a known-good interpreter:
.\run_api.ps1 -PythonExe "C:\Path\To\python.exe"
'@
}

if (!(Test-Path $IndexPath)) {
    throw "Index file not found: $IndexPath. Build the knowledge base first."
}

$resolvedApiKey = $ApiKey
if ([string]::IsNullOrWhiteSpace($resolvedApiKey)) {
    $resolvedApiKey = $env:GRAMMAR_TEACHER_API_KEY
}
if ([string]::IsNullOrWhiteSpace($resolvedApiKey)) {
    throw @'
Missing API key.

Provide one of these:
.\run_api.ps1 -ApiKey "your-strong-key"
or set env var:
$env:GRAMMAR_TEACHER_API_KEY = "your-strong-key"
'@
}

$env:GRAMMAR_TEACHER_INDEX = $IndexPath
$env:GRAMMAR_TEACHER_API_KEY = $resolvedApiKey
$env:GRAMMAR_TEACHER_RATE_LIMIT_PER_MINUTE = "$RateLimitPerMinute"
$env:GRAMMAR_TEACHER_LOG_DIR = $LogDir

Write-Host "Starting The Grammar Teacher API at http://${Host}:${Port} ..."
if ($Reload) {
    & $PythonExe -m uvicorn grammar_teacher.api_server:app --host $Host --port $Port --reload
}
else {
    & $PythonExe -m uvicorn grammar_teacher.api_server:app --host $Host --port $Port
}
