Set-StrictMode -Version 2.0

function SubcommandInstall {
    param(
        $Context,
        [string[]]$Arguments
    )

    return (ActHelper -Context $Context -ActDescriptor 'install,Installation,Installing,Installed' -SortOption '' -Arguments $Arguments)
}

function SubcommandRemove {
    param(
        $Context,
        [string[]]$Arguments
    )

    return (ActHelper -Context $Context -ActDescriptor 'remove,Removal,Removing,Removed' -SortOption '-r' -Arguments $Arguments)
}

function SubcommandStart {
    param(
        $Context,
        [string[]]$Arguments
    )

    return (ActHelper -Context $Context -ActDescriptor 'start,Start,Starting,Started' -SortOption '' -Arguments $Arguments)
}

function SubcommandStop {
    param(
        $Context,
        [string[]]$Arguments
    )

    if ($Arguments -contains '--help') {
        return (ActHelper -Context $Context -ActDescriptor 'stop,Stop,Stopping,Stopped' -SortOption '-r' -Arguments $Arguments)
    }

    $resolvedArguments = @(ActResolveArgs -Context $Context -ActName 'stop' -Arguments $Arguments)
    if (-not ($resolvedArguments -contains '--continue')) {
        $resolvedArguments += '--continue'
    }
    return (ActHelper -Context $Context -ActDescriptor 'stop,Stop,Stopping,Stopped' -SortOption '-r' -Arguments $resolvedArguments)
}

function Get-FinalizedInstallerFunctionNames {
    param(
        [string]$ScriptPath
    )

    $functionNames = New-Object System.Collections.ArrayList
    $resolvedScriptPath = Get-CurrentScriptPath -PreferredPath $ScriptPath -FunctionName 'Get-FinalizedInstallerFunctionNames'
    $root = [System.IO.Path]::GetFullPath((Get-InstallerRoot -ScriptPath $resolvedScriptPath))
    $rootPrefix = $root.TrimEnd([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
    foreach ($command in @(Get-Command -CommandType Function -ErrorAction SilentlyContinue | Sort-Object Name)) {
        $name = [string]$command.Name
        if ($functionNames.Contains($name)) {
            continue
        }
        if (($null -eq $command.ScriptBlock) -or [string]::IsNullOrEmpty($command.ScriptBlock.File)) {
            continue
        }
        $commandPath = [System.IO.Path]::GetFullPath($command.ScriptBlock.File)
        if (-not ($commandPath.StartsWith($rootPrefix, [System.StringComparison]::OrdinalIgnoreCase))) {
            continue
        }
        [void]$functionNames.Add($name)
    }
    return @($functionNames)
}

function SubcommandList {
    param(
        $Context,
        [string[]]$Arguments
    )

    if ($Arguments -contains '--help') {
        [Console]::Out.WriteLine('list options:')
        [Console]::Out.WriteLine('  list            show discovered components and profiles.')
        [Console]::Out.WriteLine('')
        return 0
    }

    [Console]::Out.WriteLine('Mapping profiles and components...')

    $profileLines = New-Object System.Collections.ArrayList
    $moduleLines = New-Object System.Collections.ArrayList
    $allCommands = @($Context.Commands)
    $allModules = @($Context.Modules | Sort-Object)
    $profileFunctions = @(ActGet -Operation 'prefix' -Prefix 'profile_' -Context $Context)
    $moduleCommandMap = @{}

    foreach ($moduleName in $allModules) {
        $moduleCommands = New-Object System.Collections.ArrayList
        foreach ($commandName in $allCommands) {
            $expandedNames = @(ActExpandModules -Context $Context -ActName $commandName -Modules @($moduleName) -Arguments @())
            foreach ($expandedName in $expandedNames) {
                if ($Context.Functions.ContainsKey($commandName + '_' + $expandedName)) {
                    if (-not $moduleCommands.Contains($commandName)) {
                        [void]$moduleCommands.Add($commandName)
                    }
                    break
                }
            }
        }
        $moduleCommandMap[$moduleName] = @($moduleCommands)
        [void]$moduleLines.Add([pscustomobject]@{ Name = $moduleName; Commands = '[' + (($moduleCommandMap[$moduleName] -join ' ')) + ']' })
    }

    foreach ($profileFunction in $profileFunctions) {
        if ($profileFunction -match '^Windows\d+Profile(.+)$') {
            $profileName = ConvertFrom-ActFunctionSuffix -Name $Matches[1]
            if ($allModules -contains $profileName) {
                continue
            }

            $profileCommands = New-Object System.Collections.ArrayList
            foreach ($commandName in $allCommands) {
                foreach ($expandedName in @(& $profileFunction $commandName)) {
                    $expandedModule = [string]$expandedName
                    if ($moduleCommandMap.ContainsKey($expandedModule) -and ($moduleCommandMap[$expandedModule] -contains $commandName)) {
                        if (-not $profileCommands.Contains($commandName)) {
                            [void]$profileCommands.Add($commandName)
                        }
                        break
                    }
                }
            }
            [void]$profileLines.Add([pscustomobject]@{ Name = $profileName; Commands = '[' + (($profileCommands -join ' ')) + ']' })
        }
    }

    if ($profileLines.Count -gt 0) {
        Write-Output 'List of Profiles:'
        $profileLines | EnsureColumns
        Write-Output ''
    }

    if ($moduleLines.Count -gt 0) {
        Write-Output 'List of Components:'
        $moduleLines | Sort-Object Name | EnsureColumns
        Write-Output ''
    }

    return 0
}

function SubcommandSetup {
    param(
        $Context,
        [string[]]$Arguments
    )

    if ($Arguments -contains '--help') {
        [Console]::Out.WriteLine('setup options:')
        [Console]::Out.WriteLine('  setup           reconstruct the installer under the user profile.')
        [Console]::Out.WriteLine('')
        return 0
    }

    $localAppData = $env:LOCALAPPDATA
    if ([string]::IsNullOrEmpty($localAppData)) {
        $localAppData = Join-Path $env:HOME '.local/share'
    }
    $installerDirectory = Join-Path $localAppData 'Programs/openedge-cli'
    $installerPath = Join-Path $installerDirectory 'openedge-cli.ps1'
    if (-not (Test-Path $installerDirectory)) {
        [void](New-Item -ItemType Directory -Path $installerDirectory -Force)
    }

    $functionNames = @(Get-FinalizedInstallerFunctionNames -ScriptPath (Get-CurrentScriptPath -PreferredPath $null -FunctionName 'SubcommandSetup'))

    $builder = New-Object System.Collections.ArrayList
    [void]$builder.Add('Set-StrictMode -Version 2.0')
    foreach ($functionName in $functionNames) {
        $functionBody = [string]((Get-Item -LiteralPath ('Function:\' + $functionName)).ScriptBlock.ToString())
        [void]$builder.Add(('function {0} {{' -f $functionName))
        foreach ($functionLine in ($functionBody -split "`r?`n")) {
            [void]$builder.Add($functionLine)
        }
        [void]$builder.Add('}')
        [void]$builder.Add('')
    }
    [void]$builder.Add('$__openEdgeCliEnvArgs = ConvertTo-OpenEdgeArgumentList -Text ([Environment]::GetEnvironmentVariable(''OPENEDGE_CLI_ARGS''))')
    [void]$builder.Add('$__openEdgeCliScriptArgs = @($args)')
    [void]$builder.Add('$__openEdgeCliDefaultInstall = @()')
    [void]$builder.Add('$__openEdgeCliDefaultStart = @()')
    [void]$builder.Add('$__openEdgeCliInvocationPath = $null')
    [void]$builder.Add('if ($MyInvocation.MyCommand) { $__openEdgeCliInvocationPath = $MyInvocation.MyCommand.Path }')
    [void]$builder.Add('$__openEdgeCliEnableImplicitDefaults = [string]::IsNullOrEmpty($__openEdgeCliInvocationPath)')
    [void]$builder.Add('if ($MyInvocation.InvocationName -eq ''.'') { $__openEdgeCliEnableImplicitDefaults = $false }')
    [void]$builder.Add('$__openEdgeCliRegisteredExitCleanupEvent = $false')
    [void]$builder.Add('$__openEdgeCliExitCleanupEvent = Get-EventSubscriber -SourceIdentifier PowerShell.Exiting -ErrorAction SilentlyContinue | Where-Object { $_.Action -and $_.Action.ToString().Contains(''EnsureSudoStopSession'') } | Select-Object -First 1')
    [void]$builder.Add('if ($null -eq $__openEdgeCliExitCleanupEvent) {')
    [void]$builder.Add('    $__openEdgeCliExitCleanupEvent = Register-EngineEvent -SourceIdentifier PowerShell.Exiting -SupportEvent -Action { if (Get-Command -Name ''EnsureSudoStopSession'' -ErrorAction SilentlyContinue) { EnsureSudoStopSession } }')
    [void]$builder.Add('    $__openEdgeCliRegisteredExitCleanupEvent = $true')
    [void]$builder.Add('}')
    [void]$builder.Add('$__openEdgeCliFinalArgs = @(Get-EntryPointArguments -ScriptArgs $__openEdgeCliScriptArgs -EnvArgs $__openEdgeCliEnvArgs -ScriptPath $__openEdgeCliInvocationPath -DefaultInstall $__openEdgeCliDefaultInstall -DefaultStart $__openEdgeCliDefaultStart -EnableImplicitDefaults $__openEdgeCliEnableImplicitDefaults)')
    [void]$builder.Add('$__openEdgeCliExitCode = 1')
    [void]$builder.Add('try {')
    [void]$builder.Add('    $__openEdgeCliExitCode = main -Arguments @($__openEdgeCliFinalArgs) -ScriptPath $__openEdgeCliInvocationPath')
    [void]$builder.Add('}')
    [void]$builder.Add('finally {')
    [void]$builder.Add('    if ($__openEdgeCliRegisteredExitCleanupEvent -and ($null -ne $__openEdgeCliExitCleanupEvent)) {')
    [void]$builder.Add('        Unregister-Event -SubscriptionId $__openEdgeCliExitCleanupEvent.Id -ErrorAction SilentlyContinue')
    [void]$builder.Add('    }')
    [void]$builder.Add('    if (Get-Command -Name ''EnsureSudoStopSession'' -ErrorAction SilentlyContinue) {')
    [void]$builder.Add('        EnsureSudoStopSession')
    [void]$builder.Add('    }')
    [void]$builder.Add('}')
    [void]$builder.Add('if (-not [string]::IsNullOrEmpty($__openEdgeCliInvocationPath)) { exit $__openEdgeCliExitCode }')
    [System.IO.File]::WriteAllLines($installerPath, [string[]]$builder)
    Write-Output ('Installer reconstructed at {0}' -f $installerPath)

    $completionPath = Join-Path $installerDirectory 'openedge-cli-completion.ps1'
    $allNames = @($Context.Names | Sort-Object -Unique)
    $completionCommands = New-Object System.Collections.ArrayList
    foreach ($entry in @(Get-SubcommandSpecs)) {
        if (-not $completionCommands.Contains([string]$entry.Name)) {
            [void]$completionCommands.Add([string]$entry.Name)
        }
    }
    $escapedCommands = @($completionCommands | ForEach-Object { ($_ -replace "'", "''") })
    $escapedComponents = @($allNames | ForEach-Object { ($_ -replace "'", "''") })
    $completionScript = @(
        'Register-ArgumentCompleter -CommandName openedge-cli.ps1,openedge-cli -ScriptBlock {',
        '    param($commandName, $parameterName, $wordToComplete, $commandAst, $fakeBoundParameters)',
        ('    $commands = @(''{0}'')' -f ($escapedCommands -join ''',''')),
        ('    $components = @(''{0}'')' -f ($escapedComponents -join ''',''')),
                '    $words = @($commandAst.CommandElements | ForEach-Object { $_.Extent.Text })',
        '    $argumentWords = @($words | Select-Object -Skip 1)',
        '    $cursorIsCommand = ($argumentWords.Count -eq 0) -or (($argumentWords.Count -eq 1) -and ($wordToComplete -eq $argumentWords[0]))',
        '    if ($cursorIsCommand -or [string]::IsNullOrEmpty($wordToComplete)) {',
        '        foreach ($item in $commands) {',
        '            if ($item -like ($wordToComplete + ''*'')) {',
        '                Write-Output (New-Object System.Management.Automation.CompletionResult ($item, $item, ''ParameterValue'', $item))',
        '            }',
        '        }',
        '    }',
        '    foreach ($item in $components) {',
        '        if ($item -like ($wordToComplete + ''*'')) {',
        '            Write-Output (New-Object System.Management.Automation.CompletionResult ($item, $item, ''ParameterValue'', $item))',
        '        }',
        '    }',
        '}'
    )
    [System.IO.File]::WriteAllLines($completionPath, [string[]]$completionScript)
    Write-Output ('PowerShell completion created at {0}' -f $completionPath)

    $commandShimPath = Join-Path $installerDirectory 'openedge-cli.cmd'
    $commandShim = @(
        '@echo off',
        'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0openedge-cli.ps1" %*'
    )
    [System.IO.File]::WriteAllLines($commandShimPath, [string[]]$commandShim)
    Write-Output ('Command shim created at {0}' -f $commandShimPath)

    $userPath = [Environment]::GetEnvironmentVariable('PATH', 'User')
    $pathEntries = New-Object System.Collections.ArrayList
    if (-not [string]::IsNullOrEmpty($userPath)) {
        foreach ($entry in ($userPath -split ';')) {
            if (-not [string]::IsNullOrEmpty($entry)) {
                [void]$pathEntries.Add($entry)
            }
        }
    }
    $normalizedTarget = $installerDirectory.TrimEnd('\')
    $alreadyOnPath = $false
    foreach ($entry in $pathEntries) {
        if ($entry.TrimEnd('\') -ieq $normalizedTarget) {
            $alreadyOnPath = $true
            break
        }
    }
    if (-not $alreadyOnPath) {
        [void]$pathEntries.Add($installerDirectory)
        [Environment]::SetEnvironmentVariable('PATH', ($pathEntries -join ';'), 'User')
        Write-Output ('Added {0} to your user PATH. Restart your terminal to use ''openedge-cli''.' -f $installerDirectory)
    }
    if (($env:PATH -split ';') -notcontains $installerDirectory) {
        $env:PATH = '{0};{1}' -f $env:PATH, $installerDirectory
    }
    return 0
}