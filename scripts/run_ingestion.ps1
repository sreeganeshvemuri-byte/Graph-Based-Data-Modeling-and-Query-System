param(
  [Parameter(Mandatory=$true)]
  [string]$DatasetRoot,

  [switch]$BuildEdges,

  [ValidateSet("DEBUG","INFO","WARNING","ERROR")]
  [string]$LogLevel = "INFO"
)

$ErrorActionPreference = "Stop"

$backendDir = Join-Path $PSScriptRoot "..\\backend"
Set-Location $backendDir

$logFile = Join-Path $backendDir "..\\data\\ingestion.log"
if (Test-Path $logFile) { Remove-Item -Force $logFile }

& python -m app.ingestion.cli $DatasetRoot --log-level $LogLevel @(if ($BuildEdges) { "--build-edges" } else { @() })

