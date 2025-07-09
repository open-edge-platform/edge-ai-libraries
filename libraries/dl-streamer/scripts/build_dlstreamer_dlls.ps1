#Requires -RunAsAdministrator
# ==============================================================================
# Copyright (C) 2025 Intel Corporation
#
# SPDX-License-Identifier: MIT
# ==============================================================================

$env:HTTP_PROXY="http://proxy-dmz.intel.com:911"
$env:HTTPS_PROXY="http://proxy-dmz.intel.com:912"
$DLSTREAMER_TMP = "C:\\dlstreamer_tmp"

if (-Not (Test-Path $DLSTREAMER_TMP)) {
	mkdir $DLSTREAMER_TMP
}

if (-Not (Get-Command winget -errorAction SilentlyContinue)) {
	$progressPreference = 'silentlyContinue'
	Write-Host "Installing WinGet PowerShell module from PSGallery..."
	Install-PackageProvider -Name NuGet -Force | Out-Null
	Install-Module -Name Microsoft.WinGet.Client -Force -Repository PSGallery | Out-Null
	Write-Host "Using Repair-WinGetPackageManager cmdlet to bootstrap WinGet..."
	Repair-WinGetPackageManager -AllUsers
	Write-Host "Done."
}

if (-Not (Test-Path "C:\\BuildTools")) {
	echo "Installing VS BuildTools. Please wait."
	Invoke-WebRequest -OutFile $DLSTREAMER_TMP\\vs_buildtools.exe -Uri https://aka.ms/vs/17/release/vs_buildtools.exe
	Start-Process -Wait -FilePath $DLSTREAMER_TMP\vs_buildtools.exe -ArgumentList "--quiet", "--wait", "--norestart", "--nocache", "--installPath", "C:\\BuildTools", "--add", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "--add", "Microsoft.VisualStudio.ComponentGroup.NativeDesktop.Core"
}

if (-Not (Test-Path "${env:ProgramFiles(x86)}\\Windows Kits")) {
	echo "Installing Windows SDK. Please wait."
	winget install --source winget --exact --id Microsoft.WindowsSDK.10.0.26100
}

$GSTREAMER_VERSION = "1.26.1"

if (-Not (Test-Path "${DLSTREAMER_TMP}\\gstreamer-1.0-msvc-x86_64_${GSTREAMER_VERSION}.msi")) {
	echo "Installing GStreamer ${GSTREAMER_VERSION}. Please wait."
	Invoke-WebRequest -OutFile ${DLSTREAMER_TMP}\\gstreamer-1.0-msvc-x86_64_${GSTREAMER_VERSION}.msi -Uri https://gstreamer.freedesktop.org/data/pkg/windows/${GSTREAMER_VERSION}/msvc/gstreamer-1.0-msvc-x86_64-${GSTREAMER_VERSION}.msi
	Start-Process -Wait -FilePath "msiexec" -ArgumentList "/passive", "INSTALLDIR=C:\gstreamer", "/i", "${DLSTREAMER_TMP}\\gstreamer-1.0-msvc-x86_64_${GSTREAMER_VERSION}.msi", "/qn"
	Invoke-WebRequest -OutFile ${DLSTREAMER_TMP}\\gstreamer-1.0-devel-msvc-x86_64_${GSTREAMER_VERSION}.msi -Uri https://gstreamer.freedesktop.org/data/pkg/windows/${GSTREAMER_VERSION}/msvc/gstreamer-1.0-devel-msvc-x86_64-${GSTREAMER_VERSION}.msi
	Start-Process -Wait -FilePath "msiexec" -ArgumentList "/passive", "INSTALLDIR=C:\gstreamer", "/i", "${DLSTREAMER_TMP}\\gstreamer-1.0-devel-msvc-x86_64_${GSTREAMER_VERSION}.msi", "/qn"
	(Get-Content C:\gstreamer\1.0\msvc_x86_64\lib\pkgconfig\gstreamer-analytics-1.0.pc).Replace('-lm', '') | Set-Content C:\gstreamer\1.0\msvc_x86_64\lib\pkgconfig\gstreamer-analytics-1.0.pc
}

$OPENVINO_FULL_VERSION = "2025.2.0.19140.c01cd93e24d"
$OPENVINO_VERSION = "2025.2"
$OPENVINO_DEST_FOLDER = "C:\\openvino"

if (-Not (Test-Path "${DLSTREAMER_TMP}\\openvino_toolkit_windows_${OPENVINO_FULL_VERSION}_x86_64.zip")) {
	echo "Installing OpenVINO ${OPENVINO_FULL_VERSION}. Please wait."
	Invoke-WebRequest -OutFile ${DLSTREAMER_TMP}\\openvino_toolkit_windows_${OPENVINO_FULL_VERSION}_x86_64.zip -Uri "https://storage.openvinotoolkit.org/repositories/openvino/packages/${OPENVINO_VERSION}/windows/openvino_toolkit_windows_${OPENVINO_FULL_VERSION}_x86_64.zip"
	Expand-Archive -Path "${DLSTREAMER_TMP}\\openvino_toolkit_windows_${OPENVINO_FULL_VERSION}_x86_64.zip" -DestinationPath "C:\"
	if (Test-Path "${OPENVINO_DEST_FOLDER}") {
		Remove-Item -LiteralPath "${OPENVINO_DEST_FOLDER}" -Recurse
	}
	Move-Item -Path "C:\\openvino_toolkit_windows_${OPENVINO_FULL_VERSION}_x86_64" -Destination "${OPENVINO_DEST_FOLDER}"
}

if (-Not (Test-Path "C:\\Program Files\\Git")) {
	echo "Installing Git. Please wait."
	winget install --id Git.Git -e --source winget
}

${env:VCPKG_ROOT}="C:\\vcpkg"
setx path "${env:VCPKG_ROOT};C:\Program Files\Git\bin;${env:VCPKG_ROOT}\downloads\tools\cmake-3.30.1-windows\cmake-3.30.1-windows-i386\bin;${env:VCPKG_ROOT}\downloads\tools\python\python-3.12.7-x64-1"
setx PKG_CONFIG_PATH "C:\gstreamer\1.0\msvc_x86_64\lib\pkgconfig;C:\libva\Microsoft.Direct3D.VideoAccelerationCompatibilityPack.1.0.2\build\native\x64\lib\pkgconfig"
setx LIBVA_DRIVER_NAME "vaon12"
setx LIBVA_DRIVERS_PATH "C:\libva\Microsoft.Direct3D.VideoAccelerationCompatibilityPack.1.0.2\build\native\x64\bin"

C:\BuildTools\Common7\Tools\Launch-VsDevShell.ps1

$DLSTREAMER_SRC_LOCATION = $PWD.Path

if (-Not (Test-Path "${env:VCPKG_ROOT}")) {
	git clone --recursive https://github.com/microsoft/vcpkg.git ${env:VCPKG_ROOT}
	Set-Location -Path ${env:VCPKG_ROOT}
	Start-Process -Wait -FilePath powershell.exe -ArgumentList "-file", "${env:VCPKG_ROOT}\scripts\bootstrap.ps1", "-disableMetrics" -NoNewWindow
	Add-Content -Path ${env:VCPKG_ROOT}\triplets\x64-windows.cmake -Value "`r`nset(VCPKG_BUILD_TYPE release)"
}

if (-Not (Get-Command py -errorAction SilentlyContinue)) {
	Set-Alias -Name python3 -Value python
	Set-Alias -Name py -Value python
}

if (-Not (Test-Path "C:\\libva")) {
	mkdir C:\libva
	Set-Location -Path "C:\libva"
	Invoke-WebRequest -OutFile "nuget.exe" -Uri https://dist.nuget.org/win-x86-commandline/latest/nuget.exe
	Start-Process -Wait -FilePath ".\nuget.exe" -ArgumentList "install", "Microsoft.Direct3D.VideoAccelerationCompatibilityPack" -NoNewWindow
}

if (Test-Path "${DLSTREAMER_TMP}\\build") {
	Remove-Item -LiteralPath "${DLSTREAMER_TMP}\\build" -Recurse
}

mkdir "${DLSTREAMER_TMP}\\build"

Set-Location -Path "${DLSTREAMER_TMP}\\build"
Start-Process -Wait -FilePath "vcpkg" -ArgumentList "integrate", "install", "--triplet=x64-windows" -NoNewWindow
Start-Process -Wait -FilePath "vcpkg" -ArgumentList "install", "--triplet=x64-windows", "--vcpkg-root=${env:VCPKG_ROOT}", "--x-manifest-root=${DLSTREAMER_SRC_LOCATION}" -NoNewWindow

C:\openvino\setupvars.ps1

Start-Process -Wait -FilePath "cmake" -ArgumentList "-DVCPKG_BUILD_TYPE=release", "-DCMAKE_TOOLCHAIN_FILE=${env:VCPKG_ROOT}\scripts\buildsystems\vcpkg.cmake", "${DLSTREAMER_SRC_LOCATION}" -NoNewWindow
Start-Process -Wait -FilePath "cmake" -ArgumentList "--build", ".", "--target", "ALL_BUILD", "--config", "Release" -NoNewWindow

