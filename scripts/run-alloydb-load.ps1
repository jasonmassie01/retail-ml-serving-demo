param(
  [Parameter(Mandatory = $true)]
  [string]$ProjectId,
  [string]$Region = "us-central1",
  [string]$JobName = "retail-alloydb-loader"
)

$ErrorActionPreference = "Stop"

& "$HOME\bin\gcloud" run jobs execute $JobName `
  --project $ProjectId `
  --region $Region `
  --wait `
  --quiet
