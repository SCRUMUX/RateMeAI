<#
.SYNOPSIS
    Deploy RateMeAI — commit, push, and verify deployment.
.DESCRIPTION
    1. Checks you are on the main branch
    2. Typechecks the frontend (web)
    3. Stages and commits changes (if any)
    4. Pushes to origin/main (triggers CI/CD)
    5. Waits and verifies the API health endpoint
.PARAMETER Message
    Commit message. Required if there are uncommitted changes.
.EXAMPLE
    .\scripts\deploy.ps1 -Message "fix: storage redis fallback"
#>
param(
    [string]$Message = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$API_URL = "https://app-production-6986.up.railway.app"
$HEALTH_RETRIES = 8
$HEALTH_DELAY_SEC = 30

function Write-Step($text) {
    Write-Host "`n=== $text ===" -ForegroundColor Cyan
}

# 1. Check branch
Write-Step "Checking branch"
$branch = git rev-parse --abbrev-ref HEAD
if ($branch -ne "main") {
    Write-Host "ERROR: You are on branch '$branch', not 'main'. Switch first." -ForegroundColor Red
    exit 1
}
Write-Host "On branch: $branch"

# 2. Typecheck frontend
Write-Step "Typechecking frontend"
Push-Location web
try {
    npx tsc --noEmit
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Frontend typecheck failed" -ForegroundColor Red
        exit 1
    }
    Write-Host "Frontend typecheck passed" -ForegroundColor Green
} finally {
    Pop-Location
}

# 3. Check for changes and commit
Write-Step "Checking for changes"
$status = git status --porcelain
if ($status) {
    if (-not $Message) {
        Write-Host "ERROR: There are uncommitted changes but no -Message provided" -ForegroundColor Red
        Write-Host "Usage: .\scripts\deploy.ps1 -Message 'fix: description'" -ForegroundColor Yellow
        git status --short
        exit 1
    }
    Write-Host "Staging and committing..."
    git add -A
    git commit -m $Message
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: git commit failed" -ForegroundColor Red
        exit 1
    }
    Write-Host "Committed: $Message" -ForegroundColor Green
} else {
    Write-Host "No changes to commit"
}

# 4. Push
Write-Step "Pushing to origin/main"
git push origin main
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: git push failed" -ForegroundColor Red
    exit 1
}
Write-Host "Push successful — CI/CD triggered" -ForegroundColor Green

# 5. Wait and verify
Write-Step "Waiting for deployment (CI build + Railway deploy)"
Write-Host "Will check $API_URL/health every ${HEALTH_DELAY_SEC}s, up to $HEALTH_RETRIES times..."

$sha = (git rev-parse HEAD).Substring(0, 12)
Write-Host "Expected commit: $sha"

Start-Sleep -Seconds 60

for ($i = 1; $i -le $HEALTH_RETRIES; $i++) {
    Write-Host "`nAttempt $i/$HEALTH_RETRIES..."
    try {
        $resp = Invoke-RestMethod -Uri "$API_URL/health" -TimeoutSec 10
        Write-Host "  status=$($resp.status) version=$($resp.version) git=$($resp.git)"
        if ($resp.status -eq "ok") {
            Write-Host "`nDeployment verified! API is healthy." -ForegroundColor Green
            Write-Host "  Version: $($resp.version)"
            Write-Host "  Git:     $($resp.git)"
            Write-Host "`nFrontend: https://ailookstudio.vercel.app"
            Write-Host "API:      $API_URL"
            exit 0
        }
    } catch {
        Write-Host "  Health check failed: $_" -ForegroundColor Yellow
    }
    if ($i -lt $HEALTH_RETRIES) {
        Write-Host "  Waiting ${HEALTH_DELAY_SEC}s..."
        Start-Sleep -Seconds $HEALTH_DELAY_SEC
    }
}

Write-Host "`nWARNING: Health check did not confirm deployment after $HEALTH_RETRIES attempts." -ForegroundColor Yellow
Write-Host "Check manually: $API_URL/health"
Write-Host "Railway logs:   https://railway.com/project/abb23754-4c0e-4e96-a2f4-39529bf3b90e"
exit 1
