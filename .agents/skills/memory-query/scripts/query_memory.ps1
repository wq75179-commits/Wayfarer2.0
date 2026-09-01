[CmdletBinding()]
param(
    [string]$RepoRoot,
    [Parameter(Mandatory = $true)]
    [string]$Stage,
    [string]$Status,
    [ValidateSet('json', 'markdown')]
    [string]$Format = 'markdown'
)

$queryArgs = @(
    "$PSScriptRoot/query_memory.py",
    '--stage',
    $Stage
)

function Add-OptionalArgument {
    param(
        [string]$Name,
        [object]$Value
    )

    if ($null -ne $Value -and "$Value" -ne '') {
        $script:queryArgs += $Name
        $script:queryArgs += "$Value"
    }
}

Add-OptionalArgument '--repo-root' $RepoRoot
Add-OptionalArgument '--status' $Status
Add-OptionalArgument '--format' $Format

try {
    & python @queryArgs
    exit $LASTEXITCODE
}
catch {
    Write-Error "memory-query 启动失败：$($_.Exception.Message)"
    exit 8
}
