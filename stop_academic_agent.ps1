$patterns = @(
    'paper_analyzer.server',
    'vite.js.*5173',
    '文献追踪助手-1\\frontend'
)

Write-Host ""
Write-Host "[Academic Agent] Stopping project backend/frontend processes..."

$processes = Get-CimInstance Win32_Process | Where-Object {
    if ($_.Name -notmatch 'python|node') {
        return $false
    }

    $commandLine = $_.CommandLine
    if (-not $commandLine) {
        return $false
    }

    foreach ($pattern in $patterns) {
        if ($commandLine -match $pattern) {
            return $true
        }
    }

    return $false
}

if (-not $processes) {
    Write-Host "No matching processes found."
    exit 0
}

foreach ($process in $processes) {
    try {
        Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop
        Write-Host ("Stopped PID " + $process.ProcessId)
    }
    catch {
        Write-Host ("Failed PID " + $process.ProcessId)
    }
}

Write-Host "Done."
