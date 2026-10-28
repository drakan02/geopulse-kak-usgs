
$ErrorActionPreference = "Stop"

$python = py -3.14 -c "import sys; print(sys.executable)"

$startDate = [datetime]"2023-01-01"
$endDate = [datetime]"2026-04-01"

$channels = @("X", "Y", "Z", "F")
$checkpoint = ".\cv3\results\completed_39_months.txt"

New-Item -ItemType Directory -Force ".\cv3\results" | Out-Null

if (!(Test-Path $checkpoint)) {
    New-Item -ItemType File $checkpoint | Out-Null
}

foreach ($channel in $channels) {
    $current = $startDate

    while ($current -lt $endDate) {
        $next = $current.AddMonths(1)
        $start = $current.ToString("yyyy-MM-dd")
        $end = $next.ToString("yyyy-MM-dd")

        $key = "KAK,$channel,$start,$end"

        if (Select-String -Path $checkpoint -Pattern $key -SimpleMatch -Quiet) {
            Write-Host "SKIP: $key"
            $current = $next
            continue
        }

        Write-Host "Running: $key" -ForegroundColor Cyan

        & $python -m cv3.run_filters `
            --station KAK `
            --channel $channel `
            --start $start `
            --end $end `
            --method all

        if ($LASTEXITCODE -ne 0) {
            Write-Host "FAILED: $key" -ForegroundColor Red
            exit 1
        }

        Add-Content -Path $checkpoint -Value $key
        Write-Host "DONE: $key" -ForegroundColor Green

        $current = $next
    }
}

Write-Host "ALL BATCHES COMPLETED" -ForegroundColor Green
