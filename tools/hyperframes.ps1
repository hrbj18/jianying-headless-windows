param(
    [Parameter(Mandatory=$true)][string]$Project,
    [Parameter(ValueFromRemainingArguments=$true)][string[]]$HyperFramesArgs
)
$ErrorActionPreference = 'Stop'
$taskProjectPath = (Resolve-Path -LiteralPath $Project).Path
$taskOldBrowser = $env:HYPERFRAMES_BROWSER_PATH
$taskChrome = Join-Path $env:ProgramFiles 'Google\Chrome\Application\chrome.exe'
if (-not $taskOldBrowser -and (Test-Path -LiteralPath $taskChrome)) {
    $env:HYPERFRAMES_BROWSER_PATH = $taskChrome
}
Push-Location -LiteralPath $taskProjectPath
try {
    & npx.cmd --yes hyperframes@0.8.34 @HyperFramesArgs
    $taskExitCode = $LASTEXITCODE
} finally {
    Pop-Location
    $env:HYPERFRAMES_BROWSER_PATH = $taskOldBrowser
}
exit $taskExitCode
