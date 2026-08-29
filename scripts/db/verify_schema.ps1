<#
.SYNOPSIS
    Structural verification of the applied schema: table/view/constraint/index counts, every
    view actually EXECUTED (not just parsed), and a presence check against the same
    REQUIRED_TABLES list pipelines/common/db.py --check-schema-files scans for.

.DESCRIPTION
    Run after apply_migrations.ps1. Exits non-zero if any REQUIRED_TABLES entry is missing --
    every other section is informational, printed for eyeball comparison against the P0
    validation report's numbers (27 tables, 4 views, 27 PKs, 26 FKs, 65 CHECKs, 6 UNIQUEs,
    63 indexes).
#>

$ErrorActionPreference = "Stop"

$Container = "datn_pg"
$DbUser    = "datn"
$DbName    = "datn"
$SqlFile   = Join-Path $PSScriptRoot "verify_schema.sql"

Write-Host "== Verifying schema in $Container ==" -ForegroundColor Cyan

$Output = Get-Content -Raw $SqlFile | docker exec -i $Container psql -U $DbUser -d $DbName
if ($LASTEXITCODE -ne 0) {
    Write-Host $Output
    throw "verify_schema.sql failed to run -- see output above (a view that fails to execute lands here)"
}

Write-Host $Output

# The last \echo block lists missing required tables, one per row, under the header
# "missing_table". psql prints "(0 rows)" when the set is empty; anything else is a failure.
if ($Output -match "\(0 rows\)\s*$") {
    Write-Host "`n== All REQUIRED_TABLES present. ==" -ForegroundColor Green
    exit 0
} else {
    Write-Host "`n== Some REQUIRED_TABLES are MISSING -- see 'missing_table' rows above. ==" -ForegroundColor Red
    exit 1
}
