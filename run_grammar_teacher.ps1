param(
    [string]$PythonExe = "python",
    [string]$InputDir = ".",
    [string]$BuildDir = "build/grammar_teacher",
    [string]$RunDir = "runs/the-grammar-teacher",
    [string]$Device = "cpu",
    [int]$MaxSteps = 4000,
    [int]$MaxNewTokens = 300,
    [double]$Temperature = 0.6,
    [int]$TopK = 20,
    [string]$Prompt = "A noun is a word that",
    [switch]$Resume
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
.\run_grammar_teacher.ps1 -PythonExe "C:\Path\To\python.exe"
'@
}

$resumeArgs = @()
if ($Resume) {
    # Preserve the previously processed document state for incremental rebuilds.
    $resumeArgs += "--resume"
}

Write-Host "Building The Grammar Teacher knowledge base..."
& $PythonExe -m grammar_teacher.build_knowledge_base --input-dir $InputDir --output-dir $BuildDir @resumeArgs

Write-Host "Training The Grammar Teacher..."
& $PythonExe -m tiny_lm.train --data-dir $BuildDir --out-dir $RunDir --device $Device --max-steps $MaxSteps

Write-Host "Generating a sample response..."
& $PythonExe -m tiny_lm.generate --checkpoint "$RunDir/model.pt" --prompt $Prompt --max-new-tokens $MaxNewTokens --temperature $Temperature --top-k $TopK --device $Device
