#!/bin/bash
# shellcheck disable=SC1091
set -euo pipefail # enables strict error handling in shell scripts

# Function to display usage information
usage() {
  cat <<EOF
Usage: $0 [vpro]

This script installs vPro components (LMS and RPC).
The 'vpro' argument is optional and default.

Examples:
  $0             # Install vPro components
  $0 vpro        # Install vPro components
EOF
  exit 1
}

# Parse command line arguments FIRST - before any other operations
PROFILE="vpro"
if [ $# -eq 0 ]; then
  PROFILE="vpro"
elif [ $# -eq 1 ]; then
  case "${1,,}" in
    vpro)
      PROFILE="vpro"
      ;;
    -h|--help|help)
      usage
      ;;
    *)
      echo "Error: Unknown argument '$1'"
      usage
      ;;
  esac
else
  echo "Error: Too many arguments"
  usage
fi

echo "Installing vPro components (Profile: $PROFILE)"

# Version constants
readonly LMS_VERSION="2506.0.0.0"
readonly LMS_CHECKSUM="bfdcbfb6b2a739321998a0772767c1532ede70f4bd38cdbe48488b59d118a086"
readonly RPC_VERSION="2.48.10"
readonly RPC_CHECKSUM="01cf33b637631b6a27e20e46bfe046f6b1b3f3ac75d98825b7698488a287b557"

# Initialize sudo credential cache
echo "Authentication required for system configuration."
if ! sudo -v; then
  echo "Error: Failed to obtain sudo privileges"
  exit 1
fi

# Keep sudo credentials fresh in background
(
  while true; do
    sleep 50
    sudo -v
  done
) &
SUDO_REFRESH_PID=$!

# Cleanup function
cleanup() {
  if [ -n "${SUDO_REFRESH_PID:-}" ]; then
    kill "$SUDO_REFRESH_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

# Delete a folder if it exists
delete_folder_if_exists() {
  local folder_name="$1"
  if [ -d "$folder_name" ]; then
    echo "Directory '$folder_name' exists. Removing the existing directory."
    rm -rf "$folder_name"
  else
    echo "Directory '$folder_name' does not exist."
  fi
}

# Create a new folder
create_folder() {
  local folder_name="$1"
  echo "Creating directory '$folder_name'."
  mkdir -p "$folder_name"
}

echo 'NTP=corp.intel.com' | sudo tee -a /etc/systemd/timesyncd.conf > /dev/null

STATUS_DIR=$(pwd)
LOGFILE="$STATUS_DIR/output.log"
exec > >(tee -a "$LOGFILE") 2>&1

declare -i proxy_build_status=0
declare -i build_dependency_build_status=0
declare -i ca_certificate_installation_build_status=0
declare -i lms_build_status=0
declare -i rpc_build_status=0
declare -i reboot_continue_build_status=0

SETUP_STATUS_FILENAME="install_pkgs_status"
PACKAGE_BUILD_FILENAME="package_build_time"
STATUS_DIR_FILE_PATH=$STATUS_DIR/$SETUP_STATUS_FILENAME
PACKAGE_BUILD_TIME_FILE=$STATUS_DIR/$PACKAGE_BUILD_FILENAME

touch "$PACKAGE_BUILD_TIME_FILE"
if [ -e "$STATUS_DIR_FILE_PATH" ]; then
  echo "File $STATUS_DIR_FILE_PATH exists"
else
  touch "$STATUS_DIR_FILE_PATH"
  {
  
echo "proxy_build_status=0"
echo "build_dependency_build_status=0"
echo "ca_certificate_installation_build_status=0"
echo "lms_build_status=0"
echo "rpc_build_status=0"
echo "reboot_continue_build_status=0"
  }>> "$STATUS_DIR_FILE_PATH"
fi

#shellcheck source=/dev/null
source "$STATUS_DIR_FILE_PATH"

Proxy_Settings () {
echo "Installing Proxy_Settings"
if [ "$proxy_build_status" -ne 1 ]; then
  SECONDS=0
  echo "*************************"
  echo "     Proxy Settings      "
  echo "*************************"

  http_proxy="http://proxy-dmz.intel.com:911"
  https_proxy="http://proxy-dmz.intel.com:912"
  ftp_proxy="http://proxy-dmz.intel.com:911"
  socks_proxy="socks://proxy-dmz.intel.com:1080"
  no_proxy="localhost,*.intel.com,*intel.com,192.168.0.0/16,172.16.0.0/12,127.0.0.0/8,10.0.0.0/8,/var/run/docker.sock,.internal"
  HTTP_PROXY="http://proxy-dmz.intel.com:911"
  HTTPS_PROXY="http://proxy-dmz.intel.com:912"
  NO_PROXY="localhost,*.intel.com,*intel.com,192.168.0.0/16,172.16.0.0/12,127.0.0.0/8,10.0.0.0/8,/var/run/docker.sock"

  if grep -q "http_proxy" /etc/environment && \
      grep -q "https_proxy" /etc/environment && \
      grep -q "ftp_proxy" /etc/environment && \
      grep -q "no_proxy" /etc/environment && \
      grep -q "HTTP_PROXY" /etc/environment && \
      grep -q "LD_LIBRARY_PATH" /etc/environment; then
    echo "Proxies are already present in /etc/environment."
  else
    {
      echo http_proxy=$http_proxy
      echo https_proxy=$https_proxy
      echo ftp_proxy=$ftp_proxy
      echo socks_proxy="$socks_proxy"
      echo no_proxy="$no_proxy"
      echo HTTP_PROXY=$HTTP_PROXY
      echo HTTPS_PROXY=$HTTPS_PROXY
      echo NO_PROXY="$NO_PROXY"
      if ! grep -q "/usr/lib/x86_64-linux-gnu/" /etc/environment; then
        echo "LD_LIBRARY_PATH=\${LD_LIBRARY_PATH:+\$LD_LIBRARY_PATH:}/usr/lib/x86_64-linux-gnu/" | sudo tee -a /etc/environment > /dev/null
      fi
    } | sudo tee -a /etc/environment > /dev/null
    echo "Proxies added to /etc/environment."
  fi
  #shellcheck source=/dev/null
  source /etc/environment
  export http_proxy https_proxy ftp_proxy socks_proxy no_proxy HTTP_PROXY HTTPS_PROXY NO_PROXY

  sed -i 's/proxy_build_status=0/proxy_build_status=1/g' "$STATUS_DIR_FILE_PATH"

  elapsedseconds=$SECONDS
  echo "proxy build time = $((elapsedseconds))" >> "$PACKAGE_BUILD_TIME_FILE"

fi

}

Install_Build_Dependencies () {
echo "Installing build dependencies..."
if [ "$build_dependency_build_status" -ne 1 ]; then
  SECONDS=0
  echo "*************************"
  echo "   Build Dependencies    "
  echo "*************************"
  sudo apt-get update
  sudo apt-get install -y bash python3 python3-dev ca-certificates wget python3-pip git \
    build-essential cmake meson pkg-config software-properties-common

  echo "Build essentials installation done"
  sed -i 's/build_dependency_build_status=0/build_dependency_build_status=1/g' "$STATUS_DIR_FILE_PATH"
  elapsedseconds=$SECONDS
  echo "build_dependency build time = $((elapsedseconds))" >> "$PACKAGE_BUILD_TIME_FILE"

fi

}

CA_Cert_Installation () {
echo "Installing CA certificates..."
if [ "$ca_certificate_installation_build_status" -ne 1 ]; then
  SECONDS=0
  echo "*************************"
  echo "    CA Certificates      "
  echo "*************************"

  cd "$STATUS_DIR" || exit 1
  delete_folder_if_exists "ca_cert"
  create_folder "ca_cert"
  cd ca_cert || exit 1

  for cert in IntelCA5A-base64.crt IntelCA5B-base64.crt IntelSHA256RootCA-base64.crt; do
    wget "http://owrdropbox.intel.com/dropbox/public/Ansible/certificates/$cert" --no-proxy
  done

  sudo cp Intel* /usr/local/share/ca-certificates/
  sudo update-ca-certificates

  cd "$STATUS_DIR" || exit 1
  delete_folder_if_exists "ca_cert"

sed -i 's/ca_certificate_installation_build_status=0/ca_certificate_installation_build_status=1/g' "$STATUS_DIR_FILE_PATH"

elapsedseconds=$SECONDS
echo "ca_certificate_installation build time = $((elapsedseconds))" >> "$PACKAGE_BUILD_TIME_FILE"

fi

}

Install_vPRO_Components () {
  echo "Installing vPRO components..."
  if [ "$lms_build_status" -ne 1 ]; then
    SECONDS=0
    cd "$STATUS_DIR" || exit 1
    echo "***************************************"
    echo "  Installing vPRO Component LMS        "
    echo "***************************************"

      # Install the dependencies for building LMS
      echo "Installing LMS build dependencies..."
      sudo apt-get update
      sudo apt-get install -y \
        libace-dev cmake python3 libglib2.0-dev libcurl4-openssl-dev libxerces-c-dev libnl-3-dev libnl-route-3-dev libxml2-dev libidn2-0-dev xsltproc docbook-xsl devscripts
      
      # Download, build and install LMS
      local expected_checksum="$LMS_CHECKSUM"

      curl -fsSL --connect-timeout 30 --max-time 300 \
        "https://github.com/intel/lms/archive/refs/tags/v${LMS_VERSION}.tar.gz" \
        -o "v${LMS_VERSION}.tar.gz"

      if [ -f "v${LMS_VERSION}.tar.gz" ]; then
        local actual_checksum
        actual_checksum=$(sha256sum "v${LMS_VERSION}.tar.gz" | awk '{print $1}')
        if [ "$actual_checksum" != "$expected_checksum" ]; then
          echo "ERROR: Checksum mismatch. Expected: $expected_checksum, Got: $actual_checksum"
          rm -f "v${LMS_VERSION}.tar.gz"
          exit 1
        fi
        echo "Checksum verification successful."

        tar -xzf "v${LMS_VERSION}.tar.gz"
        rm -f "v${LMS_VERSION}.tar.gz"
        
        if [ ! -d "lms-${LMS_VERSION}" ]; then
          echo "ERROR: LMS source directory not found after extraction"
          exit 1
        fi
        
        cd "lms-${LMS_VERSION}" || exit 1
        export LMS_ROOT="$PWD"
        
        mkdir -p build || { echo "ERROR: Failed to create build directory"; exit 1; }
        cd build || exit 1

    cmake -Wno-dev -DBUILD_SHARED_LIBS=OFF -DNETWORK_NM=OFF \
        -DNETWORK_CN=OFF -DCMAKE_INSTALL_PREFIX=/usr "$LMS_ROOT"

    if ! make -j"$(($(nproc) / 2))"; then
      echo "ERROR: LMS build failed"
      exit 1
    fi

    if ! make package; then
      echo "ERROR: LMS package creation failed"
      exit 1
    fi

        local lms_package="./lms-${LMS_VERSION%%.*}.0.0-Linux.deb"
        if [ -f "$lms_package" ]; then
          echo "Installing LMS package....."
          if sudo apt-get install -y -o Dpkg::Options::="--force-confnew" "$lms_package"; then
            echo "LMS package installed successfully"
            rm -f "$lms_package"

            # Start and enable LMS service
            echo "Starting LMS service..."
            sudo systemctl unmask lms.service 2>/dev/null || true
            sudo systemctl daemon-reload
            sudo systemctl enable lms.service
            sudo systemctl start lms.service

            # Give the service a moment to start
            sleep 2
          else
            echo "WARNING: Failed to install LMS package. Platform manageability features may not work properly."
          fi
        else
          echo "ERROR: LMS package not found at $lms_package. Build failed."
          exit 1
        fi
      else
        echo "ERROR: Failed to download LMS source. Aborting installation."
        exit 1
      fi

      # Verify LMS installation
      echo -e "\n Verifying LMS installation..."
      if sudo systemctl is-active lms.service --quiet; then
        echo "✓ LMS service is running successfully"
        sudo systemctl status lms.service --no-pager --lines=10
      else
        echo "✗ LMS service is not running"
        sudo systemctl status lms.service --no-pager --lines=10
        echo ""
        echo "Note: LMS service may fail if Intel ME/AMT is not available or properly configured on this system."
        echo "This does not affect other vPRO components like RPC."
      fi
      echo "✓ LMS Installation completed."

sed -i 's/lms_build_status=0/lms_build_status=1/g' "$STATUS_DIR_FILE_PATH"

elapsedseconds=$SECONDS
echo "lms build time = $((elapsedseconds))" >> "$PACKAGE_BUILD_TIME_FILE"

fi
  if [ "$rpc_build_status" -ne 1 ]; then
    SECONDS=0
    cd "$STATUS_DIR" || exit 1
    echo "***************************************"
    echo "     Installing vPRO Component RPC     "
    echo "***************************************"

      # Download RPC binary
      echo "Downloading RPC binary...."
      local expected_checksum="$RPC_CHECKSUM"
      curl -LO "https://github.com/device-management-toolkit/rpc-go/releases/download/v${RPC_VERSION}/rpc_linux_x64.tar.gz"

      if [ -f "rpc_linux_x64.tar.gz" ]; then
        local actual_checksum
        actual_checksum=$(sha256sum "rpc_linux_x64.tar.gz" | awk '{print $1}')
        if [ "$actual_checksum" != "$expected_checksum" ]; then
          echo "ERROR: Checksum mismatch. Expected: $expected_checksum, Got: $actual_checksum"
          rm -f "rpc_linux_x64.tar.gz"
          exit 1
        fi
        echo "Checksum verification successful."
        sudo tar -xvf rpc_linux_x64.tar.gz -C /usr/bin
        rm -rf rpc_linux_x64.tar.gz
        sudo mv /usr/bin/rpc_linux_x64 /usr/bin/rpc
        sudo chmod +x /usr/bin/rpc

        # Verify RPC installation
        echo -e "\n Verifying RPC installation..."
        if sudo /usr/bin/rpc amtinfo >/dev/null 2>&1; then
          echo "✓ RPC installed and working successfully"
          echo -e "\n AMT Information:"
          sudo /usr/bin/rpc amtinfo
        else
          echo "✗ RPC verification failed. AMT may not be available or RPC binary not working correctly."
          echo "Note: This is expected if AMT is not provisioned on this system."
        fi
      else
        echo "ERROR: Downloaded file does not exist. Aborting installation."
        exit 1
      fi
      echo "✓ RPC installation completed successfully."

sed -i 's/rpc_build_status=0/rpc_build_status=1/g' "$STATUS_DIR_FILE_PATH"

elapsedseconds=$SECONDS
echo "rpc build time = $((elapsedseconds))" >> "$PACKAGE_BUILD_TIME_FILE"

fi

}

reboot_continue_installation () {
  echo "Finalizing installation..."
  if [ "$reboot_continue_build_status" -ne 1 ]; then
    SECONDS=0
    echo "***********************"
    echo "         Reboot        "
    echo "***********************"
    echo -e "\nThe EEF Device Management Profile installation has been completed successfully."
    echo -e "A system reboot is required to ensure that all modifications take effect.\n"
    
    # Interactive prompt for user choice
    read -r -p "Do you want to reboot the system now? (y/n): " choice
    if [[ "$choice" == "y" || "$choice" == "Y" ]]; then
      echo -e "\n*** Initiating system reboot... ***"
      sudo reboot
    else
      echo -e "\nReboot has been canceled. Continuing with the module installation..."
      echo -e "\nNote: A system reboot is required after the installation is complete to apply the changes.\n"
    fi

sed -i 's/reboot_continue_build_status=0/reboot_continue_build_status=1/g' "$STATUS_DIR_FILE_PATH"

elapsedseconds=$SECONDS
echo "reboot_continue build time = $((elapsedseconds))" >> "$PACKAGE_BUILD_TIME_FILE"

fi

}

Proxy_Settings
Install_Build_Dependencies
CA_Cert_Installation
Install_vPRO_Components
reboot_continue_installation
