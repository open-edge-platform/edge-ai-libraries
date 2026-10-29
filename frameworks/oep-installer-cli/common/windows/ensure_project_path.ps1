Set-StrictMode -Version 2.0

function EnsureProjectPath {
    $rootPath = $env:LOCALAPPDATA
    if ([string]::IsNullOrEmpty($rootPath)) {
        $rootPath = Join-Path $env:HOME '.local/share'
    }
    $basePath = Join-Path $rootPath 'openedge-cli'
    if (-not (Test-Path $basePath)) {
        [void](New-Item -ItemType Directory -Path $basePath -Force)
    }
    return $basePath
}
