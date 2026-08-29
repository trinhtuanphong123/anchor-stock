<#
.SYNOPSIS
    Structural verification of the applied schema: table/view/constraint/index counts, every
    view actually EXECUTED (not just parsed), and a presence check against the same
    REQUIRED_TABLES list pipelines/common/db.py --check-schema-files scans for.

.DESCRIPTION
    Run after apply_migrations.ps1. Exits non-zero if the final gate block returns any row --
    a required relation missing, or a table P15 withdrew still present. Every other section is
    informational, printed for eyeball comparison.

    Reference counts are P15's, measured 2026-08-30 against a freshly migrated database:
    17 base tables (16 public + 1 staging), 13 views, 17 PKs, 14 FKs, 46 CHECKs, 5 UNIQUEs,
    44 indexes.
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

# The gate is the LAST result set in verify_schema.sql, and this reads it positionally: psql
# prints "(0 rows)" for an empty set, so the whole output ending in "(0 rows)" means the gate
# passed. A query appended after the gate in the .sql would take its place here silently, which
# is why that file folds both of its checks into one block and says so.
if ($Output -match "\(0 rows\)\s*$") {
    Write-Host "`n== Schema gate passed: required relations present, withdrawn tables absent. ==" -ForegroundColor Green
    exit 0
} else {
    Write-Host "`n== Schema gate FAILED -- see the 'problem'/'relation' rows above. ==" -ForegroundColor Red
    exit 1
}
