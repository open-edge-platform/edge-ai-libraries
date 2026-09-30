Set-StrictMode -Version 2.0

function EnsurePortsOpen {
    param(
        [int[]]$Ports
    )

    $listeners = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue
    $listenerPorts = @{}
    foreach ($listener in @($listeners)) {
        $listenerPorts[[int]$listener.LocalPort] = $true
    }

    foreach ($port in $Ports) {
        if (-not $listenerPorts.ContainsKey([int]$port)) {
            throw ('Port {0} is not listening.' -f $port)
        }
    }

    return $true
}
