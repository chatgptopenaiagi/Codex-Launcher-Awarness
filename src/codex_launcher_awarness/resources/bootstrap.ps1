param([Parameter(Mandatory=$true)][string]$Manifest)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$PSNativeCommandArgumentPassing = 'Standard'
$launch = $null
function Write-CLAStatus([string]$State, [Nullable[int]]$Code = $null, [string]$Reason = '') {
    if ($null -eq $launch) { return }
    $status = @{ session_id = $launch.session_id; project = $launch.project; status = $State;
                 terminal_pid = $PID; at = [DateTime]::UtcNow.ToString('o'); exit_code = $Code; reason = $Reason }
    $temporary = $launch.status_path + '.tmp'
    $status | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $temporary -Encoding utf8
    [IO.File]::Replace($temporary, $launch.status_path, [NullString]::Value)
}
try {
    $launch = Get-Content -LiteralPath $Manifest -Raw -Encoding utf8 | ConvertFrom-Json
    if ($launch.schema_version -ne '1.0') { throw 'Unsupported CLA launch schema.' }
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    if ($principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator) -and -not $launch.allow_elevated) {
        throw 'CLA refuses an elevated Codex terminal. Open CLA without Run as administrator.'
    }
    if ($launch.allow_elevated -and $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        Write-Warning 'Explicit administrator-token inheritance: this Codex terminal has administrator rights.'
    }
    if (-not (Test-Path -LiteralPath $launch.project -PathType Container)) { throw 'Project directory no longer exists.' }
    if (-not (Test-Path -LiteralPath $launch.codex_path -PathType Leaf)) { throw 'Selected Codex executable no longer exists.' }
    if ([IO.Path]::GetExtension($launch.codex_path) -notin @('.exe', '.ps1')) { throw 'Unsafe executable wrapper type.' }
    Set-Location -LiteralPath $launch.project
    if ($null -ne $launch.conda) {
        if (-not (Test-Path -LiteralPath $launch.conda.hook -PathType Leaf)) { throw 'Trusted Conda hook missing.' }
        # Only reviewed installation-owned code is sourced. User values remain argument data.
        . $launch.conda.hook
        conda activate ([string]$launch.conda.environment)
        if (-not $?) { throw 'Conda activation failed.' }
    }
    Write-CLAStatus 'codex_starting'
    [string[]]$codexArguments = @($launch.codex_args | ForEach-Object { [string]$_ })
    & $launch.codex_path @codexArguments
    $code = $LASTEXITCODE
    if ($null -eq $code) { $code = 0 }
    if ($code -eq 0) { Write-CLAStatus 'codex_exited' $code }
    else { Write-CLAStatus 'failed' $code 'codex_nonzero_exit' }
    Write-Host ('CLA: Codex exited with code ' + $code + '. This PowerShell session remains open.')
} catch {
    Write-CLAStatus 'failed' 1 'launch_failed_see_terminal'
    Write-Error ('CLA launch failed: ' + $_.Exception.Message) -ErrorAction Continue
}
