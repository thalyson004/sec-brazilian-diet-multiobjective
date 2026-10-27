[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Pof,
    [Parameter(Mandatory=$true)][string]$Footprints,
    [string]$OutputDir = "",
    [ValidateRange(1,8)][int]$Workers = 4,
    [int]$Evaluations = 16500,
    [int]$Replicates = 20,
    [switch]$PrepareOnly,
    [switch]$AnalyzeOnly,
    [switch]$Resume,
    [switch]$Penalty,
    [switch]$NoPenalty,
    [Nullable[double]]$PenaltyWeight
)
$ErrorActionPreference = "Stop"
$studyRoot = $PSScriptRoot
$studyPython = Join-Path $studyRoot ".venv\Scripts\python.exe"
function Invoke-StudyNative {
    param([string]$Executable, [string[]]$Arguments)
    # Windows PowerShell represents native stderr as error records. Notices and
    # warnings do not determine success: preserve output and check the exit code.
    $studySavedPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & $Executable @Arguments
        $studyExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $studySavedPreference
    }
    if ($studyExitCode -ne 0) {
        throw "Study command ended with exit code $studyExitCode. See the retained output."
    }
}
if (-not (Test-Path -LiteralPath $studyPython)) {
    Invoke-StudyNative -Executable "python" -Arguments @("-m", "venv", (Join-Path $studyRoot ".venv"))
}
Invoke-StudyNative -Executable $studyPython -Arguments @("-m", "pip", "install", "-e", "${studyRoot}[experiment,figures]")
$studyArguments = @((Join-Path $studyRoot "scripts\run_profile_study.py"), "--pof", $Pof,
    "--footprints", $Footprints, "--workers", "$Workers", "--evaluations", "$Evaluations", "--replicates", "$Replicates")
if ($OutputDir) { $studyArguments += @("--output-dir", $OutputDir) }
if ($PrepareOnly) { $studyArguments += "--prepare-only" }
if ($AnalyzeOnly) { $studyArguments += "--analyze-only" }
if ($Resume) { $studyArguments += "--resume" }
if ($Penalty) { $studyArguments += "--penalty" }
if ($NoPenalty) { $studyArguments += "--no-penalty" }
if ($null -ne $PenaltyWeight) { $studyArguments += @("--penalty-weight", "$PenaltyWeight") }
Invoke-StudyNative -Executable $studyPython -Arguments $studyArguments
