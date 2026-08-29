<#
.SYNOPSIS
    Bring up the named local Postgres container and apply the nine baseline migrations, in order,
    under ON_ERROR_STOP. Idempotent: re-running against an already-migrated database fails loudly
    on the first CREATE that collides, which is the correct behaviour for a migration runner that
    has no down-migrations.

.DESCRIPTION
    Repeats the P0 procedure (apply to a real server, ON_ERROR_STOP, non-recursive glob so
    supabase/migrations/_archive/ is never touched) against the named container from
    compose.db.yml instead of a throwaway one. See scripts/db/compose.db.yml for why.
#>

$ErrorActionPreference = "Stop"

$RepoRoot   = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$ComposeYml = Join-Path $PSScriptRoot "compose.db.yml"
$Container  = "datn_pg"
$DbUser     = "datn"
$DbName     = "datn"

Write-Host "== Starting $Container (docker compose) ==" -ForegroundColor Cyan
docker compose -f $ComposeYml up -d
if ($LASTEXITCODE -ne 0) { throw "docker compose up failed" }

Write-Host "== Waiting for healthy ==" -ForegroundColor Cyan
$deadline = (Get-Date).AddSeconds(60)
while ($true) {
    $status = docker inspect --format='{{.State.Health.Status}}' $Container 2>$null
    if ($status -eq "healthy") { break }
    if ((Get-Date) -gt $deadline) { throw "$Container did not become healthy within 60s" }
    Start-Sleep -Seconds 1
}
Write-Host "$Container is healthy." -ForegroundColor Green

$MigrationsDir = Join-Path $RepoRoot "supabase\migrations"
# Get-ChildItem without -Recurse: supabase/migrations/_archive/ (the superseded pre-anchor set)
# is a subdirectory and is therefore never picked up, matching the P0 procedure's own note.
$Files = Get-ChildItem -Path $MigrationsDir -Filter "*.sql" -File | Sort-Object Name

if ($Files.Count -eq 0) { throw "no *.sql files found directly under $MigrationsDir" }

Write-Host "== Applying $($Files.Count) migrations ==" -ForegroundColor Cyan
foreach ($f in $Files) {
    Write-Host "  -> $($f.Name)"
    docker exec $Container psql -v ON_ERROR_STOP=1 -U $DbUser -d $DbName `
        -f "/migrations/$($f.Name)"
    if ($LASTEXITCODE -ne 0) {
        throw "migration $($f.Name) failed (see psql output above) -- database is in a partial state"
    }
}

Write-Host "== All $($Files.Count) migrations applied cleanly. ==" -ForegroundColor Green
Write-Host "Connection string: postgresql://${DbUser}:datn_local_dev@localhost:55432/${DbName}"
