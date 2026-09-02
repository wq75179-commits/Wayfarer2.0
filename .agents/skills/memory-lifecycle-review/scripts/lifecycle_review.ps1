[CmdletBinding()]
param(
    [string]$RepoRoot,
    [string[]]$Episode,
    [switch]$All,
    [string[]]$MemoryId,
    [string[]]$ReobserveMemoryId,
    [ValidateSet('json', 'markdown')]
    [string]$Format = 'markdown'
)

$scriptPath = Join-Path $PSScriptRoot 'lifecycle_review.py'
$argsList = @($scriptPath, '--format', $Format)

if ($RepoRoot) {
    $argsList += @('--repo-root', $RepoRoot)
}

if ($All) {
    $argsList += '--all'
}

foreach ($item in $Episode) {
    if ($item) {
        $argsList += @('--episode', $item)
    }
}

foreach ($item in $MemoryId) {
    if ($item) {
        $argsList += @('--memory-id', $item)
    }
}

foreach ($item in $ReobserveMemoryId) {
    if ($item) {
        $argsList += @('--reobserve-memory-id', $item)
    }
}

try {
    & python @argsList
    exit $LASTEXITCODE
}
catch {
    Write-Error "memory-lifecycle-review 启动失败：$($_.Exception.Message)"
    exit 8
}
