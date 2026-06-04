param(
  [Parameter(Mandatory = $true)]
  [string]$ProjectId,
  [string]$Region = "us-central1",
  [string]$Zone = "us-central1-b",
  [string]$BqLocation = "US",
  [string]$VertexRankingEndpoint = "",
  [string]$VertexPricingEndpoint = "",
  [string]$VertexCouponEndpoint = "",
  [switch]$SkipSql,
  [switch]$SkipSecondApply
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$tfRoot = Join-Path $repoRoot "infra\terraform"
$checkScript = Join-Path $repoRoot "scripts\check-prereqs.ps1"
$runSqlScript = Join-Path $repoRoot "scripts\run-sql.ps1"

& $checkScript -ProjectId $ProjectId

if (-not $env:TF_VAR_alloydb_password) {
  $chars = (48..57) + (65..90) + (97..122)
  $password = -join ($chars | Get-Random -Count 32 | ForEach-Object { [char]$_ })
  $env:TF_VAR_alloydb_password = $password
}

$image = "$Region-docker.pkg.dev/$ProjectId/retail-ml-demo/api:latest"
$terraformVars = @(
  "-var=project_id=$ProjectId",
  "-var=region=$Region",
  "-var=zone=$Zone",
  "-var=bq_location=$BqLocation",
  "-var=vertex_ranking_endpoint=$VertexRankingEndpoint",
  "-var=vertex_pricing_endpoint=$VertexPricingEndpoint",
  "-var=vertex_coupon_endpoint=$VertexCouponEndpoint"
)

terraform -chdir="$tfRoot" init
terraform -chdir="$tfRoot" apply -auto-approve @terraformVars

& "$HOME\bin\gcloud" auth configure-docker "$Region-docker.pkg.dev" --quiet
docker build -f (Join-Path $repoRoot "services\api\Dockerfile") -t $image $repoRoot
docker push $image

if (-not $SkipSecondApply) {
  terraform -chdir="$tfRoot" apply -auto-approve @terraformVars "-var=api_image=$image"
}

if (-not $SkipSql) {
  & $runSqlScript `
    -ProjectId $ProjectId `
    -Dataset "retail_demo" `
    -Region $Region `
    -BqLocation $BqLocation `
    -BigtableInstance "retail-features" `
    -BigtableAppProfile "serving" `
    -BigtableTable "online_features"
}

terraform -chdir="$tfRoot" output
