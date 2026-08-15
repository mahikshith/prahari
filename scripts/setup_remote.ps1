<#
.SYNOPSIS
    One-time: authenticate to GitHub, create a PRIVATE repo, push.

.DESCRIPTION
    Run this yourself - it needs an interactive browser login, which is why it was
    not done for you.

    The repo is created PRIVATE and stays private. It contains the incident narrative,
    the competitive analysis, and the go-to-market strategy. Do not flip it public
    without re-reading gtm/case-study-incident.md and resolving ASSUMPTIONS.md A2
    (the employer IP / data-use position).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\setup_remote.ps1
    powershell -ExecutionPolicy Bypass -File scripts\setup_remote.ps1 -RepoName prahari-ai
#>
param(
    [string]$RepoName = "prahari",
    [string]$Description = "AI spend control plane - cross-provider cost visibility with sub-hour credential-abuse detection"
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

Write-Host "`n=== Prahari: GitHub remote setup ===`n" -ForegroundColor Cyan

# --- gh present? ---
$gh = Get-Command gh -ErrorAction SilentlyContinue
if (-not $gh) {
    $candidate = "$env:ProgramFiles\GitHub CLI\gh.exe"
    if (Test-Path $candidate) {
        $env:Path = "$env:ProgramFiles\GitHub CLI;$env:Path"
    } else {
        Write-Host "GitHub CLI not found. Install it with:" -ForegroundColor Yellow
        Write-Host "    winget install --id GitHub.cli`n"
        Write-Host "Then open a NEW terminal and run this script again."
        exit 1
    }
}
Write-Host "gh found: $((gh --version) -split "`n" | Select-Object -First 1)"

# --- authenticated? ---
gh auth status 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "`nNot authenticated. Launching browser login..." -ForegroundColor Yellow
    gh auth login --hostname github.com --git-protocol https --web
    if ($LASTEXITCODE -ne 0) { Write-Host "Login failed." -ForegroundColor Red; exit 1 }
}
$who = gh api user --jq .login
Write-Host "Authenticated as: $who"

# --- safety: nothing uncommitted, no secrets staged ---
$dirty = git status --porcelain
if ($dirty) {
    Write-Host "`nUncommitted changes present:" -ForegroundColor Yellow
    git status --short
    Write-Host "`nCommit or stash them first, then re-run." -ForegroundColor Yellow
    exit 1
}

if (git ls-files | Select-String -Pattern '(^|/)\.env$' -Quiet) {
    Write-Host "`nREFUSING TO PUSH: .env is tracked by git." -ForegroundColor Red
    Write-Host "Remove it with: git rm --cached .env"
    exit 1
}

# --- create (idempotent) ---
$existing = gh repo view "$who/$RepoName" --json name 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "`nRepo $who/$RepoName already exists - reusing it."
    $visibility = gh repo view "$who/$RepoName" --json visibility --jq .visibility
    if ($visibility -ne "PRIVATE") {
        Write-Host "WARNING: existing repo is $visibility, not PRIVATE." -ForegroundColor Red
        Write-Host "It holds the incident narrative and GTM strategy. Aborting."
        exit 1
    }
} else {
    Write-Host "`nCreating PRIVATE repo $who/$RepoName ..."
    gh repo create $RepoName --private --description $Description --source . --remote origin
    if ($LASTEXITCODE -ne 0) { Write-Host "Create failed." -ForegroundColor Red; exit 1 }
}

if (-not (git remote | Select-String -Pattern '^origin$' -Quiet)) {
    git remote add origin "https://github.com/$who/$RepoName.git"
}

# --- push ---
Write-Host "`nPushing main ..."
git push -u origin main
if ($LASTEXITCODE -ne 0) { Write-Host "Push failed." -ForegroundColor Red; exit 1 }

Write-Host "`nDone: https://github.com/$who/$RepoName" -ForegroundColor Green
Write-Host "Private. Keep it that way until ASSUMPTIONS.md A2 is resolved.`n"
