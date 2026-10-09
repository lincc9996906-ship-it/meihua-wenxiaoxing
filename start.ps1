$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$localPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$previewPython = Join-Path $PSScriptRoot '..\..\work\python-web\python.exe'
if (Test-Path -LiteralPath $localPython) {
    $appPython = $localPython
} elseif (Test-Path -LiteralPath $previewPython) {
    $appPython = (Resolve-Path -LiteralPath $previewPython).Path
} else {
    $launcher = Get-Command python -ErrorAction SilentlyContinue
    if (-not $launcher) { throw 'Python was not found. Install Python 3.12 and add it to PATH.' }
    & $launcher.Source -m venv (Join-Path $PSScriptRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
    $appPython = $localPython
}
& $appPython -c "import streamlit, requests, lunardate; assert streamlit.__version__ == '1.65.0'; assert hasattr(lunardate.LunarDate, 'fromSolarDate')"
if ($LASTEXITCODE -ne 0) {
    & $appPython -m pip install -r (Join-Path $PSScriptRoot 'requirements.txt') --disable-pip-version-check
    if ($LASTEXITCODE -ne 0) { throw 'Dependencies could not be installed. Check the network and try again.' }
}
Write-Host 'Opening Wenxiaoxing at http://localhost:8501 . Keep this window open. Ctrl+C stops the server.'
& $appPython -m streamlit run (Join-Path $PSScriptRoot 'app.py') --server.address=127.0.0.1 --server.port=8501 --server.headless=false
