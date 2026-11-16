param([switch]$CaptureMail)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
if ($CaptureMail) {
    # Process-scoped overrides only: the user's real SMTP settings remain in .env.
    $env:SMTP_HOST = 'localhost'
    $env:SMTP_PORT = '1025'
    $env:SMTP_TLS = 'none'
    $env:SMTP_AUTH = 'false'
    $env:SMTP_USER = ''
    $env:SMTP_PASSWORD = ''
    $env:SMTP_FROM = 'TravelMemo <noreply@example.com>'
}
& '.\.venv\Scripts\python.exe' main.py serve
exit $LASTEXITCODE
