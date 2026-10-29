Set-StrictMode -Version 2.0

function EnsureDiskSpace {
    param(
        [string]$Drive = $env:SystemDrive,
        [double]$MinimumGigabytes = 1
    )

    $driveRoot = [System.IO.Path]::GetPathRoot($Drive)
    if ([string]::IsNullOrEmpty($driveRoot)) {
        $driveRoot = $Drive
    }
    $driveLetter = $driveRoot.TrimEnd('\\')
    $disk = Get-CimInstance -ClassName Win32_LogicalDisk -Filter ("DeviceID = '{0}'" -f $driveLetter) -ErrorAction Stop
    $freeGigabytes = [math]::Round(($disk.FreeSpace / 1GB), 2)
    if ($freeGigabytes -lt $MinimumGigabytes) {
        throw ('Insufficient disk space on {0}. Need {1} GB, found {2} GB.' -f $driveLetter, $MinimumGigabytes, $freeGigabytes)
    }

    return $freeGigabytes
}
