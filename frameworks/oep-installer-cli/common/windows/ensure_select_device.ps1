Set-StrictMode -Version 2.0

function EnsureSelectDevice {
    param(
        [string]$Pattern = ''
    )

    $devices = @(Get-CimInstance -ClassName Win32_VideoController -ErrorAction SilentlyContinue)
    if ([string]::IsNullOrEmpty($Pattern)) {
        return $devices
    }

    return @($devices | Where-Object { $_.Name -match $Pattern })
}
