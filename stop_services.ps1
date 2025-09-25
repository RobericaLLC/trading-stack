# PowerShell script to stop all trading stack services
Write-Host "Stopping Trading Stack Services..." -ForegroundColor Yellow

# Stop all Python processes running our services
$services = @(
    "trading_stack.services.feedd.main",
    "trading_stack.services.engined.live",
    "trading_stack.services.advisor.main", 
    "trading_stack.services.controller.apply_params",
    "trading_stack.services.execd.worker"
)

foreach ($service in $services) {
    $processes = Get-Process python* -ErrorAction SilentlyContinue | 
        Where-Object { $_.CommandLine -like "*$service*" }
    
    if ($processes) {
        foreach ($proc in $processes) {
            Write-Host "Stopping $service (PID: $($proc.Id))..." -ForegroundColor Red
            Stop-Process -Id $proc.Id -Force
        }
    }
}

Write-Host "`nAll services stopped!" -ForegroundColor Green
