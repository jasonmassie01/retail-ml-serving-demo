param(
  [string]$Mode = "emulator",
  [int]$Port = 8080
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$apiRoot = Join-Path $repoRoot "services\api"

$env:SERVING_MODE = $Mode
$env:PORT = "$Port"
python -m pip install -r (Join-Path $apiRoot "requirements-dev.txt")
python -m uvicorn app.main:app --app-dir $apiRoot --host 127.0.0.1 --port $Port
