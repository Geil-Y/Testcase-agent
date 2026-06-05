# Start Pipeline Console (backend + frontend)
# Usage: .\start.ps1

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Pipeline Console" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Backend
Write-Host "[backend] Starting FastAPI on http://localhost:8000 ..." -ForegroundColor Green
$backend = Start-Process -FilePath "python" -ArgumentList "-m", "uvicorn", "testcase_agent.api:app", "--port", "8000", "--reload" -NoNewWindow -PassThru

# Frontend
Write-Host "[frontend] Starting Vite on http://localhost:5173 ..." -ForegroundColor Green
$frontend = Start-Process -FilePath "npm" -ArgumentList "run", "dev" -WorkingDirectory "$PSScriptRoot\console-ui" -NoNewWindow -PassThru

Write-Host ""
Write-Host "----------------------------------------" -ForegroundColor Cyan
Write-Host "  UI:  http://localhost:5173" -ForegroundColor Yellow
Write-Host "  API: http://localhost:8000/api/v1/health" -ForegroundColor Yellow
Write-Host "----------------------------------------" -ForegroundColor Cyan
Write-Host ""
Write-Host "Press Ctrl+C to stop both servers..." -ForegroundColor Gray

# Trap Ctrl+C to clean up
try {
    while ($true) { Start-Sleep -Seconds 1 }
}
finally {
    Write-Host "`nShutting down..." -ForegroundColor Red
    if (!$backend.HasExited) { Stop-Process -Id $backend.Id -Force }
    if (!$frontend.HasExited) { Stop-Process -Id $frontend.Id -Force }
    Write-Host "Done." -ForegroundColor Red
}
