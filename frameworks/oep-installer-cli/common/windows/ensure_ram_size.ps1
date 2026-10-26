Set-StrictMode -Version 2.0

function EnsureRamSize {
    param(
        [double]$MinimumGigabytes = 1
    )

    $computerSystem = Get-CimInstance -ClassName Win32_ComputerSystem -ErrorAction Stop
    $totalGigabytes = [math]::Round(($computerSystem.TotalPhysicalMemory / 1GB), 2)
    if ($totalGigabytes -lt $MinimumGigabytes) {
        throw ('Insufficient RAM. Need {0} GB, found {1} GB.' -f $MinimumGigabytes, $totalGigabytes)
    }

    return $totalGigabytes
}
