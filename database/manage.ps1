param(
    [ValidateSet('start','import','inspect','verify','benchmark','refresh','archive-raw','status','stop','test')]
    [string]$Action = 'status'
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Docker is not available. Use windows-native.ps1 on Windows, or install/open Docker Desktop.'
}
if (-not (Test-Path -LiteralPath '.env')) {
    $adminPassword = [Guid]::NewGuid().ToString('N') + [Guid]::NewGuid().ToString('N')
    $readerPassword = [Guid]::NewGuid().ToString('N') + [Guid]::NewGuid().ToString('N')
    @("POSTGRES_DB=geopulse", "POSTGRES_USER=geopulse", "POSTGRES_PASSWORD=$adminPassword",
      'POSTGRES_PORT=5433', "PG_READER_PASSWORD=$readerPassword", 'TIMESCALE_IMAGE=timescale/timescaledb:2.30.2-pg17') |
      Set-Content -LiteralPath '.env' -Encoding utf8
    Write-Host 'Created local credentials in database/.env (ignored by Git).'
}
switch ($Action) {
    'start' {
        & docker compose up -d --wait db
        if ($LASTEXITCODE -ne 0) { throw 'Database failed to start.' }
        & docker compose run --rm --build tools init
    }
    'status' { & docker compose ps }
    'stop' { & docker compose stop db }
    'verify' { & docker compose run --rm --build tools verify --full }
    default { & docker compose run --rm --build tools $Action }
}
if ($LASTEXITCODE -ne 0) { throw "CV2 action failed: $Action" }
