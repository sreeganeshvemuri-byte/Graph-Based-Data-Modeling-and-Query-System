$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $repoRoot "backend"

Set-Location $backendDir

python -m unittest discover -s "tests" -p "test_*.py"

