Set-StrictMode -Version 2.0

function EnsureTrap {
    param(
        [string]$CleanupPath
    )

    if ([string]::IsNullOrEmpty($CleanupPath)) {
        return $null
    }

    foreach ($subscriber in @(Get-EventSubscriber -SourceIdentifier 'PowerShell.Exiting' -ErrorAction SilentlyContinue)) {
        if ($subscriber.Action -and ($subscriber.Action.ToString() -like '*OpenEdgeCliCleanup*')) {
            Unregister-Event -SubscriptionId $subscriber.SubscriptionId -ErrorAction SilentlyContinue
        }
    }

    return (Register-EngineEvent -SourceIdentifier 'PowerShell.Exiting' -Action {
        # OpenEdgeCliCleanup
        if (Test-Path $event.MessageData) {
            Remove-Item -Path $event.MessageData -Force -Recurse -ErrorAction SilentlyContinue
        }
    } -MessageData $CleanupPath)
}
