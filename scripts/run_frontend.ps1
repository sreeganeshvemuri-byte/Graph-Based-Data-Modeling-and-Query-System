$ErrorActionPreference = "Stop"

$frontendDir = Join-Path $PSScriptRoot "..\frontend"
Set-Location $frontendDir

# Requires Node.js + npm to be installed locally.
# Run `npm install` once before the first `npm run dev`.
& npm run dev

