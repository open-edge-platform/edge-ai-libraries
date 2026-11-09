Set-StrictMode -Version 2.0

function Windows05InstallGit {
    param(
        [string[]]$Arguments
    )

    if (Get-Command git.exe -ErrorAction SilentlyContinue) {
        Write-Output 'Git is already installed. Skipping...'
        return
    }

    Write-Output '@@HIGHLIGHT Installing Git for Windows'
    if (Get-Command winget.exe -ErrorAction SilentlyContinue) {
        $wingetExitCode = EnsureSudo -FilePath 'winget.exe' -ArgumentList @('install', '--id', 'Git.Git', '-e', '--source', 'winget', '--accept-package-agreements', '--accept-source-agreements')
        if ($wingetExitCode -ne 0) {
            throw 'winget failed to install Git.'
        }
        return
    }

    Write-Output 'winget is not available. Install Git for Windows manually from https://git-scm.com/download/win and rerun the installer.'
    throw 'Git installation failed because winget is unavailable.'
}
