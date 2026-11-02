Set-StrictMode -Version 2.0

function EnsureHfToken {
    param(
        [string[]]$Models
    )

    if (-not [string]::IsNullOrEmpty($env:HF_TOKEN)) {
        return $env:HF_TOKEN
    }

    $secureToken = Read-Host -Prompt 'Enter HF_TOKEN' -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
    try {
        $env:HF_TOKEN = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    }
    finally {
        if ($bstr -ne [IntPtr]::Zero) {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
        }
    }
    if ([string]::IsNullOrEmpty($env:HF_TOKEN)) {
        throw 'HF_TOKEN is required.'
    }

    return $env:HF_TOKEN
}
