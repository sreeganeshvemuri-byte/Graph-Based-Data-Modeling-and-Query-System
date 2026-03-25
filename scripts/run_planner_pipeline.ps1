param(
  [Parameter(Mandatory=$true)]
  [string]$UserInput
)

$ErrorActionPreference = "Stop"

$backendDir = Join-Path $PSScriptRoot "..\backend"
Set-Location $backendDir

$inputJson = ($UserInput | ConvertTo-Json -Compress)
$env:INPUT_JSON = $inputJson

python -c "import os, json; from app.db.session import init_db, SessionLocal; from app.query.execute import execute_user_input; init_db(); user_input=json.loads(os.environ['INPUT_JSON']); s=SessionLocal(); res=execute_user_input(s, user_input); s.close(); print(json.dumps(res, ensure_ascii=False, indent=2))"

