# Constants
$SampleInterval = 1
$FilePathToCheck = ".\.collector-signals\.collector.run"
$CollectorOutputFile = ".\.collector-signals\.collector.out"

# Select Counters to Query
$CounterSet = New-Object System.Collections.Generic.List[System.String]
# - Avg CPU frequency [MHz]
$CounterSet.Add("\Processor Information(_Total)\Processor Frequency")
# - Avg CPU utilization [%]
$CounterSet.Add("\Processor Information(_Total)\% Processor Time")
# - Avg memory utilization [%]
$CounterSet.Add("\Memory\% Committed Bytes In Use")
# - Avg GPU Engine 3D utilization [%]
$CounterSet.Add("\GPU Engine(*_engtype_3d)\Utilization Percentage")
# - Avg GPU Engine Video Decode utilization [%]
$CounterSet.Add("\GPU Engine(*_engtype_VideoDecode)\Utilization Percentage")
# - Avg package power [picowatt-hours]
$CounterSet.Add("\Energy Meter(_Total)\Energy")
# - Avg overall system temperature [Kelvin]
$CounterSet.Add("\Thermal Zone Information(\_TZ.THM0)\Temperature")
# Not Found in Performance Counters:
# - Avg GPU frequency [MHz]
# - Avg GPU power [picowatt-hours]
# - Avg CPU temperature [Kelvin]

while ($true) {

    # Wait until the file is present
    while (-not (Test-Path $FilePathToCheck)) {
        Write-Output "Waiting for $FilePathToCheck"
        Start-Sleep -Seconds 1
    }

    Write-Output "Starting Performance Counter Collection"

    # Cleanup previous collection 
    Remove-Item -Path $CollectorOutputFile -ErrorAction SilentlyContinue

    try {
        # Query Counters
        Get-Counter -Counter $CounterSet -Continuous -SampleInterval $SampleInterval -ErrorAction Stop | Foreach-Object {

            # Get Per Counter Values
            $ProcessorFrequencyValue = ($_.CounterSamples | Where-Object -Property Path -Match ".*processor information.*processor frequency").CookedValue
            $ProcessorUsageValue = ($_.CounterSamples | Where-Object -Property Path -Match ".*processor information.*% processor time").CookedValue
            $MemoryUsageValue = ($_.CounterSamples | Where-Object -Property Path -Match ".*memory.*% committed bytes in use").CookedValue
            $PackagePowerValue = ($_.CounterSamples | Where-Object -Property Path -Match ".*energy meter.*energy").CookedValue
            $SystemTemperatureValue = ($_.CounterSamples | Where-Object -Property Path -Match ".*thermal zone information.*temperature").CookedValue
            $GPUEngine3DValues = ($_.CounterSamples | Where-Object -Property Path -Match ".*gpu engine.*engtype_3d").CookedValue
            $GPUEngineVideoDecodeValues = ($_.CounterSamples | Where-Object -Property Path -Match ".*gpu engine.*engtype_videodecode").CookedValue

            # Sum Per Counter Values
            $GPUEngine3DSum = ($GPUEngine3DValues | Measure-Object -Sum).sum
            $GPUEngineVideoDecodeSum = ($GPUEngineVideoDecodeValues | Measure-Object -Sum).sum

            # Prepare Reporting Data
            $ProcessorFrequency = [math]::Round($ProcessorFrequencyValue,2)
            $ProcessorUsage = [math]::Round($ProcessorUsageValue,2)
            $MemoryUsage = [math]::Round($MemoryUsageValue,2)
            $PackagePower = [math]::Round($PackagePowerValue,2)
            $SystemTemperature = [math]::Round($SystemTemperatureValue,2)
            $GPUEngine3DUsage = [math]::Round($GPUEngine3DSum,2)
            $GPUEngineVideoDecodeUsage = [math]::Round($GPUEngineVideoDecodeSum,2)
            $Epoch = [DateTimeOffset]::Now.ToUnixTimeSeconds()

            # Report Data
            $output = "metrics "
            $output += "cpu-frequency-mhz=$ProcessorFrequency,"
            $output += "cpu-usage-percent=$ProcessorUsage,"
            # NOTE: Echoing the value from system temperature
            $output += "cpu-temperature-kelvins=$SystemTemperature,"
            $output += "memory-usage-percent=$MemoryUsage,"
            $output += "package-power-pwh=$PackagePower,"
            $output += "system-temperature-kelvins=$SystemTemperature,"
            # NOTE: Echoing the value from cpu frequency
            $output += "gpu-frequency-mhz=$ProcessorFrequency,"
            # NOTE: Echoing the value from package power
            $output += "gpu-power-pwh=$PackagePower,"
            $output += "gpu-3d-usage-percent=$GPUEngine3DUsage,"
            $output += "gpu-videodecode-usage-percent=$GPUEngineVideoDecodeUsage"
            $output += " $($Epoch)"
            
            # Write to console
            Write-Output $output

            # Write to file
            $output | Out-File -Append -FilePath $CollectorOutputFile

            # Check if the run file is still present
            if (-not (Test-Path $FilePathToCheck)) {
                Write-Output "Stopping Performance Counter Collection"
                continue
            }
        }
    } catch {
        Write-Output "Error occurred in Get-Counter. Restarting collection."
        Start-Sleep -Seconds 1
        continue
    }
}