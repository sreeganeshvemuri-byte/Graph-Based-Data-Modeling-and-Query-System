param(
  [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

$backendDir = Join-Path $PSScriptRoot "..\backend"
Set-Location $backendDir

& uvicorn app.main:app --reload --port $Port

