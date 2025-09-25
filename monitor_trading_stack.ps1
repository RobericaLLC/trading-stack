# Trading Stack Monitoring Script
# Continuously monitors system health during operation

param(
    [int]$IntervalSeconds = 60
)

Write-Host "=== Trading Stack Monitor ===" -ForegroundColor Green
Write-Host "Monitoring interval: $IntervalSeconds seconds" -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop" -ForegroundColor Yellow
Write-Host ""

while ($true) {
    Clear-Host
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "=== Trading Stack Monitor - $timestamp ===" -ForegroundColor Green
    
    # Feed health check
    Write-Host "`n--- Feed Health ---" -ForegroundColor Cyan
    python -m trading_stack.services.feedd.main verify
    
    # Quick bar check
    Write-Host "`n--- Latest Bar Info ---" -ForegroundColor Cyan
    python -c "import pandas as pd, glob; paths = sorted(glob.glob(r'data\live\*\bars1s_SPY.parquet')); df = pd.read_parquet(paths[-1]) if paths else None; print(f'Bars: {len(df)} rows, last: {df.iloc[-1].to_dict()}' if df is not None and not df.empty else 'No bars data')"
    
    # Scorecard summary (key metrics only)
    Write-Host "`n--- Key Metrics ---" -ForegroundColor Cyan
    $scorecard = python -m trading_stack.scorecard.main 2>$null | Out-String
    
    # Extract key metrics
    if ($scorecard -match "llm_freeze_active\s+\│\s+(\w+)\s+\│") {
        $freezeStatus = $matches[1]
        $color = if ($freezeStatus -eq "False") { "Green" } else { "Red" }
        Write-Host "LLM Freeze Active: $freezeStatus" -ForegroundColor $color
    }
    
    if ($scorecard -match "intents_enqueued_last_15m\s+\│\s+(\d+)\s+\│") {
        Write-Host "Intents (15m): $($matches[1])"
    }
    
    if ($scorecard -match "llm_proposals_seen_15m\s+\│\s+(\d+)\s+\│") {
        Write-Host "Proposals (15m): $($matches[1])"
    }
    
    if ($scorecard -match "llm_proposals_applied_15m\s+\│\s+(\d+)\s+\│") {
        Write-Host "Applied (15m): $($matches[1])"
    }
    
    if ($scorecard -match "realized_points_30m\s+\│\s+(\S+)\s+\│") {
        Write-Host "Realized Points (30m): $($matches[1])"
    }
    
    if ($scorecard -match "pnl_drawdown_30m_pct\s+\│\s+(\S+)\s+\│") {
        Write-Host "Drawdown (30m): $($matches[1])"
    }
    
    Write-Host "`nNext update in $IntervalSeconds seconds..." -ForegroundColor Gray
    Start-Sleep -Seconds $IntervalSeconds
}
