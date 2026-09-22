Set-StrictMode -Version 2.0

function EnsureSudoInvokeLocked {
    param(
        [scriptblock]$Action
    )

    $mutexName = 'Local\OpenEdgeCliSudo-{0}' -f $PID
    $mutex = New-Object System.Threading.Mutex($false, $mutexName)
    $lockTaken = $false
    try {
        $lockTaken = $mutex.WaitOne()
        if (-not $lockTaken) {
            throw 'Failed to acquire the EnsureSudo session lock.'
        }

        function EnsureSudoTestSessionDirectory {
            param(
                [string]$SessionDirectory
            )

            if ([string]::IsNullOrEmpty($SessionDirectory)) {
                return $false
            }

            $resolvedSessionDirectory = [System.IO.Path]::GetFullPath($SessionDirectory)
            $resolvedTempPath = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
            $leafName = Split-Path -Leaf $resolvedSessionDirectory
            if (-not $leafName.StartsWith('openedge-cli-elevated-', [System.StringComparison]::OrdinalIgnoreCase)) {
                return $false
            }
            return EnsureSudoTestPathWithinDirectory -BasePath $resolvedTempPath -CandidatePath $resolvedSessionDirectory
        }
        return (& $Action)
    }
    finally {
        if ($lockTaken) {
            [void]$mutex.ReleaseMutex()
        }
        $mutex.Dispose()
    }
}

function EnsureSudoGetLaunchSpec {
    param(
        [string]$Edition,
        [string]$EncodedCommand
    )

    if ([string]::IsNullOrEmpty($Edition)) {
        $Edition = $PSVersionTable.PSEdition
    }

    $hostExecutable = 'powershell.exe'
    $argumentList = @('-NoProfile')
    if ($Edition -eq 'Core') {
        $hostExecutable = Join-Path $PSHOME 'pwsh'
        if (-not (Test-Path $hostExecutable)) {
            $hostExecutable = 'pwsh.exe'
        }
    }
    else {
        $argumentList += @('-ExecutionPolicy', 'Bypass')
    }

    if (-not [string]::IsNullOrEmpty($EncodedCommand)) {
        $argumentList += @('-EncodedCommand', $EncodedCommand)
    }

    return [pscustomobject]@{
        FilePath = $hostExecutable
        ArgumentList = $argumentList
    }
}

function EnsureSudoGetRelayEncodedCommand {
    param(
        [string]$RelayLogPath,
        [string]$ReadyMarkerPath,
        [string]$StopMarkerPath,
        [string]$RequestDirectory,
        [string]$ReadyToken
    )

    $relayPathLiteral = $RelayLogPath.Replace("'", "''")
    $readyMarkerLiteral = $ReadyMarkerPath.Replace("'", "''")
    $stopMarkerLiteral = $StopMarkerPath.Replace("'", "''")
    $requestDirectoryLiteral = $RequestDirectory.Replace("'", "''")
    $readyTokenLiteral = $ReadyToken.Replace("'", "''")
    $commandTemplate = @'
Set-StrictMode -Version 2.0
[Environment]::SetEnvironmentVariable('OPENEDGE_CLI_RELAY_LOG', '__RELAY__', 'Process')
$relayStream = New-Object System.IO.FileStream('__RELAY__', [System.IO.FileMode]::Append, [System.IO.FileAccess]::Write, [System.IO.FileShare]::ReadWrite)
$relayWriter = New-Object System.IO.StreamWriter($relayStream)
$relayWriter.AutoFlush = $true
try {
    $relayWriter.WriteLine('@@HIGHLIGHT Elevated wrapper started')
    [System.IO.File]::WriteAllText('__READY__', '__READYTOKEN__')
    while ((Test-Path '__REQUESTDIR__') -and (-not (Test-Path '__STOP__'))) {
        $requestFiles = @(Get-ChildItem -LiteralPath '__REQUESTDIR__' -Filter 'request-*.json' -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -notlike '*.response.json' } | Sort-Object Name)
        if ($requestFiles.Count -eq 0) {
            Start-Sleep -Milliseconds 200
            continue
        }

        foreach ($requestFile in $requestFiles) {
            $exitCode = 0
            $commandSucceeded = $true
            $responsePath = ''
            try {
                $request = Get-Content -LiteralPath $requestFile.FullName -Raw | ConvertFrom-Json
                $targetFilePath = [string]$request.FilePath
                $responsePath = [string]$request.ResponsePath
                $responseToken = [string]$request.ResponseToken
                $requestWorkingDirectory = [string]$request.WorkingDirectory
                $resolvedRequestDirectory = [System.IO.Path]::GetFullPath('__REQUESTDIR__')
                $resolvedResponsePath = [System.IO.Path]::GetFullPath($responsePath)
                $resolvedResponseDirectory = [System.IO.Path]::GetDirectoryName($resolvedResponsePath)
                $expectedResponsePath = [System.IO.Path]::GetFullPath(($requestFile.FullName -replace '\.json$', '.response.json'))
                if ([string]::IsNullOrEmpty($resolvedResponseDirectory) -or ($resolvedResponseDirectory -ne $resolvedRequestDirectory)) {
                    throw 'Refusing to write elevated response outside the session request directory.'
                }
                if ($resolvedResponsePath -ne $expectedResponsePath) {
                    throw 'Refusing to write elevated response to an unexpected response file path.'
                }
                $requestDirectoryItem = Get-Item -LiteralPath $resolvedRequestDirectory -ErrorAction Stop
                if (($requestDirectoryItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                    throw 'Refusing to write elevated response through a reparse-point request directory.'
                }
                $isNative = $false
                if ($null -ne $request.PSObject.Properties['IsNative']) {
                    $isNative = [bool]$request.IsNative
                }
                $argumentList = @()
                if ($request.ArgumentList -is [System.Array]) {
                    $argumentList = @($request.ArgumentList)
                }
                elseif ($null -ne $request.ArgumentList) {
                    $argumentList = @([string]$request.ArgumentList)
                }
                $relayWriter.WriteLine(('@@HIGHLIGHT Launching {0}' -f $targetFilePath))
                $LASTEXITCODE = 0
                if (-not [string]::IsNullOrEmpty($requestWorkingDirectory)) {
                    Push-Location -LiteralPath $requestWorkingDirectory
                }
                try {
                    $commandOutput = @(& $targetFilePath @argumentList 2>&1)
                    $commandSucceeded = $?
                    foreach ($outputLine in $commandOutput) {
                        $relayWriter.WriteLine([string]$outputLine)
                    }
                }
                finally {
                    if (-not [string]::IsNullOrEmpty($requestWorkingDirectory)) {
                        Pop-Location
                    }
                }
                if ($isNative -and (($LASTEXITCODE -is [int]) -or ($LASTEXITCODE -is [long]))) {
                    $exitCode = [int]$LASTEXITCODE
                }
                elseif (-not $commandSucceeded) {
                    $exitCode = 1
                }
            }
            catch {
                if ($_.Exception -and $_.Exception.Message) {
                    [Console]::Error.WriteLine($_.Exception.Message)
                    $relayWriter.WriteLine($_.Exception.Message)
                }
                $exitCode = 1
            }
            finally {
                if (-not [string]::IsNullOrEmpty($responsePath)) {
                    [System.IO.File]::WriteAllText($responsePath, (@{ ExitCode = $exitCode; ResponseToken = $responseToken } | ConvertTo-Json -Compress))
                }
                Remove-Item -LiteralPath $requestFile.FullName -Force -ErrorAction SilentlyContinue
            }
        }
    }
}
finally {
    $relayWriter.Dispose()
    $relayStream.Dispose()
}
'@
    $commandText = $commandTemplate.Replace('__RELAY__', $relayPathLiteral).Replace('__READY__', $readyMarkerLiteral).Replace('__STOP__', $stopMarkerLiteral).Replace('__REQUESTDIR__', $requestDirectoryLiteral).Replace('__READYTOKEN__', $readyTokenLiteral)
    return [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($commandText))
}

function EnsureSudoReceiveRelayLines {
    param(
        [string]$RelayPath,
        [long]$Offset,
        [scriptblock]$EmitLine
    )

    if ([string]::IsNullOrEmpty($RelayPath) -or (-not (Test-Path $RelayPath))) {
        return [pscustomobject]@{
            Offset = $Offset
        }
    }

    $fileStream = $null
    $reader = $null
    try {
        $fileStream = New-Object System.IO.FileStream($RelayPath, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
        if ($Offset -gt $fileStream.Length) {
            $Offset = $fileStream.Length
        }
        [void]$fileStream.Seek($Offset, [System.IO.SeekOrigin]::Begin)
        $reader = New-Object System.IO.StreamReader($fileStream)
        while (-not $reader.EndOfStream) {
            & $EmitLine $reader.ReadLine()
        }
        return [pscustomobject]@{
            Offset = $fileStream.Position
        }
    }
    finally {
        if ($null -ne $reader) {
            $reader.Dispose()
        }
        if ($null -ne $fileStream) {
            $fileStream.Dispose()
        }
    }
}

function EnsureSudoResolveCommandPath {
    param(
        [string]$FilePath
    )

    if ([string]::IsNullOrEmpty($FilePath)) {
        return [pscustomobject]@{
            Path = ''
            IsNative = $false
        }
    }

    $command = Get-Command -Name $FilePath -ErrorAction SilentlyContinue
    if ($null -ne $command) {
        if (($command.CommandType -in @('Application', 'ExternalScript')) -and (-not [string]::IsNullOrEmpty($command.Path))) {
            return [pscustomobject]@{
                Path = $command.Path
                IsNative = $true
            }
        }
        return [pscustomobject]@{
            Path = $FilePath
            IsNative = $false
        }
    }

    return [pscustomobject]@{
        Path = $FilePath
        IsNative = $false
    }
}

function EnsureSudoTestPathWithinDirectory {
    param(
        [string]$BasePath,
        [string]$CandidatePath
    )

    if ([string]::IsNullOrEmpty($BasePath) -or [string]::IsNullOrEmpty($CandidatePath)) {
        return $false
    }

    $resolvedBasePath = [System.IO.Path]::GetFullPath($BasePath)
    $resolvedCandidatePath = [System.IO.Path]::GetFullPath($CandidatePath)
    if ($resolvedCandidatePath -eq $resolvedBasePath) {
        return $true
    }
    return $resolvedCandidatePath.StartsWith($resolvedBasePath + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)
}

function EnsureSudoGetSessionInfo {
    $sessionDirectory = [Environment]::GetEnvironmentVariable('OPENEDGE_CLI_SUDO_DIR')
    $relayPath = [Environment]::GetEnvironmentVariable('OPENEDGE_CLI_SUDO_RELAY')
    $readyMarkerPath = [Environment]::GetEnvironmentVariable('OPENEDGE_CLI_SUDO_READY')
    $stopMarkerPath = [Environment]::GetEnvironmentVariable('OPENEDGE_CLI_SUDO_STOP')
    $requestDirectory = [Environment]::GetEnvironmentVariable('OPENEDGE_CLI_SUDO_REQUESTS')
    $processIdText = [Environment]::GetEnvironmentVariable('OPENEDGE_CLI_SUDO_PID')
    $processStartTimeText = [Environment]::GetEnvironmentVariable('OPENEDGE_CLI_SUDO_PROCESS_START')
    $readyToken = [Environment]::GetEnvironmentVariable('OPENEDGE_CLI_SUDO_READY_TOKEN')
    if ([string]::IsNullOrEmpty($sessionDirectory) -or [string]::IsNullOrEmpty($relayPath) -or [string]::IsNullOrEmpty($readyMarkerPath) -or [string]::IsNullOrEmpty($stopMarkerPath) -or [string]::IsNullOrEmpty($requestDirectory) -or [string]::IsNullOrEmpty($processIdText) -or [string]::IsNullOrEmpty($processStartTimeText) -or [string]::IsNullOrEmpty($readyToken)) {
        return $null
    }
    if (-not (Test-Path $sessionDirectory)) {
        return $null
    }
    if ((-not (EnsureSudoTestPathWithinDirectory -BasePath $sessionDirectory -CandidatePath $relayPath)) -or
        (-not (EnsureSudoTestPathWithinDirectory -BasePath $sessionDirectory -CandidatePath $readyMarkerPath)) -or
        (-not (EnsureSudoTestPathWithinDirectory -BasePath $sessionDirectory -CandidatePath $stopMarkerPath)) -or
        (-not (EnsureSudoTestPathWithinDirectory -BasePath $sessionDirectory -CandidatePath $requestDirectory))) {
        return $null
    }
    $processId = 0
    try {
        $processId = [int]$processIdText
    }
    catch {
        return $null
    }
    return [pscustomobject]@{
        SessionDirectory = $sessionDirectory
        RelayPath = $relayPath
        ReadyMarkerPath = $readyMarkerPath
        StopMarkerPath = $stopMarkerPath
        RequestDirectory = $requestDirectory
        ProcessId = $processId
        ProcessStartTime = $processStartTimeText
        ReadyToken = $readyToken
    }
}

function EnsureSudoSetSessionInfo {
    param(
        $Session,
        [long]$Offset
    )

    [Environment]::SetEnvironmentVariable('OPENEDGE_CLI_SUDO_DIR', $Session.SessionDirectory, 'Process')
    [Environment]::SetEnvironmentVariable('OPENEDGE_CLI_SUDO_RELAY', $Session.RelayPath, 'Process')
    [Environment]::SetEnvironmentVariable('OPENEDGE_CLI_SUDO_READY', $Session.ReadyMarkerPath, 'Process')
    [Environment]::SetEnvironmentVariable('OPENEDGE_CLI_SUDO_STOP', $Session.StopMarkerPath, 'Process')
    [Environment]::SetEnvironmentVariable('OPENEDGE_CLI_SUDO_REQUESTS', $Session.RequestDirectory, 'Process')
    [Environment]::SetEnvironmentVariable('OPENEDGE_CLI_SUDO_PID', [string]$Session.ProcessId, 'Process')
    [Environment]::SetEnvironmentVariable('OPENEDGE_CLI_SUDO_PROCESS_START', [string]$Session.ProcessStartTime, 'Process')
    [Environment]::SetEnvironmentVariable('OPENEDGE_CLI_SUDO_READY_TOKEN', [string]$Session.ReadyToken, 'Process')
    [Environment]::SetEnvironmentVariable('OPENEDGE_CLI_SUDO_OFFSET', [string]$Offset, 'Process')
}

function EnsureSudoClearSessionInfo {
    foreach ($name in @('OPENEDGE_CLI_SUDO_DIR', 'OPENEDGE_CLI_SUDO_RELAY', 'OPENEDGE_CLI_SUDO_READY', 'OPENEDGE_CLI_SUDO_STOP', 'OPENEDGE_CLI_SUDO_REQUESTS', 'OPENEDGE_CLI_SUDO_PID', 'OPENEDGE_CLI_SUDO_PROCESS_START', 'OPENEDGE_CLI_SUDO_READY_TOKEN', 'OPENEDGE_CLI_SUDO_OFFSET')) {
        [Environment]::SetEnvironmentVariable($name, $null, 'Process')
    }
}

function EnsureSudoTestSessionAlive {
    param(
        $Session
    )

    if ($null -eq $Session) {
        return $false
    }

    try {
        $process = Get-Process -Id ([int]$Session.ProcessId) -ErrorAction Stop
        if (($null -eq $process) -or $process.HasExited) {
            return $false
        }
        $actualStartTime = $process.StartTime.ToUniversalTime().ToString('o')
        if ($actualStartTime -ne [string]$Session.ProcessStartTime) {
            return $false
        }
        if (-not (Test-Path $Session.ReadyMarkerPath)) {
            return $false
        }
        $readyContent = Get-Content -LiteralPath $Session.ReadyMarkerPath -Raw -ErrorAction SilentlyContinue
        return ($readyContent -eq [string]$Session.ReadyToken)
    }
    catch {
        return $false
    }
}

function EnsureSudoStopSession {
    param(
        [int]$TimeoutSeconds = 5
    )

    try {
        $session = EnsureSudoGetSessionInfo
        if ($null -eq $session) {
            EnsureSudoClearSessionInfo
            return
        }

        $isAlive = EnsureSudoTestSessionAlive -Session $session

        if ($isAlive) {
            try {
                [System.IO.File]::WriteAllText($session.StopMarkerPath, 'stop')
            }
            catch {
            }

            $deadline = (Get-Date).AddSeconds([Math]::Max(1, $TimeoutSeconds))
            while ((Get-Date) -lt $deadline) {
                if (-not (EnsureSudoTestSessionAlive -Session $session)) {
                    $isAlive = $false
                    break
                }
                Start-Sleep -Milliseconds 200
            }
        }

        if ($isAlive -and (EnsureSudoTestSessionAlive -Session $session)) {
            try {
                Stop-Process -Id ([int]$session.ProcessId) -Force -ErrorAction SilentlyContinue
            }
            catch {
            }
            try {
                Wait-Process -Id ([int]$session.ProcessId) -Timeout ([Math]::Max(1, $TimeoutSeconds)) -ErrorAction SilentlyContinue
            }
            catch {
            }
        }

        try {
            if ((Test-Path $session.SessionDirectory) -and
                (Get-Command -Name 'EnsureSudoTestSessionDirectory' -ErrorAction SilentlyContinue) -and
                (EnsureSudoTestSessionDirectory -SessionDirectory $session.SessionDirectory)) {
                EnsureTmpdir -Operation Destroy -Path $session.SessionDirectory | Out-Null
            }
        }
        catch {
        }
    }
    catch {
    }
    finally {
        EnsureSudoClearSessionInfo
    }
}

function EnsureSudoStartSession {
    param(
        [scriptblock]$EmitLine
    )

    $session = EnsureSudoGetSessionInfo
    if (($null -ne $session) -and (Test-Path $session.ReadyMarkerPath) -and (Test-Path $session.RequestDirectory) -and (EnsureSudoTestSessionAlive -Session $session)) {
        return $session
    }
    if (($null -ne $session) -and (Test-Path $session.SessionDirectory) -and (EnsureSudoTestSessionDirectory -SessionDirectory $session.SessionDirectory)) {
        EnsureTmpdir -Operation Destroy -Path $session.SessionDirectory | Out-Null
    }
    EnsureSudoClearSessionInfo

    $sessionDirectory = EnsureTmpdir -Operation Create -Prefix 'elevated' -AllowAdministrators
    $relayPath = Join-Path $sessionDirectory 'relay.log'
    $readyMarkerPath = Join-Path $sessionDirectory 'ready.marker'
    $stopMarkerPath = Join-Path $sessionDirectory 'stop.marker'
    $requestDirectory = Join-Path $sessionDirectory 'requests'
    $readyToken = [guid]::NewGuid().ToString('N')
    $workingDirectory = (Get-Location).Path
    [void](New-Item -ItemType Directory -Path $requestDirectory -Force)
    [System.IO.File]::WriteAllText($relayPath, '')
    EnsureTrap -CleanupPath $sessionDirectory | Out-Null

    $encodedCommand = EnsureSudoGetRelayEncodedCommand -RelayLogPath $relayPath -ReadyMarkerPath $readyMarkerPath -StopMarkerPath $stopMarkerPath -RequestDirectory $requestDirectory -ReadyToken $readyToken
    $launchSpec = EnsureSudoGetLaunchSpec -EncodedCommand $encodedCommand
    $elevatedProcess = Start-Process -FilePath $launchSpec.FilePath -Verb RunAs -WindowStyle Minimized -WorkingDirectory $workingDirectory -ArgumentList $launchSpec.ArgumentList -PassThru
    [Console]::Out.WriteLine('Waiting for elevation approval and installer output...')

    $offset = 0L
    $deadline = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $deadline) {
        $state = EnsureSudoReceiveRelayLines -RelayPath $relayPath -Offset $offset -EmitLine $EmitLine
        $offset = [long]$state.Offset
        if ($elevatedProcess.HasExited) {
            EnsureSudoClearSessionInfo
            if (Test-Path $sessionDirectory) {
                EnsureTmpdir -Operation Destroy -Path $sessionDirectory | Out-Null
            }
            throw 'Elevated session startup was cancelled or exited before becoming ready.'
        }
        if (Test-Path $readyMarkerPath) {
            $readyMarkerContent = Get-Content -LiteralPath $readyMarkerPath -Raw -ErrorAction SilentlyContinue
            if ($readyMarkerContent -ne $readyToken) {
                Start-Sleep -Milliseconds 200
                continue
            }
            $processStartTime = ''
            try {
                $elevatedProcess.Refresh()
                if ($elevatedProcess.HasExited) {
                    throw 'Elevated session startup was cancelled or exited before becoming ready.'
                }
                $processStartTime = $elevatedProcess.StartTime.ToUniversalTime().ToString('o')
            }
            catch {
                try {
                    $elevatedProcessState = Get-Process -Id $elevatedProcess.Id -ErrorAction Stop
                    $processStartTime = $elevatedProcessState.StartTime.ToUniversalTime().ToString('o')
                }
                catch {
                    throw 'Elevated session startup was cancelled or exited before becoming ready.'
                }
            }
            $session = [pscustomobject]@{
                SessionDirectory = $sessionDirectory
                RelayPath = $relayPath
                ReadyMarkerPath = $readyMarkerPath
                StopMarkerPath = $stopMarkerPath
                RequestDirectory = $requestDirectory
                ProcessId = $elevatedProcess.Id
                ProcessStartTime = $processStartTime
                ReadyToken = $readyToken
            }
            EnsureSudoSetSessionInfo -Session $session -Offset $offset
            return $session
        }
        Start-Sleep -Milliseconds 200
    }

    EnsureSudoClearSessionInfo
    if (Test-Path $sessionDirectory) {
        EnsureTmpdir -Operation Destroy -Path $sessionDirectory | Out-Null
    }
    throw 'Timed out waiting for elevated session startup.'
}

function EnsureSudoWaitResponse {
    param(
        $Session,
        [string]$ResponsePath,
        [string]$ResponseToken,
        [scriptblock]$EmitLine,
        [int]$TimeoutSeconds
    )

    if ($TimeoutSeconds -le 0) {
        $TimeoutSeconds = 900
    }

    $offsetText = [Environment]::GetEnvironmentVariable('OPENEDGE_CLI_SUDO_OFFSET', 'Process')
    $offset = 0L
    if (-not [string]::IsNullOrEmpty($offsetText)) {
        try {
            $offset = [long]$offsetText
        }
        catch {
            $offset = 0L
        }
    }

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $state = EnsureSudoReceiveRelayLines -RelayPath $Session.RelayPath -Offset $offset -EmitLine $EmitLine
        $offset = [long]$state.Offset
        [Environment]::SetEnvironmentVariable('OPENEDGE_CLI_SUDO_OFFSET', [string]$offset, 'Process')
        if (Test-Path $ResponsePath) {
            $response = Get-Content -LiteralPath $ResponsePath -Raw | ConvertFrom-Json
            Remove-Item -LiteralPath $ResponsePath -Force -ErrorAction SilentlyContinue
            if ([string]$response.ResponseToken -ne [string]$ResponseToken) {
                throw 'Received mismatched response token from elevated session.'
            }
            return [int]$response.ExitCode
        }
        if ((-not (Test-Path $Session.SessionDirectory)) -or (-not (EnsureSudoTestSessionAlive -Session $Session))) {
            [Console]::Error.WriteLine('Elevated session exited before returning a response.')
            break
        }
        Start-Sleep -Milliseconds 200
    }

    $state = EnsureSudoReceiveRelayLines -RelayPath $Session.RelayPath -Offset $offset -EmitLine $EmitLine
    $offset = [long]$state.Offset
    [Environment]::SetEnvironmentVariable('OPENEDGE_CLI_SUDO_OFFSET', [string]$offset, 'Process')
    if ((Get-Date) -ge $deadline) {
        [Console]::Error.WriteLine('Timed out waiting for elevated command completion.')
    }
    return 1
}

function EnsureSudo {
    param(
        [string]$FilePath,
        [string[]]$ArgumentList,
        [switch]$CheckOnly
    )

    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    $isAdministrator = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

    if ($CheckOnly) {
        return $isAdministrator
    }

    if ([string]::IsNullOrEmpty($FilePath)) {
        throw 'Administrator elevation requires a file path.'
    }

    $resolvedCommand = EnsureSudoResolveCommandPath -FilePath $FilePath
    $resolvedFilePath = [string]$resolvedCommand.Path
    $commandDescription = $resolvedFilePath
    if ($ArgumentList.Count -gt 0) {
        $commandDescription = '{0} {1}' -f $resolvedFilePath, ($ArgumentList -join ' ')
    }

    if ($isAdministrator) {
        try {
            $LASTEXITCODE = 0
            & $resolvedFilePath @ArgumentList
            if ($resolvedCommand.IsNative -and (($LASTEXITCODE -is [int]) -or ($LASTEXITCODE -is [long]))) {
                return [int]$LASTEXITCODE
            }
            if (-not $?) {
                return 1
            }
            return 0
        }
        catch {
            if ($_.Exception -and $_.Exception.Message) {
                [Console]::Error.WriteLine($_.Exception.Message)
            }
            return 1
        }
    }

    try {
        return (EnsureSudoInvokeLocked -Action {
            $session = EnsureSudoStartSession -EmitLine {
                param($Line)
                [Console]::Out.WriteLine([string]$Line)
            }
            $requestId = [guid]::NewGuid().ToString('N')
            $responseToken = [guid]::NewGuid().ToString('N')
            $requestPath = Join-Path $session.RequestDirectory ('request-{0}.json' -f $requestId)
            $responsePath = Join-Path $session.RequestDirectory ('request-{0}.response.json' -f $requestId)
            if (Test-Path $responsePath) {
                Remove-Item -LiteralPath $responsePath -Force -ErrorAction SilentlyContinue
            }
            $requestPayload = @{
                FilePath = $resolvedFilePath
                ArgumentList = @($ArgumentList)
                ResponsePath = $responsePath
                ResponseToken = $responseToken
                WorkingDirectory = (Get-Location).Path
                IsNative = [bool]$resolvedCommand.IsNative
            } | ConvertTo-Json -Compress
            $requestTempPath = '{0}.tmp' -f $requestPath
            [System.IO.File]::WriteAllText($requestTempPath, $requestPayload)
            if (Test-Path $requestPath) {
                [System.IO.File]::Replace($requestTempPath, $requestPath, $null, $false)
            }
            else {
                [System.IO.File]::Move($requestTempPath, $requestPath)
            }
            return (EnsureSudoWaitResponse -Session $session -ResponsePath $responsePath -ResponseToken $responseToken -EmitLine {
                param($Line)
                [Console]::Out.WriteLine([string]$Line)
            } -TimeoutSeconds 900)
        })
    }
    catch {
        $message = 'Elevation failed for: {0}' -f $commandDescription
        if ($_.Exception -and $_.Exception.Message) {
            if ($_.Exception.Message -match 'canceled by the user|cancelled by the user') {
                $message = 'Elevation was cancelled for: {0}' -f $commandDescription
            }
            $message = '{0} ({1})' -f $message, $_.Exception.Message
        }
        [Console]::Error.WriteLine($message)
        return 1
    }
}
