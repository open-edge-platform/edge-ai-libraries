Set-StrictMode -Version 2.0

function EnsureGitClone {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Repository,
        [Parameter(Mandatory = $true)]
        [string]$Destination,
        [string]$Branch
    )

    if (Test-Path $Destination) {
        Write-Output ('Git clone target already exists. Skipping clone: {0}' -f $Destination)
        return $Destination
    }

    $arguments = @('clone', $Repository, $Destination)
    if (-not [string]::IsNullOrEmpty($Branch)) {
        $arguments = @('clone', '--branch', $Branch, $Repository, $Destination)
    }

    & git @arguments
    if ($LASTEXITCODE -ne 0) {
        throw ('git clone failed for {0}' -f $Repository)
    }

    return $Destination
}
