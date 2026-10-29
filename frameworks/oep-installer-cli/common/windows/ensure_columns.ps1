Set-StrictMode -Version 2.0

function EnsureColumns {
    [CmdletBinding()]
    param(
        [Parameter(ValueFromPipeline = $true)]
        $InputObject
    )

    begin {
        $items = New-Object System.Collections.ArrayList
    }

    process {
        [void]$items.Add($InputObject)
    }

    end {
        if ($items.Count -eq 0) {
            return
        }

        if ($items[0] -is [string]) {
            foreach ($item in $items) {
                Write-Output $item
            }
            return
        }

        $items | Format-Table -AutoSize | Out-String -Width 4096 | ForEach-Object {
            foreach ($line in $_ -split "`r?`n") {
                if ($line -ne '') {
                    Write-Output $line.TrimEnd()
                }
            }
        }
    }
}
