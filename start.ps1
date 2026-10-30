# Запуск «Планирования дня» на Windows PowerShell.
# Использование: .\start.ps1 [-Port 8000] [-NoBrowser]

param(
    [int]$Port = 8000,
    [switch]$NoBrowser
)

Set-Location -LiteralPath $PSScriptRoot

$python = $null
foreach ($candidate in @("python", "py")) {
    $command = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($command) { $python = $command.Source; break }
}

if (-not $python) {
    Write-Host "Python не найден. Установите Python 3.10+ с https://www.python.org/downloads/" -ForegroundColor Red
    exit 1
}

$arguments = @("run.py", "--port", "$Port")
if (-not $NoBrowser) { $arguments += "--open" }

& $python @arguments
