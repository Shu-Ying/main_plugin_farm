param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('nonebot', 'zhenxun', 'astrbot')]
    [string]$Platform,
    [string]$OutputDirectory
)

$ErrorActionPreference = 'Stop'
$farmProjectRoot = Split-Path -Parent $PSScriptRoot
$farmCandidates = @()
if ($env:FARM_PYTHON) {
    $farmCandidates += @{ Exe = $env:FARM_PYTHON; Prefix = @() }
} else {
    foreach ($farmLocal in @('.venv\Scripts\python.exe',
                              'venv\Scripts\python.exe')) {
        $farmCandidate = Join-Path $farmProjectRoot $farmLocal
        if (Test-Path -LiteralPath $farmCandidate -PathType Leaf) {
            $farmCandidates += @{ Exe = $farmCandidate; Prefix = @() }
        }
    }
    foreach ($farmName in @('python', 'py')) {
        $farmCommand = Get-Command $farmName -ErrorAction SilentlyContinue
        if ($farmCommand) {
            $farmPrefix = @()
            if ($farmName -eq 'py') { $farmPrefix = @('-3') }
            $farmCandidates += @{ Exe = $farmCommand.Source;
                                  Prefix = $farmPrefix }
        }
    }
    if ($env:USERPROFILE) {
        $farmBundled = Join-Path $env:USERPROFILE ('.cache\codex-runtimes\' +
            'codex-primary-runtime\dependencies\python\python.exe')
        if (Test-Path -LiteralPath $farmBundled -PathType Leaf) {
            $farmCandidates += @{ Exe = $farmBundled; Prefix = @() }
        }
    }
}

$farmPython = $null
foreach ($farmCandidate in $farmCandidates) {
    try {
        $farmExe = $farmCandidate.Exe
        $farmPrefix = $farmCandidate.Prefix
        $farmProbe = 'import sys, importlib.util; sys.exit(' +
            'sys.version_info < (3, 10) or ' +
            'importlib.util.find_spec("PIL") is None)'
        # Windows PowerShell 5.1 rewrites quotes in native arguments.
        # Use stdin instead of -c; keep this script ASCII for PS 5.1.
        $farmProbe | & $farmExe @farmPrefix -
        if ($LASTEXITCODE -eq 0) {
            $farmPython = $farmCandidate
            break
        }
    } catch {
        Write-Host ('Python candidate unavailable: ' + $farmCandidate.Exe)
    }
}
if (-not $farmPython) {
    Write-Error ('Python 3.10+ with Pillow not found. ' +
        'Install Python/Pillow or set FARM_PYTHON.')
    exit 1
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    $farmGit = Join-Path $env:USERPROFILE ('.cache\codex-runtimes\' +
        'codex-primary-runtime\dependencies\native\git\cmd')
    if (Test-Path -LiteralPath (Join-Path $farmGit 'git.exe')) {
        $env:PATH = $farmGit + ';' + $env:PATH
    }
}
$farmExe = $farmPython.Exe
$farmArguments = @($farmPython.Prefix) + @(
    (Join-Path $PSScriptRoot 'build_plugin.py'), $Platform
)
if ($OutputDirectory) { $farmArguments += @('--output', $OutputDirectory) }
& $farmExe @farmArguments
exit $LASTEXITCODE
