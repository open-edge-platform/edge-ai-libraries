Set-StrictMode -Version 2.0

function ConvertFrom-ActFunctionSuffix {
    param(
        [string]$Name
    )

    if ([string]::IsNullOrEmpty($Name)) {
        return ''
    }

    return ([regex]::Replace($Name, '([a-z0-9])([A-Z])', '$1_$2')).ToLowerInvariant()
}

function ActGet {
    param(
        [ValidateSet('init', 'prefix')]
        [string]$Operation,
        [string]$Prefix,
        $Context
    )

    switch ($Operation) {
        'init' {
            $commands = @('install', 'remove', 'start', 'stop')
            $modules = New-Object System.Collections.ArrayList
            $names = New-Object System.Collections.ArrayList
            $functions = @{}

            foreach ($command in Get-Command -CommandType Function -Name 'Windows[0-9][0-9]*' -ErrorAction SilentlyContinue | Sort-Object Name) {
                if ($command.Name -match '^Windows(\d+)(Install|Remove|Start|Stop|Profile)(.+)$') {
                    $verb = $Matches[2].ToLowerInvariant()
                    $moduleName = ConvertFrom-ActFunctionSuffix -Name $Matches[3]
                    if ($verb -eq 'profile') {
                        $functions['profile_' + $moduleName] = $command.Name
                        if (-not $names.Contains($moduleName)) {
                            [void]$names.Add($moduleName)
                        }
                    }
                    else {
                        $functions[$verb + '_' + $moduleName] = $command.Name
                        if (-not $modules.Contains($moduleName)) {
                            [void]$modules.Add($moduleName)
                        }
                        if (-not $names.Contains($moduleName)) {
                            [void]$names.Add($moduleName)
                        }
                    }
                }
            }

            return [ordered]@{
                Commands = $commands
                Modules = @($modules)
                Names = @($names)
                Functions = $functions
            }
        }
        'prefix' {
            $matches = New-Object System.Collections.ArrayList
            if ($null -eq $Context) {
                return @()
            }
            foreach ($key in ($Context.Functions.Keys | Sort-Object)) {
                if ($key.StartsWith($Prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
                    [void]$matches.Add([string]$Context.Functions[$key])
                }
            }
            return @($matches)
        }
    }
}

function ActExpandModules {
    param(
        $Context,
        [string]$ActName,
        [string[]]$Modules,
        [string[]]$Arguments
    )

    $queue = New-Object System.Collections.ArrayList
    $seen = @{}
    foreach ($moduleName in @($Modules)) {
        if (-not [string]::IsNullOrEmpty($moduleName)) {
            [void]$queue.Add($moduleName)
        }
    }

    for ($index = 0; $index -lt $queue.Count; $index++) {
        $name = [string]$queue[$index]
        if ($seen.ContainsKey($name)) {
            continue
        }

        $seen[$name] = $true
        $profileKey = 'profile_' + $name
        if ($Context.Functions.ContainsKey($profileKey)) {
            $profileFunction = [string]$Context.Functions[$profileKey]
            foreach ($expandedModule in @(& $profileFunction $ActName @($Arguments))) {
                $expandedName = [string]$expandedModule
                if (($expandedName -ne '') -and (-not $seen.ContainsKey($expandedName))) {
                    [void]$queue.Add($expandedName)
                }
            }
        }
    }

    return @($seen.Keys)
}

function ActExtractModules {
    param(
        $Context,
        [string]$ActName,
        [string[]]$Arguments
    )

    $modules = New-Object System.Collections.ArrayList
    foreach ($argument in @($Arguments)) {
        if (($argument -like '--*') -and ($argument.Length -gt 2)) {
            $candidate = $argument.Substring(2)
            if ($Context.Names -contains $candidate) {
                if (-not $modules.Contains($candidate)) {
                    [void]$modules.Add($candidate)
                }
            }
        }
    }

    return @($modules)
}

function ActExtractArgs {
    param(
        $Context,
        [string]$ActName,
        [string]$ModuleName,
        [string[]]$ResolvedModules,
        [string[]]$Arguments
    )

    $globalArgs = New-Object System.Collections.ArrayList
    $moduleArgs = New-Object System.Collections.ArrayList
    $currentModule = ''

    foreach ($argument in @($Arguments)) {
        if ([string]::IsNullOrEmpty($argument) -or ($argument -eq '--')) {
            continue
        }

        if (($argument -like '--*') -and ($argument.Length -gt 2)) {
            $candidate = $argument.Substring(2)
            if ($Context.Names -contains $candidate) {
                $currentModule = $candidate
                continue
            }
        }

        if (($Context.Names -contains $argument) -and (-not $argument.StartsWith('-'))) {
            continue
        }

        if ($currentModule -eq $ModuleName) {
            [void]$moduleArgs.Add($argument)
        }
        elseif ([string]::IsNullOrEmpty($currentModule)) {
            [void]$globalArgs.Add($argument)
        }
    }

    return [ordered]@{
        GlobalArgs = @($globalArgs)
        ModuleArgs = @($moduleArgs)
        Modules = @($ResolvedModules)
    }
}

function ActFindDeps {
    param(
        $Context,
        [string]$ActName,
        [string[]]$Names,
        [string[]]$Arguments
    )

    $handlers = New-Object System.Collections.ArrayList
    foreach ($name in @(ActExpandModules -Context $Context -ActName $ActName -Modules $Names -Arguments $Arguments)) {
        $key = $ActName + '_' + $name
        if ($Context.Functions.ContainsKey($key)) {
            $handler = [string]$Context.Functions[$key]
            if (-not $handlers.Contains($handler)) {
                [void]$handlers.Add($handler)
            }
        }
    }

    return @($handlers)
}

function ActResolveArgs {
    param(
        $Context,
        [string]$ActName,
        [string[]]$Arguments
    )

    if ($ActName -ne 'stop') {
        return @($Arguments)
    }

    $hasExplicitModules = $false
    $seenOption = $false
    for ($argumentIndex = 0; $argumentIndex -lt $Arguments.Count; $argumentIndex++) {
        $argument = [string]$Arguments[$argumentIndex]
        if ($argument -like '--*') {
            if ($Context.Names -contains $argument.Substring(2)) {
                $hasExplicitModules = $true
                break
            }
            $seenOption = $true
            continue
        }
        if ($argument.StartsWith('-')) {
            $seenOption = $true
            continue
        }
        if ((-not $seenOption) -and ($Context.Names -contains $argument)) {
            $hasExplicitModules = $true
            break
        }
    }

    if ($hasExplicitModules) {
        return @($Arguments)
    }

    $stateRoot = Join-Path (EnsureProjectPath) 'states'
    $resolvedArgs = New-Object System.Collections.ArrayList
    if (Test-Path $stateRoot) {
        foreach ($directory in Get-ChildItem -Path $stateRoot -Directory -ErrorAction SilentlyContinue | Sort-Object Name) {
            [void]$resolvedArgs.Add($directory.Name)
        }
    }
    foreach ($argument in @($Arguments)) {
        [void]$resolvedArgs.Add($argument)
    }

    return @($resolvedArgs)
}

function ActHelper {
    param(
        $Context,
        [string]$ActDescriptor,
        [string]$SortOption,
        [string[]]$Arguments
    )

    $parts = $ActDescriptor.Split(',')
    $actName = $parts[0]

    if ($Arguments -contains '--help') {
        Write-Output ('{0} options:' -f $actName)
        Write-Output '  --dry-run       dry-run operations'
        Write-Output '  --continue      ignore errors and proceed to the end'
        if ($actName -eq 'install') {
            $handlers = @(ActGet -Operation 'prefix' -Prefix ($actName + '_') -Context $Context)
            if ($handlers.Count -gt 0) {
                Write-Output '  --reinstall  force reinstallation of the component if present.'
                Write-Output '  --validate   validate component features if present.'
            }
        }
        Write-Output ''
        return 0
    }

    $requestedNames = New-Object System.Collections.ArrayList
    foreach ($argument in @($Arguments)) {
        if ((-not $argument.StartsWith('-')) -and ($Context.Names -contains $argument)) {
            if (-not $requestedNames.Contains($argument)) {
                [void]$requestedNames.Add($argument)
            }
        }
    }
    foreach ($argument in @(ActExtractModules -Context $Context -ActName $actName -Arguments $Arguments)) {
        if (-not $requestedNames.Contains($argument)) {
            [void]$requestedNames.Add($argument)
        }
    }

    foreach ($alwaysIncluded in @('pre_system_scan', 'core_types')) {
        if ($Context.Functions.ContainsKey($actName + '_' + $alwaysIncluded) -and (-not $requestedNames.Contains($alwaysIncluded))) {
            [void]$requestedNames.Add($alwaysIncluded)
        }
    }

    $handles = @(ActFindDeps -Context $Context -ActName $actName -Names @($requestedNames) -Arguments $Arguments)
    if ($handles.Count -eq 0) {
        [Console]::Error.WriteLine('Component not found')
        return 3
    }

    if ($SortOption -eq '-r') {
        $orderedHandles = @($handles | Sort-Object @{ Expression = { if ($_ -match '^Windows(\d+)') { [int]$Matches[1] } else { 9999 } }; Descending = $true }, @{ Expression = { $_ } })
    }
    else {
        $orderedHandles = @($handles | Sort-Object @{ Expression = { if ($_ -match '^Windows(\d+)') { [int]$Matches[1] } else { 9999 } } }, @{ Expression = { $_ } })
    }

    $continueOnError = $Arguments -contains '--continue'
    $dryRun = $Arguments -contains '--dry-run'
    $projectPath = EnsureProjectPath
    $commandLine = ($actName + ' ' + (($Arguments | ForEach-Object { [string]$_ }) -join ' ')).Trim()
    $result = 0

    & {
        foreach ($handler in $orderedHandles) {
            if ($handler -notmatch '^Windows(\d+)(Install|Remove|Start|Stop)(.+)$') {
                continue
            }

            $moduleName = ConvertFrom-ActFunctionSuffix -Name $Matches[3]
            $argumentSplit = ActExtractArgs -Context $Context -ActName $actName -ModuleName $moduleName -ResolvedModules @($requestedNames) -Arguments $Arguments
            $invokeArgs = @($argumentSplit.GlobalArgs + $argumentSplit.ModuleArgs)
            $statePath = Join-Path (Join-Path $projectPath 'states') $moduleName

            if ($dryRun) {
                Write-Output ('@@COMP {0}' -f $moduleName)
                Write-Output ('Invoke {0} with {1}' -f $handler, (($invokeArgs | ForEach-Object { [string]$_ }) -join ' '))
                Write-Output ('@@OK {0}' -f $moduleName)
                continue
            }

            if ($actName -eq 'start') {
                [void](New-Item -ItemType Directory -Path $statePath -Force)
            }

            Write-Output ('@@COMP {0}' -f $moduleName)
            $previousErrorActionPreference = $ErrorActionPreference
            try {
                $ErrorActionPreference = 'Stop'
                foreach ($line in @(& $handler @invokeArgs)) {
                    if ($null -ne $line) {
                        Write-Output ([string]$line)
                    }
                }
                if (($actName -eq 'stop') -or ($actName -eq 'remove')) {
                    if (Test-Path $statePath) {
                        Remove-Item -Path $statePath -Force -Recurse -ErrorAction SilentlyContinue
                    }
                }
                Write-Output ('@@OK {0}' -f $moduleName)
            }
            catch {
                if ($_.Exception -and $_.Exception.Message) {
                    Write-Output $_.Exception.Message
                }
                Write-Output ('@@FAIL {0}' -f $moduleName)
                $result = 1
                if (-not $continueOnError) {
                    break
                }
            }
            finally {
                $ErrorActionPreference = $previousErrorActionPreference
            }
        }

        if ((-not $dryRun) -and ($result -eq 0)) {
            Write-Output '@@REPORT SYSTEM SUMMARY'
            Write-Output ('Completed {0} sequence.' -f $actName)
        }
    } | ActSequentialLogs -ProjectPath $projectPath -CommandLine $commandLine

    return $result
}
