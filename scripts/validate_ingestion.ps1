$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $repoRoot "backend"

Set-Location $backendDir

param(
  [string]$SalesOrder,
  [string]$BillingDocument,
  [int]$GraphDepth = 2
)

$args = @()
if ($SalesOrder) { $args += "--sales-order"; $args += $SalesOrder }
if ($BillingDocument) { $args += "--billing-document"; $args += $BillingDocument }
$args += "--graph-depth"; $args += $GraphDepth

& python -m app.ingestion.validate @args

