param(
    [string]$ConfigPath = (Join-Path $PSScriptRoot 'postgres-sync.local.psd1'),
    [switch]$DryRun,
    [int]$MaxWindows = 0,
    [string]$Since = ''
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
$python = Join-Path $repoRoot '.venv-sync\Scripts\python.exe'
$tunnel = $null
$exitCode = 1
try {
    $config = Import-PowerShellDataFile -Path $ConfigPath
    $env:PYTHONPATH = Join-Path $repoRoot 'webapp'
    foreach ($name in @('PGHOST', 'PGPORT', 'PGDATABASE', 'PGUSER', 'PGPASSFILE', 'PGSSLMODE', 'PGSSLROOTCERT', 'QUACK_TOKEN_FILE', 'DUCKDB_EXTENSION_DIRECTORY')) {
        if ($config.ContainsKey($name)) {
            [Environment]::SetEnvironmentVariable($name, [string]$config[$name], 'Process')
        }
    }
    # This wrapper uses explicit PG* settings, not an inherited DSN override.
    Remove-Item Env:SYNC_POSTGRES_DSN -ErrorAction SilentlyContinue
    $logDirectory = Join-Path $repoRoot 'data\sync-logs'
    New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
    $env:FLIGHT_QUACK_URL = $config.FLIGHT_QUACK_URL
    if ($config.SSH_HOST) {
        $port = [int]$config.SSH_LOCAL_PORT
        if ($port -lt 1 -or $port -gt 65535) { throw 'Invalid SSH_LOCAL_PORT' }
        $sshArgs = @('-N', '-T', '-o', 'BatchMode=yes', '-o', 'ExitOnForwardFailure=yes',
            '-o', 'StrictHostKeyChecking=yes', '-o', 'ServerAliveInterval=30',
            '-o', 'ServerAliveCountMax=3', '-L', "127.0.0.1:${port}:127.0.0.1:9494")
        if ($config.SSH_IDENTITY_FILE) { $sshArgs += @('-i', ('"' + $config.SSH_IDENTITY_FILE + '"')) }
        $sshArgs += $config.SSH_HOST
        $tunnel = Start-Process -FilePath 'ssh.exe' -ArgumentList $sshArgs -PassThru -WindowStyle Hidden `
            -RedirectStandardError (Join-Path $logDirectory 'ssh-error.log') `
            -RedirectStandardOutput (Join-Path $logDirectory 'ssh-output.log')
        $ready = $false
        for ($attempt = 0; $attempt -lt 40; $attempt++) {
            if ($tunnel.HasExited) { throw 'SSH tunnel failed; see data\sync-logs\ssh-error.log' }
            $probe = New-Object System.Net.Sockets.TcpClient
            try { $probe.Connect('127.0.0.1', $port); $ready = $true } catch {} finally { $probe.Dispose() }
            if ($ready) { break }
            Start-Sleep -Milliseconds 250
        }
        if (-not $ready) { throw 'SSH tunnel did not become ready' }
        $env:FLIGHT_QUACK_URL = "quack:127.0.0.1:$port"
    }
    $syncArgs = @('-m', 'webapp.data.sync_flights', '--log-file', (Join-Path $logDirectory 'sync.log'))
    if ($config.WINDOW_DAYS) { $syncArgs += @('--window-days', [string]$config.WINDOW_DAYS) }
    if ($DryRun) { $syncArgs += '--dry-run' }
    if ($MaxWindows -gt 0) { $syncArgs += @('--max-windows', [string]$MaxWindows) }
    if ($Since) { $syncArgs += @('--since', $Since) }
    & $python @syncArgs
    $exitCode = $LASTEXITCODE
} catch {
    Write-Error -Message $_.Exception.Message -ErrorAction Continue
} finally {
    if ($tunnel -and -not $tunnel.HasExited) { Stop-Process -Id $tunnel.Id -ErrorAction SilentlyContinue }
}
exit $exitCode
