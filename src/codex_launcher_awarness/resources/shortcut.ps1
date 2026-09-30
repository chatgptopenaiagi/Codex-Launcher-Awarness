param([Parameter(Mandatory=$true)][string]$Manifest)
$ErrorActionPreference = 'Stop'
$item = Get-Content -LiteralPath $Manifest -Raw -Encoding utf8 | ConvertFrom-Json
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut([string]$item.shortcut)
$shortcut.TargetPath = [string]$item.target
$shortcut.Arguments = [string]$item.arguments
$shortcut.Description = 'Codex Launcher Awarness (experimental)'
$shortcut.Save()
