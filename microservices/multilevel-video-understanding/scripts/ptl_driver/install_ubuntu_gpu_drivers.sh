#!/bin/bash

################################################################
##
## This script will setup the apt configuration & install all
## the Platform Software Packages
## with platform POR kernel
##
## usage: sudo ./installer.sh <os_version> <platform> <release_tag> <kernel_variant>
## Passing arguments 1: <os_version>
##     possible values ==> UBUNTU_JAMMY, UBUNTU_NOBLE
## Passing arguments 2: <platform>
##     possible values ==> ARL, ASL, RPL, MTL, ADL, PTL, BTL, TWL, WCL
## Passing arguments 3: <release_tag>
##     possible values for release_tag ==> kernel release tag
## Passing arguments 4: <kernel_variant>
##     possible values for kernel_variant ==> default or rt


set -o pipefail


current_workspace="$PWD"

# Function to display help
display_help() {
    echo "Usage: $0 <os_version> <platform> <release_tag> <kernel_variant>"
    echo
    echo "This script will set up the apt configuration & install all the Platform Software Packages with platform POR kernel."
    echo
    echo "The <os_version> parameter should be one of the following:"
    echo "  UBUNTU_JAMMY"
    echo "  UBUNTU_NOBLE"
    echo
    echo "<platform> parameter should be MTL / ARL / RPL / ASL / ADL / PTL / BTL / TWL / WCL"
    echo
    echo "<release_tag> should be the release tag example mainline-tracking-overlay-v6.8-ubuntu-240509T064507Z"
    echo
    echo "<kernel_variant> should be default or rt"
    echo
    echo "Example:"
    echo "  sudo $0 UBUNTU_NOBLE BTL mainline-tracking-overlay-pre-prod-v6.14-ubuntu-250606T082705Z default"
    echo
    echo "Options:"
    echo "  -h, --help    Display this help message and exit"
    exit 0
}

# Check if the correct number of parameters is provided
if [ "$#" -lt 4 ] || [ "$1" == "-h" ] || [ "$1" == "--help" ]; then
    display_help
fi

#Check 1st parameter as product name
if [ "$1" == "UBUNTU_JAMMY" ] || [ "$1" == "UBUNTU_NOBLE" ]; then
    os_version="$1"
else
    echo "ERROR: Incorrect first Parameter value"
    display_help
fi

#Check 2nd parameter with supported platform
if [ "$2" == "ARL" ] || [ "$2" == "ASL" ] || [ "$2" == "RPL" ] || [ "$2" == "MTL" ] || [ "$2" == "ADL" ] || [ "$2" == "PTL" ] || [ "$2" == "BTL" ] || [ "$2" == "TWL" ] || [ "$2" == "WCL" ]; then
    platform="$2"

    #based on platform assigned kernel version
    if  [ "$2" == "ADL" ]; then
        kernel_version="6.6"
    elif [ "$2" == "RPL" ] || [ "$2" == "MTL" ] || [ "$2" == "ARL" ] || [ "$2" == "BTL" ] || [ "$2" == "ASL" ] || [ "$2" == "TWL" ] ; then
        kernel_version="6.12"
    elif [ "$2" == "PTL" ] || [ "$2" == "WCL" ] ; then
        kernel_version="6.17"
    else
        kernel_version="6.11"
    fi
else
    echo "ERROR: Incorrect second Parameter value"
    display_help
fi

if [ "$4" == "default" ] || [ "$4" == "rt" ];then
    kernel_variant="$4"
else
    echo "ERROR: Incorrect second Parameter value"
    display_help
fi

release_tag="$3"
#Check 3rd parameter with supported platform kernel version.
if [[ $3 == *$kernel_version* ]]
then
    if [[ "$kernel_variant" == "rt" ]]
    then
        if [ "$2" == "ARL" ] || [ "$2" == "MTL" ]; then
            echo "ERROR: RT kernel is not supported in ARL and MTL platforms"
            display_help
        fi
    fi
else
    echo "ERROR: Passed kernel tag version not match with platform"
    display_help
fi

ppa_url="https://download.01.org/intel-linux-overlay/ubuntu/"

exceptionFailString=("E: Sub-process /usr/bin/dpkg returned an error code (1)")

function die()
{
    outPutOfLastCmd=$( tail -n 1 "$(date +%Y%m%d)_${kernel_variant}_installer.log" )
    isException=0
    for i in "${exceptionFailString[@]}"
    do
        if [[ $outPutOfLastCmd = *$i* ]]; then
            isException=1
            break
        fi
    done

    if [ "$isException" == "0" ]; then
        echo >&2 -e "\nERROR: $*\n"
        exit 1
    fi
}

function run()
{
  # shellcheck disable=SC2048,SC2086
  eval $*
  code=$?; [ $code -ne 0 ] && die "command [$*] failed with error code $code";
}

##################################################################
##.............. check command exist..............................
command_exists()
{
    command -v "$1" >/dev/null 2>&1
}

##################################################################
##..............download GPG Key .................................
download_gpg_key()
{
    GPG_URL=$ppa_url"/"
    if ! command_exists curl; then
            echo "curl is not installed. Installing curl..."
            run "apt install -y curl"
    fi

    if curl --head --silent --fail "$GPG_URL" > /dev/null; then
        echo "URL is accessible. Checking for .gpg key file..."
        HTML_CONTENT=$(curl --silent "$GPG_URL")
        GPG_KEY=$(echo "$HTML_CONTENT" | grep -ioP '(?<=href=")[^"]*\.gpg')
        if [ -n "$GPG_KEY" ]; then
            GPG_FILENAME=$(basename "$GPG_KEY")
            echo "Found .gpg key: $GPG_FILENAME"
            echo "Downloading $GPG_FILENAME..."
            target_file="/etc/apt/trusted.gpg.d/$platform.gpg"
            wget "${GPG_URL}${GPG_FILENAME}" -O "$target_file" --no-check-certificate

            echo "Download completed: $GPG_FILENAME"
        else
            echo "No .gpg key found at the URL."
        fi
    else
        echo "The URL is not accessible. Please check the path and try again."
        exit 1
    fi
    return 0
}


##################################################################
##.............. Update PPA ......................................
PPAUpdate() {
    echo "$(date): Adding PPA & GPG Key..."
    run "apt update"
    run "echo 'N' | apt upgrade -y"

    if [ "$platform" == "PTL" ] || [ "$platform" == "WCL" ];then
        run "DEBIAN_FRONTEND=noninteractive apt-get install ethtool libbpf1 -y"
        run "wget http://ftp.ubuntu.com/ubuntu/pool/main/i/iproute2/iproute2_6.14.0-1ubuntu1_amd64.deb -O /tmp/iproute2_6.14.0-1ubuntu1_amd64.deb"
        run "DEBIAN_FRONTEND=noninteractive apt-get install /tmp/iproute2_6.14.0-1ubuntu1_amd64.deb -y"
    fi

    if [[ $os_version == "UBUNTU_NOBLE" ]]
    then
        run "echo 'deb ${ppa_url}/ noble multimedia main non-free ' | tee /etc/apt/sources.list.d/intel-${platform}.list"
        run "echo 'deb-src ${ppa_url}/ noble multimedia main non-free ' | tee -a /etc/apt/sources.list.d/intel-${platform}.list"
    else
        run "echo 'deb ${ppa_url}/ jammy multimedia main non-free kernels' | tee /etc/apt/sources.list.d/intel-${platform}.list"
        run "echo 'deb-src ${ppa_url}/ jammy multimedia main non-free kernels' | tee -a /etc/apt/sources.list.d/intel-${platform}.list"
    fi
    download_gpg_key
    if [[ $os_version == "UBUNTU_NOBLE" ]]
    then
        echo -e "Package: *\nPin: release o=intel-iot-linux-overlay-noble\nPin-Priority: 2000" | tee /etc/apt/preferences.d/intel-"$platform"
    else
        echo -e "Package: *\nPin: release o=intel-iot-linux-overlay\nPin-Priority: 2000" | tee /etc/apt/preferences.d/intel-"$platform"
    fi
    run "apt update"
    return 0
}

##################################################################
##..........User space component install..........................
InstallPackage()
{
    echo "$(date): Installing User space Component...................."
    if [[ $os_version == "UBUNTU_NOBLE" ]]
    then
        package=("libigfxcmrt-dev,libigfxcmrt7,vim,ocl-icd-libopencl1,curl,openssh-server,net-tools,gir1.2-gst-plugins-bad-1.0,gir1.2-gst-plugins-base-1.0,gir1.2-gstreamer-1.0,gir1.2-gst-rtsp-server-1.0,gstreamer1.0-alsa,gstreamer1.0-gl,gstreamer1.0-gtk3,gstreamer1.0-opencv,gstreamer1.0-plugins-bad,gstreamer1.0-plugins-bad-apps,gstreamer1.0-plugins-base,gstreamer1.0-plugins-base-apps,gstreamer1.0-plugins-good,gstreamer1.0-plugins-ugly,gstreamer1.0-pulseaudio,gstreamer1.0-qt5,gstreamer1.0-rtsp,gstreamer1.0-tools,gstreamer1.0-x,intel-media-va-driver-non-free,libdrm-amdgpu1,libdrm-common,libdrm-dev,libdrm-intel1,libdrm-nouveau2,libdrm-radeon1,libdrm-tests,libdrm2,libgstrtspserver-1.0-dev,libgstrtspserver-1.0-0,libgstreamer-gl1.0-0,libgstreamer-opencv1.0-0,libgstreamer-plugins-bad1.0-0,libgstreamer-plugins-bad1.0-dev,libgstreamer-plugins-base1.0-0,libgstreamer-plugins-base1.0-dev,libgstreamer-plugins-good1.0-0,libgstreamer-plugins-good1.0-dev,libgstreamer1.0-0,libgstreamer1.0-dev,libigdgmm-dev,libigdgmm12,libmfx-gen1.2,libtpms-dev,libtpms0,libva-dev,libva-drm2,libva-glx2,libva-wayland2,libva-x11-2,libva2,libwayland-bin,libwayland-client0,libwayland-cursor0,libwayland-dev,libwayland-doc,libwayland-egl-backend-dev,libwayland-egl1,libwayland-server0,libxatracker2,linux-firmware,mesa-utils,mesa-va-drivers,mesa-vdpau-drivers,mesa-vulkan-drivers,libvpl-dev,libvpl-tools,libmfx-gen-dev,onevpl-tools,ovmf,ovmf-ia32,qemu-block-extra,qemu-guest-agent,qemu-system,qemu-system-arm,qemu-system-common,qemu-system-data,qemu-system-gui,qemu-system-mips,qemu-system-misc,qemu-system-ppc,qemu-system-s390x,qemu-system-sparc,qemu-system-x86,qemu-user,qemu-user-binfmt,qemu-utils,va-driver-all,vainfo,weston,xserver-xorg-core,libvirt0,libvirt-clients,libvirt-daemon,libvirt-daemon-config-network,libvirt-daemon-config-nwfilter,libvirt-daemon-driver-lxc,libvirt-daemon-driver-qemu,libvirt-daemon-driver-storage-gluster,libvirt-daemon-driver-storage-iscsi-direct,libvirt-daemon-driver-storage-rbd,libvirt-daemon-driver-storage-zfs,libvirt-daemon-driver-vbox,libvirt-daemon-driver-xen,libvirt-daemon-system,libvirt-daemon-system-systemd,libvirt-dev,libvirt-doc,libvirt-login-shell,libvirt-sanlock,libvirt-wireshark,libnss-libvirt,swtpm,swtpm-tools,bmap-tools,adb,autoconf,automake,libtool,cmake,g++,gcc,git,intel-gpu-tools,libssl3,libssl-dev,make,mosquitto,mosquitto-clients,build-essential,apt-transport-https,default-jre,docker-compose,ffmpeg,git-lfs,gnuplot,lbzip2,libglew-dev,libglm-dev,libsdl2-dev,mc,openssl,pciutils,python3-pandas,python3-pip,python3-seaborn,terminator,wmctrl,wayland-protocols,gdbserver,iperf3,msr-tools,powertop,linuxptp,lsscsi,tpm2-tools,tpm2-abrmd,binutils,cifs-utils,i2c-tools,xdotool,gnupg,lsb-release,qemu-system-modules-opengl,socat,virt-viewer,spice-client-gtk,util-linux-extra,dbus-x11,sg3-utils,rpm")
    else
        package=("vim,ocl-icd-libopencl1,curl,openssh-server,net-tools,gir1.2-gst-plugins-bad-1.0,gir1.2-gst-plugins-base-1.0,gir1.2-gstreamer-1.0,gir1.2-gst-rtsp-server-1.0,gstreamer1.0-alsa,gstreamer1.0-gl,gstreamer1.0-gtk3,gstreamer1.0-opencv,gstreamer1.0-plugins-bad,gstreamer1.0-plugins-bad-apps,gstreamer1.0-plugins-base,gstreamer1.0-plugins-base-apps,gstreamer1.0-plugins-good,gstreamer1.0-plugins-ugly,gstreamer1.0-pulseaudio,gstreamer1.0-qt5,gstreamer1.0-rtsp,gstreamer1.0-tools,gstreamer1.0-wpe,gstreamer1.0-x,intel-media-va-driver-non-free,libdrm-amdgpu1,libdrm-common,libdrm-dev,libdrm-intel1,libdrm-nouveau2,libdrm-radeon1,libdrm-tests,libdrm2,libgstrtspserver-1.0-dev,libgstrtspserver-1.0-0,libgstreamer-gl1.0-0,libgstreamer-opencv1.0-0,libgstreamer-plugins-bad1.0-0,libgstreamer-plugins-bad1.0-dev,libgstreamer-plugins-base1.0-0,libgstreamer-plugins-base1.0-dev,libgstreamer-plugins-good1.0-0,libgstreamer-plugins-good1.0-dev,libgstreamer1.0-0,libgstreamer1.0-dev,libigdgmm-dev,libigdgmm12,libigfxcmrt-dev,libigfxcmrt7,libmfx-gen1.2,libtpms-dev,libtpms0,libva-dev,libva-drm2,libva-glx2,libva-wayland2,libva-x11-2,libva2,libwayland-bin,libwayland-client0,libwayland-cursor0,libwayland-dev,libwayland-doc,libwayland-egl-backend-dev,libwayland-egl1,libwayland-server0,libweston-9-0,libweston-9-dev,libxatracker2,linux-firmware,mesa-utils,mesa-va-drivers,mesa-vdpau-drivers,mesa-vulkan-drivers,libvpl-dev,libmfx-gen-dev,onevpl-tools,ovmf,ovmf-ia32,qemu,qemu-efi,qemu-block-extra,qemu-guest-agent,qemu-system,qemu-system-arm,qemu-system-common,qemu-system-data,qemu-system-gui,qemu-system-mips,qemu-system-misc,qemu-system-ppc,qemu-system-s390x,qemu-system-sparc,qemu-system-x86,qemu-system-x86-microvm,qemu-user,qemu-user-binfmt,qemu-utils,va-driver-all,vainfo,weston,xserver-xorg-core,libvirt0,libvirt-clients,libvirt-daemon,libvirt-daemon-config-network,libvirt-daemon-config-nwfilter,libvirt-daemon-driver-lxc,libvirt-daemon-driver-qemu,libvirt-daemon-driver-storage-gluster,libvirt-daemon-driver-storage-iscsi-direct,libvirt-daemon-driver-storage-rbd,libvirt-daemon-driver-storage-zfs,libvirt-daemon-driver-vbox,libvirt-daemon-driver-xen,libvirt-daemon-system,libvirt-daemon-system-systemd,libvirt-dev,libvirt-doc,libvirt-login-shell,libvirt-sanlock,libvirt-wireshark,libnss-libvirt,swtpm,swtpm-tools,bmap-tools,adb,autoconf,automake,libtool,cmake,g++,gcc,git,intel-gpu-tools,libssl3,libssl-dev,make,mosquitto,mosquitto-clients,build-essential,apt-transport-https,default-jre,docker-compose,ffmpeg,git-lfs,gnuplot,lbzip2,libglew-dev,libglm-dev,libsdl2-dev,mc,openssl,pciutils,python3-pandas,python3-pip,python3-seaborn,terminator,wmctrl,wayland-protocols,gdbserver,ethtool,iperf3,msr-tools,powertop,linuxptp,lsscsi,tpm2-tools,tpm2-abrmd,binutils,cifs-utils,i2c-tools,xdotool,gnupg,lsb-release,iproute2,socat,virt-viewer,spice-client-gtk")
    fi
    IFS=',' read -r -a package_list <<< "${package[*]}"

    echo "Installing following list of packages : ${package_list[*]}"
    for i in "${package_list[@]}"
    do
        run "echo \$i >> \"installedPackagesNameList.txt\""
    done
    run "apt-get update"
    if [[ $os_version == "UBUNTU_NOBLE" ]]
    then
        run "DEBIAN_FRONTEND=noninteractive apt-get install ${package_list[*]} -y --allow-downgrades"
    else
        run "apt-get install ${package_list[*]} -y --allow-downgrades"
    fi

    if [ "$platform" != "PTL" ]  && [ "$platform" != "WCL" ] ;then
        run "DEBIAN_FRONTEND=noninteractive apt-get install libbpf9999 xdp-tools ethtool iproute2 -y --allow-downgrades"
    fi
    run "echo '$(date): Packages Successfully Installed....................'"
    return 0
}


Installdebpackage()
{
    if [[ $os_version == "UBUNTU_NOBLE" ]]
    then
        debpackage=(
        "https://github.com/intel/intel-graphics-compiler/releases/download/v2.20.3/intel-igc-core-2_2.20.3+19972_amd64.deb"
        "https://github.com/intel/intel-graphics-compiler/releases/download/v2.20.3/intel-igc-opencl-2_2.20.3+19972_amd64.deb"
        "https://github.com/intel/compute-runtime/releases/download/25.40.35563.4/intel-ocloc_25.40.35563.4-0_amd64.deb"
        "https://github.com/intel/compute-runtime/releases/download/25.40.35563.4/intel-opencl-icd_25.40.35563.4-0_amd64.deb"
        "https://github.com/intel/compute-runtime/releases/download/25.40.35563.4/libze-intel-gpu1_25.40.35563.4-0_amd64.deb"
        "https://github.com/oneapi-src/level-zero/releases/download/v1.22.4/level-zero_1.22.4+u24.04_amd64.deb"
        "https://github.com/oneapi-src/level-zero/releases/download/v1.22.4/level-zero-devel_1.22.4+u24.04_amd64.deb")
    else
        debpackage=(
        "https://github.com/intel/intel-graphics-compiler/releases/download/igc-1.0.16510.2/intel-igc-core_1.0.16510.2_amd64.deb"
        "https://github.com/intel/intel-graphics-compiler/releases/download/igc-1.0.16510.2/intel-igc-opencl_1.0.16510.2_amd64.deb"
        "https://github.com/intel/compute-runtime/releases/download/24.13.29138.7/intel-level-zero-gpu_1.3.29138.7_amd64.deb"
        "https://github.com/intel/compute-runtime/releases/download/24.13.29138.7/intel-opencl-icd_24.13.29138.7_amd64.deb"
        "https://github.com/intel/linux-npu-driver/releases/download/v1.2.0/intel-driver-compiler-npu_1.2.0.20240404-8553879914_ubuntu22.04_amd64.deb"
        "https://github.com/intel/linux-npu-driver/releases/download/v1.2.0/intel-fw-npu_1.2.0.20240404-8553879914_ubuntu22.04_amd64.deb"
        "https://github.com/intel/linux-npu-driver/releases/download/v1.2.0/intel-level-zero-npu_1.2.0.20240404-8553879914_ubuntu22.04_amd64.deb"
        "https://github.com/oneapi-src/level-zero/releases/download/v1.16.1/level-zero_1.16.1+u22.04_amd64.deb")
    fi
    echo "Installing the following Debian packages:"
    for url in "${debpackage[@]}"; do
        echo "$url"
        run "wget ${url} --no-check-certificate"
    done
    if [ "$platform" == "PTL" ]
    then
        run "dpkg --purge --force-remove-reinstreq intel-driver-compiler-npu intel-fw-npu intel-level-zero-npu intel-level-zero-npu-dbgsym"
        run "wget https://github.com/intel/linux-npu-driver/releases/download/v1.28.0/linux-npu-driver-v1.28.0.20251218-20347000698-ubuntu2404.tar.gz"
        run "tar -xf linux-npu-driver-v1.28.0.20251218-20347000698-ubuntu2404.tar.gz"
        run "apt update"
        run "apt install libtbb12"
    fi
    run "dpkg -i *.deb"
    return 0
}


##################################################################
##....Function to build .deb  and install.......
build_and_install_kernel()
{
    echo "build_and_install_kernel argument \"$1\" \"$2\" \"$3\" \"$4\""
    release_tag="$1"
    image_name="$2"
    variant="$3"
    ubuntu_version="$4"
    echo "$release_tag and $image_name"
    echo "-----------------Installing dependencies-----------------"
    run "apt install git quilt libssl-dev kernel-wedge liblz4-tool libelf-dev flex bison -y --allow-downgrades"

    if [[ -d linux-kernel-overlay ]]
    then
        echo "Deleting existing kernel folder if any"
        rm -rf linux-kernel-overlay
    fi
    run "git clone https://github.com/intel/linux-kernel-overlay.git -b $release_tag"
    run "cd linux-kernel-overlay"
    run "sed -i 's|KERNELRELEASE=\`make kernelversion\`-\${customized_kver_string}-\${timestamp,,}|KERNELRELEASE=${image_name}|g' \"${PWD}/build.sh\""

    if [ "$ubuntu_version" == "UBUNTU_JAMMY" ];then
        run "./build.sh"
    else
        if [ "$variant" == "default" ]; then
            run "./build.sh -r no"
        elif [ "$variant" == "rt" ]; then
            run "./build.sh -r yes"
        fi
    fi

    run "dpkg -i linux-image-*.deb"
    run "dpkg -i linux-headers-*.deb"
    run "apt list --installed | grep linux-image"
    run "apt list --installed | grep linux-headers"
    return 0
}


##################################################################
##....Install kernel Overlays and update grub configuration.......
KernelUpdate()
{
    echo "$(date): Updating Kernel.................."
    echo "kernel version: $kernel_version"
    kernel_val="${kernel_version}-intel"
    image_name="${kernel_val}"
    build_and_install_kernel "$release_tag" "$image_name" "$kernel_variant" "$os_version"
    echo "All Kernel debs are installed..."
    if [ "$kernel_version" = "6.12" ]; then
        kernel_pkg=$(run "apt list --installed 2>/dev/null | grep linux-image-6.12 | grep -v dbg | cut -d/ -f1")
    else
        kernel_pkg=$(run "apt list --installed 2>/dev/null | grep linux-image-6.17 | grep -v dbg | cut -d/ -f1")
    fi

    # Extract just the version part after 'linux-image-'
    kernel_entry=${kernel_pkg#linux-image-}
    echo "The kernel entry is:"
    echo "$kernel_entry"
    echo "Update grub corresponding to kernels entry "
    run "sed -i 's/GRUB_DEFAULT=.*/GRUB_DEFAULT=\"Advanced options for Ubuntu>Ubuntu, with Linux ${kernel_entry}\"/' /etc/default/grub"
    run "sed -e 's@^GRUB_TIMEOUT_STYLE=hidden@# GRUB_TIMEOUT_STYLE=hidden@' -e 's@^GRUB_TIMEOUT=0@GRUB_TIMEOUT=5@g' -i /etc/default/grub"
    if [ "$platform" == "PTL" ] || [ "$platform" == "WCL" ] ; then
        if [ "$kernel_variant" == "rt" ]; then
            run "sudo sed -i 's/GRUB_CMDLINE_LINUX=.*/GRUB_CMDLINE_LINUX=\"modprobe.blacklist=i915 processor.max_cstate=0 intel.max_cstate=0 processor_idle.max_cstate=0 intel_idle.max_cstate=0 clocksource=tsc tsc=reliable nowatchdog intel_pstate=disable idle=poll nosmt isolcpus=2,3 rcu_nocbs=2,3 rcupdate.rcu_cpu_stall_suppress=1 rcu_nocb_poll irqaffinity=0 mce=off hpet=disable numa_balancing=disable igb.blacklist=no nmi_watchdog=0 nosoftlockup\"/' /etc/default/grub"
        else
            run "sudo sed -i 's/GRUB_CMDLINE_LINUX=.*/GRUB_CMDLINE_LINUX=\"xe.max_vfs=7 xe.force_probe=* modprobe.blacklist=i915 udmabuf.list_limit=8192 console=tty0 console=ttyS0,115200n8\"/' /etc/default/grub"
        fi
    else
        if [ "$kernel_variant" == "rt" ]; then
            run "sed -i 's/GRUB_CMDLINE_LINUX=.*/GRUB_CMDLINE_LINUX=\"i915.enable_guc=3 i915.max_vfs=7 i915.force_probe=* udmabuf.list_limit=8192 processor.max_cstate=0 intel.max_cstate=0 processor_idle.max_cstate=0 intel_idle.max_cstate=0 clocksource=tsc tsc=reliable nowatchdog intel_pstate=disable idle=poll noht isolcpus=2,3 rcu_nocbs=2,3 rcupdate.rcu_cpu_stall_suppress=1 rcu_nocb_poll irqaffinity=0 i915.enable_rc6=0 i915.enable_dc=0 i915.disable_power_well=0 mce=off hpet=disable numa_balancing=disable igb.blacklist=no efi=runtime art=virtallow iommu=pt nmi_watchdog=0 nosoftlockup hugepages=1024 console=tty0 console=ttyS0,115200n8 intel_iommu=on\"/' /etc/default/grub"
        else
            run "sed -i 's/GRUB_CMDLINE_LINUX=.*/GRUB_CMDLINE_LINUX=\"i915.enable_guc=3 i915.max_vfs=7 i915.force_probe=* udmabuf.list_limit=8192 console=tty0 console=ttyS0,115200n8\"/' /etc/default/grub"
        fi
    fi
    run "update-grub"
    return 0
}

##################################################################
##.............. Validate installed package ......................
function ValidatePackages()
{
    declare -a arr=( "kernels" "main" "multimedia" "non-free" )
    file="installedPackagesVersionList.txt"

    #get installed package name and version.
    run "apt list --installed 2>&1 | tee /opt/Bom-list.txt"

    #get available package name and version from artifactory
    for i in "${arr[@]}"
    do
        if [[ $os_version == "UBUNTU_NOBLE" ]]
        then
            run "wget ${ppa_url}/dists/noble/$i/binary-amd64/Packages -O ./Packages_$i"
        else
            run "wget ${ppa_url}/dists/jammy/$i/binary-amd64/Packages -O ./Packages_$i"
        fi
    done

    while read -r packageLine; do
        for i in "${arr[@]}"
        do
            packageFound=0
            while read -r line; do
                str="Package: $packageLine"
                if [ "$str" == "$line" ]; then
                    packageName=$(echo "$line" | awk -F ": " '{ print $2 }')
                    packageFound=1
                elif [ $packageFound -eq 1 ]; then
                    str1=$(echo "$line" | grep -i "Version:")
                    if [ -n "$str1" ]; then
                        version=$(echo "$line" | awk -F ": " '{ print $2 }')
                        echo "$packageName=$version" >> $file
                        break
                    fi
                fi
            done < "./Packages_$i"
        done
    done < "./installedPackagesNameList.txt"

    #Validate Installed and available in artifactory package
    while read -r line; do
        package_name=$(echo "$line" | cut -d'=' -f1)
        installer_version=$(echo "$line" | cut -d'=' -f2)
        if grep -q "${package_name}/" /opt/Bom-list.txt; then
            installed_version=$(grep "${package_name}/" /opt/Bom-list.txt | awk '{print $2}')
            echo "Package Name: $package_name ==> Installed_Version: $installed_version ==> Installer_Version: $installer_version"
            if [ "$installed_version" != "$installer_version" ]; then
                echo "ERROR: $package_name is not identical!"
                echo "ERROR: SUT installed version : $installed_version"
                echo "ERROR: Version present in artifactory: $installer_version"
                exit 1
            fi
        else
            echo "ERROR: $package_name package not found in Bom-list.txt"
            exit 1
        fi
    done <$file
    echo "All installed version is identical to the version mentioned in installer.sh"

    return 0
}

echo "Script execution argument passed: sudo $0 $*" | tee -a "$current_workspace/$(date +%Y%m%d)_${kernel_variant}_installer.log" || exit 1
PPAUpdate 2>&1 | tee -a "$current_workspace/$(date +%Y%m%d)_${kernel_variant}_installer.log" || exit 1
InstallPackage 2>&1 | tee -a "$current_workspace/$(date +%Y%m%d)_${kernel_variant}_installer.log" || exit 1
Installdebpackage 2>&1 | tee -a "$current_workspace/$(date +%Y%m%d)_${kernel_variant}_installer.log" || exit 1
KernelUpdate 2>&1 | tee -a "$current_workspace/$(date +%Y%m%d)_${kernel_variant}_installer.log" || exit 1
ValidatePackages 2>&1 | tee -a "$current_workspace/$(date +%Y%m%d)_${kernel_variant}_installer.log" || exit 1
echo "Rebooting Device now" | tee -a "$current_workspace/$(date +%Y%m%d)_${kernel_variant}_installer.log"
reboot
