param(
    [ValidateSet('setup','start','import','inspect','verify','benchmark','refresh','archive-raw','status','stop','test')]
    [string]$Action = 'status',
    [string]$PythonExecutable,
    [string]$DownloadsDirectory
)
$ErrorActionPreference = 'Stop'
if (-not $PythonExecutable) {
    $configPath = Join-Path $PSScriptRoot '.local\credentials.json'
    if (Test-Path -LiteralPath $configPath) {
        $PythonExecutable = (Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json).python
    } else {
        $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
        if ($pythonCommand) { $PythonExecutable = $pythonCommand.Source }
    }
}
if (-not $PythonExecutable -or -not (Test-Path -LiteralPath $PythonExecutable)) {
    throw 'Provide -PythonExecutable with the full path to Python 3.10 or newer.'
}
$nativeArgs = @((Join-Path $PSScriptRoot 'native.py'), $Action)
if ($DownloadsDirectory) { $nativeArgs += @('--downloads-dir', $DownloadsDirectory) }
& $PythonExecutable @nativeArgs
if ($LASTEXITCODE -ne 0) { throw "CV2 native action failed: $Action" }
