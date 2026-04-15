param(
    [string]$PythonExe = "python",
    [string]$InputDir = ".",
    [string]$DataDir = "data",
    [string]$RunDir = "runs/grammar-small",
    [string]$Prompt = "Nouns are",
    [string]$Device = "cpu",
    [int]$MaxSteps = 3000,
    [int]$MaxNewTokens = 300
)

$ErrorActionPreference = "Stop"

Write-Host "Checking Python runtime..."
# Fail early if the selected interpreter is still the broken embedded one.
& $PythonExe -c "import sys, encodings; print(sys.executable)"
if ($LASTEXITCODE -ne 0) {
    throw @'
The selected Python runtime is broken or points to an incomplete embedded install.

Common fix:
1. Remove the current .venv
2. Install a normal Python from python.org
3. Recreate the virtual environment

If you already have multiple Python installations, pass a known-good interpreter:
.\run_pipeline.ps1 -PythonExe "C:\Path\To\python.exe"
'@
}

Write-Host "Preparing corpus..."
& $PythonExe -m tiny_lm.prepare_data --input-dir $InputDir --output-dir $DataDir

Write-Host "Training model..."
& $PythonExe -m tiny_lm.train --data-dir $DataDir --out-dir $RunDir --device $Device --max-steps $MaxSteps

Write-Host "Generating sample text..."
& $PythonExe -m tiny_lm.generate --checkpoint "$RunDir/model.pt" --prompt $Prompt --max-new-tokens $MaxNewTokens --device $Device
