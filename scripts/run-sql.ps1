param(
  [Parameter(Mandatory = $true)]
  [string]$ProjectId,
  [string]$Dataset = "retail_demo",
  [string]$Region = "us-central1",
  [string]$BqLocation = "US",
  [string]$BqConnectionId = "vertex_conn",
  [string]$BigtableInstance = "retail-features",
  [string]$BigtableAppProfile = "serving",
  [string]$BigtableTable = "online_features",
  [switch]$StartContinuousQuery,
  [string]$ContinuousQueryServiceAccount = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$sqlRoot = Join-Path $repoRoot "infra\sql"

function Render-Sql {
  param([string]$Path)

  $sql = Get-Content -Path $Path -Raw
  $sql = $sql.Replace("@PROJECT_ID@", $ProjectId)
  $sql = $sql.Replace("@DATASET@", $Dataset)
  $sql = $sql.Replace("@REGION@", $Region)
  $sql = $sql.Replace("@BQ_LOCATION@", $BqLocation)
  $sql = $sql.Replace("@BQ_CONNECTION_ID@", $BqConnectionId)
  $sql = $sql.Replace("@BT_INSTANCE@", $BigtableInstance)
  $sql = $sql.Replace("@BT_APP_PROFILE@", $BigtableAppProfile)
  $sql = $sql.Replace("@BT_TABLE@", $BigtableTable)
  $btUri = "https://bigtable.googleapis.com/projects/$ProjectId"
  $btUri += "/instances/$BigtableInstance/appProfiles/$BigtableAppProfile"
  $btUri += "/tables/$BigtableTable"
  $sql = $sql.Replace("@BT_URI@", $btUri)
  return $sql
}

function Invoke-BqQuery {
  param(
    [string]$Path,
    [switch]$Continuous
  )

  $rendered = Render-Sql -Path $Path
  $temp = New-TemporaryFile
  Set-Content -Path $temp -Value $rendered -NoNewline
  try {
    $args = @(
      "query",
      "--project_id=$ProjectId",
      "--location=$BqLocation",
      "--use_legacy_sql=false"
    )
    if ($Continuous) {
      if (-not $ContinuousQueryServiceAccount) {
        throw "Continuous queries require -ContinuousQueryServiceAccount."
      }
      $args += "--continuous=true"
      $args += "--connection_property=service_account=$ContinuousQueryServiceAccount"
    }
    $args += "$(Get-Content -Path $temp -Raw)"
    Write-Host "Running BigQuery SQL: $(Split-Path -Leaf $Path)"
    & bq @args | Out-Host
  }
  finally {
    Remove-Item -LiteralPath $temp -Force
  }
}

$batchFiles = @(
  "00_data_foundation.sql",
  "01_content_and_embeddings.sql",
  "02_feature_engineering.sql",
  "04_bigtable_reverse_etl.sql",
  "06_training_examples.sql"
)

foreach ($file in $batchFiles) {
  Invoke-BqQuery -Path (Join-Path $sqlRoot $file)
}

if ($StartContinuousQuery) {
  Invoke-BqQuery -Path (Join-Path $sqlRoot "05_continuous_bigtable_features.sql") -Continuous
}
