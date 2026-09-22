Set-StrictMode -Version 2.0

function ConvertTo-OpenEdgeArgumentList {
    param(
        [string]$Text
    )

    $items = New-Object System.Collections.ArrayList
    if ([string]::IsNullOrWhiteSpace($Text)) {
        return @()
    }

    $matches = [regex]::Matches($Text, '"((?:[^"\\]|\\.)*)"|''((?:[^''\\]|\\.)*)''|((?:\\.|\S)+)')
    foreach ($match in $matches) {
        if ($match.Groups[1].Success) {
            [void]$items.Add(($match.Groups[1].Value -replace '\\([\"\\])', '$1'))
        }
        elseif ($match.Groups[2].Success) {
            [void]$items.Add(($match.Groups[2].Value -replace "\\(['\\])", '$1'))
        }
        elseif ($match.Groups[3].Success) {
            $bareValue = $match.Groups[3].Value
            $bareValue = $bareValue -replace '\\(.)', '$1'
            [void]$items.Add($bareValue)
        }
    }

    return @($items)
}



function Get-EntryPointArguments {
    param(
        [string[]]$ScriptArgs,
        [string[]]$EnvArgs,
        [string]$ScriptPath,
        [string[]]$DefaultInstall,
        [string[]]$DefaultStart,
        [bool]$EnableImplicitDefaults
    )

    $finalArgs = New-Object System.Collections.ArrayList
    if ($EnableImplicitDefaults -and ($ScriptArgs.Count -eq 0) -and ($EnvArgs.Count -eq 0)) {
        [void]$finalArgs.Add('setup')
        if ($DefaultInstall.Count -gt 0) {
            [void]$finalArgs.Add('install')
            foreach ($item in $DefaultInstall) { [void]$finalArgs.Add($item) }
        }
        if ($DefaultStart.Count -gt 0) {
            [void]$finalArgs.Add('start')
            foreach ($item in $DefaultStart) { [void]$finalArgs.Add($item) }
        }
    }

    foreach ($item in @($ScriptArgs)) { [void]$finalArgs.Add($item) }
    foreach ($item in @($EnvArgs)) { [void]$finalArgs.Add($item) }
    return @($finalArgs)
}

function Get-CurrentScriptPath {
    param(
        [string]$PreferredPath,
        [string]$FunctionName
    )

    if (-not [string]::IsNullOrEmpty($PreferredPath)) {
        return $PreferredPath
    }

    $command = Get-Command -Name $FunctionName -ErrorAction SilentlyContinue
    if (($null -ne $command) -and ($null -ne $command.ScriptBlock) -and (-not [string]::IsNullOrEmpty($command.ScriptBlock.File))) {
        return $command.ScriptBlock.File
    }

    return ''
}

function Get-InstallerRoot {
    param(
        [string]$ScriptPath
    )

    if ([string]::IsNullOrEmpty($ScriptPath)) {
        return (Get-Location).Path
    }

    $scriptDirectory = Split-Path -Parent $ScriptPath
    if (Test-Path (Join-Path $scriptDirectory 'common/windows')) {
        return $scriptDirectory
    }

    $parentDirectory = Split-Path -Parent $scriptDirectory
    if (-not [string]::IsNullOrEmpty($parentDirectory) -and (Test-Path (Join-Path $parentDirectory 'common/windows'))) {
        return $parentDirectory
    }

    return $scriptDirectory
}

function Get-SubcommandSpecs {
    $commands = New-Object System.Collections.ArrayList
    foreach ($command in @(Get-Command -CommandType Function -ErrorAction SilentlyContinue | Where-Object { $_.Name -match '^Subcommand(.+)$' } | Sort-Object Name)) {
        $suffix = [string]$command.Name.Substring(10)
        if ([string]::IsNullOrEmpty($suffix)) {
            continue
        }

        if (Get-Command -Name 'ConvertFrom-ActFunctionSuffix' -CommandType Function -ErrorAction SilentlyContinue) {
            $commandName = ConvertFrom-ActFunctionSuffix -Name $suffix
        }
        else {
            $commandName = ([regex]::Replace($suffix, '([a-z0-9])([A-Z])', '$1_$2')).ToLowerInvariant()
        }
        [void]$commands.Add([pscustomobject]@{
            Name = [string]$commandName
            Function = [string]$command.Name
        })
    }

    return @($commands | Sort-Object Name, Function)
}



function Get-AvailableSubcommands {
    param(
        [string]$ScriptPath
    )

    $commands = New-Object System.Collections.ArrayList
    foreach ($entry in @(Get-SubcommandSpecs)) {
        if (-not [string]::IsNullOrEmpty([string]$entry.Name)) {
            [void]$commands.Add([string]$entry.Name)
        }
    }

    return @($commands | Sort-Object -Unique)
}

function Invoke-InstallerCommand {
    param(
        [scriptblock]$ScriptBlock,
        [object[]]$ArgumentList = @()
    )

    $results = @(& $ScriptBlock @ArgumentList)
    if ($results.Count -eq 1 -and (($results[0] -is [int]) -or ($results[0] -is [long]))) {
        return [int]$results[0]
    }

    $exitCode = 0
    $limit = $results.Count
    if (($results.Count -gt 0) -and (($results[-1] -is [int]) -or ($results[-1] -is [long]))) {
        $exitCode = [int]$results[-1]
        $limit = $results.Count - 1
    }

    for ($index = 0; $index -lt $limit; $index++) {
        if ($null -ne $results[$index]) {
            [Console]::Out.WriteLine([string]$results[$index])
        }
    }

    return $exitCode
}

function Show-MainHelp {
    param(
        [string[]]$Commands,
        $Context,
        [string]$ScriptPath
    )

    [Console]::Out.WriteLine(('Usage: <{0}> component [component...]' -f ($Commands -join '|')))
    [Console]::Out.WriteLine('common options:')
    [Console]::Out.WriteLine('  --help          this help message.')
    [Console]::Out.WriteLine('')
    $subcommandSpecs = @{}
    if (Get-Command -Name 'Get-SubcommandSpecs' -CommandType Function -ErrorAction SilentlyContinue) {
        foreach ($entry in @(Get-SubcommandSpecs)) {
            $subcommandSpecs[[string]$entry.Name] = [string]$entry.Function
        }
    }
    foreach ($commandName in $Commands) {
        if ($subcommandSpecs.ContainsKey($commandName)) {
            $subcommandFunction = [string]$subcommandSpecs[$commandName]
            [void](Invoke-InstallerCommand -ScriptBlock {
                param($FunctionName, $CurrentContext)
                & $FunctionName -Context $CurrentContext -Arguments @('--help')
            } -ArgumentList @($subcommandFunction, $Context))
        }
    }
}

function main {
    param(
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$Arguments,
        [string]$ScriptPath
    )

    $installerName = 'openedge-cli'
    $effectiveArguments = @($Arguments)
    $resolvedScriptPath = Get-CurrentScriptPath -PreferredPath $ScriptPath -FunctionName 'main'
    $commands = @(Get-AvailableSubcommands -ScriptPath $resolvedScriptPath)
    $subcommandSpecs = @{}
    if (Get-Command -Name 'Get-SubcommandSpecs' -CommandType Function -ErrorAction SilentlyContinue) {
        foreach ($entry in @(Get-SubcommandSpecs)) {
            $subcommandSpecs[[string]$entry.Name] = [string]$entry.Function
        }
    }
    $context = $null
    if (Get-Command -Name 'ActGet' -CommandType Function -ErrorAction SilentlyContinue) {
        $context = ActGet -Operation 'init'
    }
    $globalArgs = New-Object System.Collections.ArrayList
    $invocations = New-Object System.Collections.ArrayList
    $currentInvocation = $null

    for ($argumentIndex = 0; $argumentIndex -lt $effectiveArguments.Count; $argumentIndex++) {
        $value = $effectiveArguments[$argumentIndex]
        switch ($value) {
            '--help' {
                if ($invocations.Count -eq 0) {
                    Show-MainHelp -Commands $commands -Context $context -ScriptPath $resolvedScriptPath
                    return 0
                }
                [void]$currentInvocation.Args.Add($value)
            }
            '--dry-run' {
                [void]$globalArgs.Add($value)
            }
            '--continue' {
                [void]$globalArgs.Add($value)
            }
            default {
                if ($commands -contains $value) {
                    $currentInvocation = [ordered]@{
                        Command = $value
                        Args = (New-Object System.Collections.ArrayList)
                        OriginalIndex = $argumentIndex
                    }
                    [void]$invocations.Add($currentInvocation)
                }
                elseif ($invocations.Count -eq 0) {
                    [Console]::Error.WriteLine('Unknown command: {0}' -f $value)
                    return 3
                }
                else {
                    [void]$currentInvocation.Args.Add($value)
                }
            }
        }
    }

    if ($invocations.Count -eq 0) {
        Show-MainHelp -Commands $commands -Context $context -ScriptPath $resolvedScriptPath
        return 0
    }

    $result = 0
    for ($index = 0; $index -lt $invocations.Count; $index++) {
        $invocation = $invocations[$index]
        $commandName = [string]$invocation.Command
        $commandArgs = @($globalArgs + $invocation.Args)

        if ($subcommandSpecs.ContainsKey($commandName)) {
            $subcommandFunction = [string]$subcommandSpecs[$commandName]
            $result = Invoke-InstallerCommand -ScriptBlock {
                param($FunctionName, $CurrentContext, $CurrentArguments)
                & $FunctionName -Context $CurrentContext -Arguments $CurrentArguments
            } -ArgumentList @($subcommandFunction, $context, $commandArgs)
        }
        else {
            [Console]::Error.WriteLine('Unknown command: {0}' -f $commandName)
            return 3
        }

        if (($result -ne 0) -and (-not ($globalArgs -contains '--continue'))) {
            break
        }
    }

    return $result
}

#### COLLECTION OF MODULES ####

function Get-RenderedCommonPaths {
    param(
        [string]$ScriptPath
    )

    $root = Get-InstallerRoot -ScriptPath $ScriptPath
    $resolvedPaths = New-Object System.Collections.ArrayList
    $commonRoot = Join-Path $root 'common/windows'
    if (Test-Path $commonRoot) {
        foreach ($item in @(Get-ChildItem -Path $commonRoot -Filter '*.ps1' -File -ErrorAction SilentlyContinue | Sort-Object Name)) {
            [void]$resolvedPaths.Add($item.FullName)
        }
    }

    return @($resolvedPaths)
}

function Get-CommonWindowsHelperPaths {
    param(
        [string]$ScriptPath
    )

    return @(Get-RenderedCommonPaths -ScriptPath $ScriptPath | Where-Object { [System.IO.Path]::GetFileName($_) -ne 'cli_cmds.ps1' })
}

function Get-BootstrapCommonPaths {
    param(
        [string]$ScriptPath
    )

    return @(Get-RenderedCommonPaths -ScriptPath $ScriptPath)
}

function Get-SourceEntrypointPaths {
    param(
        [string]$ScriptPath
    )

    $resolvedPaths = New-Object System.Collections.ArrayList
    foreach ($fullPath in @(Get-CommonWindowsHelperPaths -ScriptPath $ScriptPath)) {
        [void]$resolvedPaths.Add($fullPath)
    }

    $root = Get-InstallerRoot -ScriptPath $ScriptPath
    foreach ($relativeRoot in @('module', 'profile')) {
        $scanRoot = Join-Path $root $relativeRoot
        if (Test-Path $scanRoot) {
            foreach ($item in @(Get-ChildItem -Path $scanRoot -Filter 'windows.ps1' -File -Recurse -ErrorAction SilentlyContinue | Sort-Object FullName | Group-Object DirectoryName | ForEach-Object { $_.Group | Select-Object -First 1 })) {
                [void]$resolvedPaths.Add($item.FullName)
            }
        }
    }

    return @($resolvedPaths)
}

function Import-InstallerSources {
    param(
        [string]$ScriptPath
    )

    return @(Get-SourceEntrypointPaths -ScriptPath $ScriptPath)
}

function SubcommandBootstrap {
    param(
        $Context,
        [string[]]$Arguments
    )

    $resolvedScriptPath = Get-CurrentScriptPath -PreferredPath $null -FunctionName 'SubcommandBootstrap'
    $root = Get-InstallerRoot -ScriptPath $resolvedScriptPath

    if ($Arguments -contains '--help') {
        Write-Output 'bootstrap options:'
        Write-Output '  --install=<name>       set default installation component|profile.'
        Write-Output '  --start=<name>         set default start component|profile.'
        Write-Output '  --output/-o/--output= specify the installer path to be created.'
        Write-Output '  --dry-run              show the bootstrap plan only.'
        Write-Output ''

        $profiles = @()
        $profileRoot = Join-Path $root 'profile'
        if (Test-Path $profileRoot) {
            $profiles = @(Get-ChildItem -Path $profileRoot -Filter 'windows.ps1' -File -Recurse -ErrorAction SilentlyContinue | ForEach-Object { $_.Directory.Name } | Sort-Object -Unique)
        }
        $modules = @()
        $moduleRoot = Join-Path $root 'module'
        if (Test-Path $moduleRoot) {
            $modules = @(Get-ChildItem -Path $moduleRoot -Filter 'windows.ps1' -File -Recurse -ErrorAction SilentlyContinue | ForEach-Object { $_.Directory.Name } | Sort-Object -Unique)
        }

        if ($profiles.Count -gt 0) {
            Write-Output '  list of bootstrap profiles:'
            foreach ($profile in $profiles) {
                Write-Output ('    {0}' -f $profile)
            }
        }

        if ($modules.Count -gt 0) {
            Write-Output '  list of bootstrap components:'
            foreach ($module in $modules) {
                Write-Output ('    {0}' -f $module)
            }
        }

        if (($profiles.Count + $modules.Count) -gt 0) {
            Write-Output ''
        }

        return 0
    }

    $installModules = New-Object System.Collections.ArrayList
    $startModules = New-Object System.Collections.ArrayList
    $selectedModules = New-Object System.Collections.ArrayList
    $renderedPath = ''
    $dryRun = $false

    for ($index = 0; $index -lt $Arguments.Count; $index++) {
        $value = $Arguments[$index]
        if ($value -like '--install=*') {
            [void]$installModules.Add($value.Substring(10))
            continue
        }
        if ($value -like '--start=*') {
            [void]$startModules.Add($value.Substring(8))
            continue
        }
        if ($value -eq '--output' -or $value -eq '-o') {
            if (($index + 1) -ge $Arguments.Count) {
                [Console]::Error.WriteLine('Missing value for {0}' -f $value)
                return 3
            }
            $index++
            $renderedPath = $Arguments[$index]
            continue
        }
        if ($value -like '--output=*') {
            $renderedPath = $value.Substring(9)
            continue
        }
        if ($value -eq '--dry-run') {
            $dryRun = $true
            continue
        }
        if ($value.StartsWith('-')) {
            [Console]::Error.WriteLine('Unknown bootstrap option: {0}' -f $value)
            return 3
        }
        [void]$selectedModules.Add($value)
    }

    if ($selectedModules.Count -eq 0) {
        $profileNames = @{}
        $profileRoot = Join-Path $root 'profile'
        if (Test-Path $profileRoot) {
            foreach ($item in Get-ChildItem -Path $profileRoot -Filter 'windows.ps1' -File -Recurse -ErrorAction SilentlyContinue | Sort-Object FullName) {
                $profileNames[$item.Directory.Name] = $true
                [void]$selectedModules.Add($item.Directory.Name)
            }
        }
        $moduleRoot = Join-Path $root 'module'
        if (Test-Path $moduleRoot) {
            foreach ($item in Get-ChildItem -Path $moduleRoot -Filter 'windows.ps1' -File -Recurse -ErrorAction SilentlyContinue | Sort-Object FullName) {
                if (-not $profileNames.ContainsKey($item.Directory.Name)) {
                    [void]$selectedModules.Add($item.Directory.Name)
                }
            }
        }
    }

    if ($selectedModules.Count -eq 0) {
        foreach ($name in @($Context.Names)) {
            [void]$selectedModules.Add($name)
        }
    }

    $queue = New-Object System.Collections.ArrayList
    $hasUnknownSelection = $false
    foreach ($name in $selectedModules) {
        [void]$queue.Add($name)
    }

    $seenNames = @{}
    $selectedScripts = @{}
    for ($index = 0; $index -lt $queue.Count; $index++) {
        $name = [string]$queue[$index]
        if ([string]::IsNullOrEmpty($name) -or $seenNames.ContainsKey($name)) {
            continue
        }

        $seenNames[$name] = $true
        $profilePath = Join-Path $root (Join-Path 'profile' (Join-Path $name 'windows.ps1')).Replace('\', '/')
        $modulePath = Join-Path $root (Join-Path 'module' (Join-Path $name 'windows.ps1')).Replace('\', '/')

        if (Test-Path $profilePath) {
            $selectedScripts[$profilePath] = $true
            $expandedModules = @(ActExpandModules -Context $Context -ActName 'install' -Modules @($name))
            foreach ($expandedModule in $expandedModules) {
                if (-not $seenNames.ContainsKey($expandedModule)) {
                    [void]$queue.Add($expandedModule)
                }
            }
        }
        elseif (Test-Path $modulePath) {
            $selectedScripts[$modulePath] = $true
        }
        else {
            [Console]::Error.WriteLine('Unknown component or profile: {0}' -f $name)
            $hasUnknownSelection = $true
        }
    }

    if ($hasUnknownSelection) {
        return 3
    }

    if ($selectedScripts.Count -eq 0) {
        foreach ($fallbackModule in @($Context.Modules)) {
            $fallbackPath = Join-Path $root (Join-Path 'module' (Join-Path $fallbackModule 'windows.ps1')).Replace('\', '/')
            if (Test-Path $fallbackPath) {
                $selectedScripts[$fallbackPath] = $true
            }
        }
    }

    if ($selectedScripts.Count -eq 0) {
        [Console]::Error.WriteLine('No bootstrap component')
        return 3
    }

    $scriptDirectory = Split-Path -Parent $resolvedScriptPath
    if ((-not [string]::IsNullOrEmpty($scriptDirectory)) -and ($scriptDirectory -ne $root)) {
        [Console]::Error.WriteLine('bootstrap is only available from the source entrypoint')
        return 3
    }

    if ([string]::IsNullOrEmpty($renderedPath)) {
        $renderedPath = Join-Path $root 'rendered/openedge-cli.ps1'
    }
    elseif (-not [System.IO.Path]::IsPathRooted($renderedPath)) {
        $renderedPath = Join-Path $root $renderedPath
    }

    $orderedScripts = @($selectedScripts.Keys | Sort-Object)
    foreach ($scriptFile in $orderedScripts) {
        $relativePath = $scriptFile.Substring($root.Length).TrimStart([char[]]@(92, 47))
        Write-Output ('==== bootstrapping {0} ====' -f $relativePath)
    }

    if ($dryRun) {
        return 0
    }

    $renderedDirectory = Split-Path -Parent $renderedPath
    if (-not (Test-Path $renderedDirectory)) {
        [void](New-Item -ItemType Directory -Path $renderedDirectory -Force)
    }

    $builder = New-Object System.Collections.ArrayList
    $scriptLines = @(Get-Content -LiteralPath $resolvedScriptPath)
    $markerIndex = -1
    for ($lineIndex = 0; $lineIndex -lt $scriptLines.Count; $lineIndex++) {
        if ($scriptLines[$lineIndex] -eq '#### COLLECTION OF MODULES ####') {
            $markerIndex = $lineIndex
            break
        }
    }
    if ($markerIndex -lt 0) {
        throw 'Bootstrap marker not found.'
    }
    foreach ($line in $scriptLines[0..($markerIndex - 1)]) {
        [void]$builder.Add($line)
    }
    [void]$builder.Add('')

    foreach ($commonPath in @(Get-BootstrapCommonPaths -ScriptPath $resolvedScriptPath)) {
        foreach ($line in @(Get-Content -LiteralPath $commonPath)) {
            [void]$builder.Add($line)
        }
        [void]$builder.Add('')
    }

    foreach ($scriptFile in $orderedScripts) {
        foreach ($line in @(Get-Content -LiteralPath $scriptFile)) {
            [void]$builder.Add($line)
        }
        [void]$builder.Add('')
    }

    $defaultInstallModules = New-Object System.Collections.ArrayList
    foreach ($moduleName in $installModules) {
        $expandedModules = @(ActExpandModules -Context $Context -ActName 'install' -Modules @($moduleName))
        if ($expandedModules.Count -eq 0) {
            $expandedModules = @($moduleName)
        }
        foreach ($expandedModule in $expandedModules) {
            if (-not $defaultInstallModules.Contains($expandedModule)) {
                [void]$defaultInstallModules.Add($expandedModule)
            }
        }
    }
    $defaultStartModules = New-Object System.Collections.ArrayList
    foreach ($moduleName in $startModules) {
        $expandedModules = @(ActExpandModules -Context $Context -ActName 'start' -Modules @($moduleName))
        if ($expandedModules.Count -eq 0) {
            $expandedModules = @($moduleName)
        }
        foreach ($expandedModule in $expandedModules) {
            if (-not $defaultStartModules.Contains($expandedModule)) {
                [void]$defaultStartModules.Add($expandedModule)
            }
        }
    }

    $defaultInstallLiteral = '@(' + (($defaultInstallModules | ForEach-Object { '''{0}''' -f ($_.Replace("'", "''")) }) -join ', ') + ')'
    $defaultStartLiteral = '@(' + (($defaultStartModules | ForEach-Object { '''{0}''' -f ($_.Replace("'", "''")) }) -join ', ') + ')'

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
    [void]$builder.Add('$__openEdgeCliEnvArgs = ConvertTo-OpenEdgeArgumentList -Text ([Environment]::GetEnvironmentVariable(''OPENEDGE_CLI_ARGS''))')
    [void]$builder.Add('$__openEdgeCliScriptArgs = @($args)')
    [void]$builder.Add((' $__openEdgeCliDefaultInstall = {0}' -f $defaultInstallLiteral).TrimStart())
    [void]$builder.Add((' $__openEdgeCliDefaultStart = {0}' -f $defaultStartLiteral).TrimStart())
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

    [System.IO.File]::WriteAllLines($renderedPath, [string[]]$builder)
    Write-Output ('Rendered to {0}' -f $renderedPath)
    return 0
}

$__openEdgeCliImportPaths = @(Import-InstallerSources -ScriptPath $MyInvocation.MyCommand.Path)
foreach ($__openEdgeCliImportPath in $__openEdgeCliImportPaths) {
    . $__openEdgeCliImportPath
}
$__openEdgeCliInvocationPath = $null
if ($MyInvocation.MyCommand) {
    $__openEdgeCliInvocationPath = $MyInvocation.MyCommand.Path
}
$__openEdgeCliEnableImplicitDefaults = [string]::IsNullOrEmpty($__openEdgeCliInvocationPath)
if ($MyInvocation.InvocationName -eq '.') {
    $__openEdgeCliEnableImplicitDefaults = $false
}
$__openEdgeCliRegisteredExitCleanupEvent = $false
$__openEdgeCliExitCleanupEvent = Get-EventSubscriber -SourceIdentifier PowerShell.Exiting -ErrorAction SilentlyContinue |
    Where-Object { $_.Action -and $_.Action.ToString().Contains('EnsureSudoStopSession') } |
    Select-Object -First 1
if ($null -eq $__openEdgeCliExitCleanupEvent) {
    $__openEdgeCliExitCleanupEvent = Register-EngineEvent -SourceIdentifier PowerShell.Exiting -SupportEvent -Action {
        if (Get-Command -Name 'EnsureSudoStopSession' -ErrorAction SilentlyContinue) {
            EnsureSudoStopSession
        }
    }
    $__openEdgeCliRegisteredExitCleanupEvent = $true
}
$__openEdgeCliEnvArgs = ConvertTo-OpenEdgeArgumentList -Text ([Environment]::GetEnvironmentVariable('OPENEDGE_CLI_ARGS'))
$__openEdgeCliScriptArgs = @($args)
$__openEdgeCliDefaultInstall = @()
$__openEdgeCliDefaultStart = @()
$__openEdgeCliFinalArgs = @(Get-EntryPointArguments -ScriptArgs $__openEdgeCliScriptArgs -EnvArgs $__openEdgeCliEnvArgs -ScriptPath $__openEdgeCliInvocationPath -DefaultInstall $__openEdgeCliDefaultInstall -DefaultStart $__openEdgeCliDefaultStart -EnableImplicitDefaults $__openEdgeCliEnableImplicitDefaults)
$__openEdgeCliExitCode = 1
try {
    $__openEdgeCliExitCode = main -Arguments @($__openEdgeCliFinalArgs) -ScriptPath $__openEdgeCliInvocationPath
}
finally {
    if ($__openEdgeCliRegisteredExitCleanupEvent -and ($null -ne $__openEdgeCliExitCleanupEvent)) {
        Unregister-Event -SubscriptionId $__openEdgeCliExitCleanupEvent.Id -ErrorAction SilentlyContinue
    }
    if (Get-Command -Name 'EnsureSudoStopSession' -ErrorAction SilentlyContinue) {
        EnsureSudoStopSession
    }
}
if (-not [string]::IsNullOrEmpty($__openEdgeCliInvocationPath)) {
    exit $__openEdgeCliExitCode
}
