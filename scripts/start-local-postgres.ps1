param([int]$Port = 55432, [string]$PostgresBin = 'C:\Program Files\PostgreSQL\17\bin')
$ErrorActionPreference = 'Stop'
$taskRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$runtimeRoot = [IO.Path]::GetFullPath((Join-Path $taskRoot '.runtime'))
$dataRoot = [IO.Path]::GetFullPath((Join-Path $runtimeRoot 'postgres'))
if (-not $dataRoot.StartsWith($taskRoot + [IO.Path]::DirectorySeparatorChar)) { throw 'Invalid runtime path' }
if (-not (Test-Path (Join-Path $PostgresBin 'initdb.exe'))) { throw 'PostgreSQL binaries not found; use Docker Compose instead' }
New-Item -ItemType Directory -Force -Path $runtimeRoot | Out-Null
$envFile = Join-Path $taskRoot 'backend/.env'
if (-not (Test-Path (Join-Path $dataRoot 'PG_VERSION'))) {
    if (Test-Path $envFile) { throw 'Existing backend/.env preserved. Configure a separate cluster explicitly.' }
    $password = [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32)).ToLowerInvariant()
    $passwordFile = Join-Path $runtimeRoot 'postgres-password'
    [IO.File]::WriteAllText($passwordFile, $password)
    & (Join-Path $PostgresBin 'initdb.exe') -D $dataRoot -U meeting --pwfile=$passwordFile --auth-host=scram-sha-256 --auth-local=scram-sha-256 --encoding=UTF8 --no-locale
    if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL initialization failed' }
    $configuration = @(
        "DATABASE_URL=postgresql+psycopg://meeting:${password}@127.0.0.1:${Port}/meeting_to_tasks",
        'APP_ENVIRONMENT=development', 'APP_ORIGIN=http://localhost:5173',
        'PUBLIC_DEMO_MODE=true', 'EMBED_PROVIDER=hash', 'OLLAMA_MODEL='
    ) -join "`n"
    [IO.File]::WriteAllText($envFile, $configuration + "`n")
    Write-Host 'Generated local database credentials in ignored backend/.env.'
}
& (Join-Path $PostgresBin 'pg_ctl.exe') -D $dataRoot status *> $null
if ($LASTEXITCODE -ne 0) {
    & (Join-Path $PostgresBin 'pg_ctl.exe') -D $dataRoot -l (Join-Path $runtimeRoot 'postgres.log') -o "-h 127.0.0.1 -p $Port" -w start
    if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL startup failed; inspect .runtime/postgres.log' }
}
$taskOriginalPassword = $env:PGPASSWORD
$env:PGPASSWORD = [IO.File]::ReadAllText((Join-Path $runtimeRoot 'postgres-password')).Trim()
try {
    $exists = & (Join-Path $PostgresBin 'psql.exe') -h 127.0.0.1 -p $Port -U meeting -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='meeting_to_tasks'"
    if ($LASTEXITCODE -ne 0) { throw 'Could not inspect local database' }
    if ($exists -ne '1') {
        & (Join-Path $PostgresBin 'createdb.exe') -h 127.0.0.1 -p $Port -U meeting meeting_to_tasks
        if ($LASTEXITCODE -ne 0) { throw 'Local database creation failed' }
    }
} finally {
    if ($null -eq $taskOriginalPassword) { Remove-Item Env:PGPASSWORD }
    else { $env:PGPASSWORD = $taskOriginalPassword }
}
Write-Host "Local PostgreSQL is ready on 127.0.0.1:$Port."
