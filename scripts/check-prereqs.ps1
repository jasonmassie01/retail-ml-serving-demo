param(
  [string]$ProjectId = ""
)

$ErrorActionPreference = "Stop"

function Assert-Command {
  param([string]$Name)

  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
    throw "Required command not found on PATH: $Name"
  }
}

function Resolve-Gcloud {
  $wrapper = Join-Path $HOME "bin\gcloud"
  if (Test-Path $wrapper) {
    return $wrapper
  }
  Assert-Command "gcloud"
  return "gcloud"
}

$gcloud = Resolve-Gcloud
Assert-Command "terraform"
Assert-Command "docker"
Assert-Command "npm"
Assert-Command "python"
Assert-Command "bq"

& $gcloud --version | Out-Host
terraform version | Out-Host
docker version --format "{{.Server.Version}}" | Out-Host
npm --version | Out-Host
python --version | Out-Host

if ($ProjectId) {
  & $gcloud config set project $ProjectId --quiet | Out-Host
}

& $gcloud auth list --filter=status:ACTIVE --format="value(account)" | Out-Host
Write-Host "Prerequisite check complete."
