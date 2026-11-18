Set-StrictMode -Version 2.0

function EnsureTmpdir {
    param(
        [ValidateSet('Create', 'Destroy')]
        [string]$Operation,
        [string]$Path,
        [string]$Prefix,
        [switch]$AllowAdministrators
    )

    switch ($Operation) {
        'Create' {
            $basePath = [System.IO.Path]::GetTempPath()
            $leafName = 'openedge-cli'
            if (-not [string]::IsNullOrEmpty($Prefix)) {
                $leafName = '{0}-{1}' -f $leafName, $Prefix
            }
            $targetPath = Join-Path $basePath ('{0}-{1}' -f $leafName, [guid]::NewGuid().ToString('N'))
            [void](New-Item -ItemType Directory -Path $targetPath -Force)

            $acl = Get-Acl -Path $targetPath
            $acl.SetAccessRuleProtection($true, $false)
            foreach ($rule in @($acl.Access)) {
                [void]$acl.RemoveAccessRule($rule)
            }
            $currentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
            $currentUserSid = $currentIdentity.User
            $acl.SetOwner($currentUserSid)
            $systemSid = New-Object Security.Principal.SecurityIdentifier([Security.Principal.WellKnownSidType]::LocalSystemSid, $null)
            $userRule = New-Object Security.AccessControl.FileSystemAccessRule($currentUserSid, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
            $systemRule = New-Object Security.AccessControl.FileSystemAccessRule($systemSid, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
            $acl.AddAccessRule($userRule)
            $acl.AddAccessRule($systemRule)
            if ($AllowAdministrators) {
                $administratorsSid = New-Object Security.Principal.SecurityIdentifier([Security.Principal.WellKnownSidType]::BuiltinAdministratorsSid, $null)
                $administratorsRule = New-Object Security.AccessControl.FileSystemAccessRule($administratorsSid, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
                $acl.AddAccessRule($administratorsRule)
            }
            Set-Acl -Path $targetPath -AclObject $acl
            return $targetPath
        }
        'Destroy' {
            if ((-not [string]::IsNullOrEmpty($Path)) -and (Test-Path $Path)) {
                Remove-Item -Path $Path -Force -Recurse -ErrorAction SilentlyContinue
            }
        }
    }
}
