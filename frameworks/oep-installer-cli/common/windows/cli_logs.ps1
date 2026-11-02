Set-StrictMode -Version 2.0

function ActSequentialLogs {
    [CmdletBinding()]
    param(
        [Parameter(ValueFromPipeline = $true)]
        [string]$InputObject,
        [string]$ProjectPath,
        [string]$CommandLine
    )

    begin {
        $logDirectory = $ProjectPath
        if (-not (Test-Path $logDirectory)) {
            [void](New-Item -ItemType Directory -Path $logDirectory -Force)
        }

        $logFile = Join-Path $logDirectory ((Get-Date).ToString('yyyy-MM-dd') + '.logs')
        $logFileStream = $null
        $logStreamWriter = $null
        $relayLogFile = [Environment]::GetEnvironmentVariable('OPENEDGE_CLI_RELAY_LOG')
        $relayFileStream = $null
        $relayStreamWriter = $null
        $logFileStream = New-Object System.IO.FileStream($logFile, [System.IO.FileMode]::Append, [System.IO.FileAccess]::Write, [System.IO.FileShare]::ReadWrite)
        $logStreamWriter = New-Object System.IO.StreamWriter($logFileStream)
        $logStreamWriter.AutoFlush = $true
        $logStreamWriter.WriteLine(('========== {0} ==========' -f (Get-Date).ToString('s')))
        $logStreamWriter.WriteLine(('@@COMMAND {0}' -f $CommandLine))
        if (-not [string]::IsNullOrEmpty($relayLogFile)) {
            $relayFileStream = New-Object System.IO.FileStream($relayLogFile, [System.IO.FileMode]::Append, [System.IO.FileAccess]::Write, [System.IO.FileShare]::ReadWrite)
            $relayStreamWriter = New-Object System.IO.StreamWriter($relayFileStream)
            $relayStreamWriter.AutoFlush = $true
        }

        $statusByComponent = @{}
        $elapsedByComponent = @{}
        $startedByComponent = @{}
        $componentOrder = New-Object System.Collections.ArrayList
        $currentComponent = ''
        $wallStart = Get-Date
        $summaryEmitted = $false
        $isRedirected = [Console]::IsOutputRedirected -or [Console]::IsErrorRedirected

        function Write-LoggedLine {
            param(
                [string]$Line,
                [string]$Color
            )

            $logStreamWriter.WriteLine($Line)
            if ($null -ne $relayStreamWriter) {
                $relayStreamWriter.WriteLine($Line)
            }
            if ($isRedirected) {
                Write-Output $Line
            }
            elseif ([string]::IsNullOrEmpty($Color)) {
                Write-Host $Line
            }
            else {
                Write-Host $Line -ForegroundColor $Color
            }
        }

        function Format-Elapsed {
            param(
                [timespan]$Elapsed
            )

            if ($Elapsed.TotalHours -ge 1) {
                return ('{0:hh\:mm\:ss}' -f $Elapsed)
            }

            return ('{0:mm\:ss}' -f $Elapsed)
        }

        function Emit-Summary {
            if ($summaryEmitted) {
                return
            }

            $summaryEmitted = $true
            $okCount = 0
            $failedCount = 0
            foreach ($component in $componentOrder) {
                $status = 'failed'
                if ($statusByComponent.ContainsKey($component)) {
                    $status = [string]$statusByComponent[$component]
                }
                if ($status -eq 'ok') {
                    $okCount++
                }
                else {
                    $failedCount++
                }

                $elapsed = [timespan]::Zero
                if ($elapsedByComponent.ContainsKey($component)) {
                    $elapsed = [timespan]$elapsedByComponent[$component]
                }
                Write-LoggedLine -Line ('{0}: {1} ({2})' -f $component, $status, (Format-Elapsed -Elapsed $elapsed)) -Color $null
            }
            Write-LoggedLine -Line ('Totals: {0} ok, {1} failed' -f $okCount, $failedCount) -Color $null
            Write-LoggedLine -Line ('Overall: {0}' -f (Format-Elapsed -Elapsed ((Get-Date) - $wallStart))) -Color $null
        }
    }

    process {
        $line = ''
        if ($null -ne $InputObject) {
            $line = [string]$InputObject
        }

        if ($line -match '^@@COMP\s+(.+)$') {
            $currentComponent = $Matches[1].Trim()
            if (-not $componentOrder.Contains($currentComponent)) {
                [void]$componentOrder.Add($currentComponent)
            }
            $startedByComponent[$currentComponent] = Get-Date
            Write-LoggedLine -Line $line -Color 'Yellow'
            return
        }

        if ($line -match '^@@OK(?:\s+(.+))?$') {
            $component = $currentComponent
            if ($Matches.ContainsKey(1) -and ($Matches[1].Trim() -ne '')) {
                $component = $Matches[1].Trim()
            }
            if (($component -ne '') -and $startedByComponent.ContainsKey($component)) {
                $elapsedByComponent[$component] = (Get-Date) - [datetime]$startedByComponent[$component]
            }
            if ($component -ne '') {
                $statusByComponent[$component] = 'ok'
            }
            Write-LoggedLine -Line $line -Color 'Green'
            return
        }

        if ($line -match '^@@FAIL(?:\s+(.+))?$') {
            $component = $currentComponent
            if ($Matches.ContainsKey(1) -and ($Matches[1].Trim() -ne '')) {
                $component = $Matches[1].Trim()
            }
            if (($component -ne '') -and $startedByComponent.ContainsKey($component)) {
                $elapsedByComponent[$component] = (Get-Date) - [datetime]$startedByComponent[$component]
            }
            if ($component -ne '') {
                $statusByComponent[$component] = 'failed'
            }
            Write-LoggedLine -Line $line -Color 'Red'
            return
        }

        if ($line -match '^@@HIGHLIGHT(?:\s+.+)?$') {
            Write-LoggedLine -Line $line -Color 'Cyan'
            return
        }

        if ($line -match '^@@REPORT(?:\s+.+)?$') {
            Write-LoggedLine -Line $line -Color 'Cyan'
            return
        }

        if ($line -match '^@@FOCUS(?:\s+.+)?$') {
            Write-LoggedLine -Line $line -Color $null
            return
        }

        if ($line -match '^@@COMMAND(?:\s+.+)?$') {
            Write-LoggedLine -Line $line -Color $null
            return
        }

        if ($line -match '^@@SUMMARY(?:\s+.+)?$') {
            return
        }

        Write-LoggedLine -Line $line -Color $null
    }

    end {
        try {
            Emit-Summary
        }
        finally {
            if ($null -ne $logStreamWriter) {
                $logStreamWriter.Dispose()
            }
            if ($null -ne $logFileStream) {
                $logFileStream.Dispose()
            }
            if ($null -ne $relayStreamWriter) {
                $relayStreamWriter.Dispose()
            }
            if ($null -ne $relayFileStream) {
                $relayFileStream.Dispose()
            }
        }
    }
}
