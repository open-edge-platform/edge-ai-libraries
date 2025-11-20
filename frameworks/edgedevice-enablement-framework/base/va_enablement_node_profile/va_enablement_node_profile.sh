#!/bin/bash
# shellcheck disable=SC1091
set -euo pipefail # enables strict error handling in shell scripts

# Function to display usage information
usage() {
  cat <<EOF
Usage: $0 [PROFILE]

PROFILE options:
  (no argument)  - Install all components (default)
  vpp            - Install VPP components
  tfcc           - Install TFCC components
  magic9         - Install Magic9 components

Examples:
  $0             # Install all components
  $0 vpp         # Install VPP components only
  $0 tfcc        # Install TFCC components only
  $0 magic9     # Install Magic9 components only
EOF
  exit 1
}

# Parse command line arguments FIRST - before any other operations
PROFILE="default"
if [ $# -eq 0 ]; then
  PROFILE="default"
elif [ $# -eq 1 ]; then
  case "${1,,}" in
    vpp)
      PROFILE="vpp"
      ;;
    tfcc)
      PROFILE="tfcc"
      ;;
    magic9)
      PROFILE="magic9"
      ;;
    -h|--help|help)
      usage
      ;;
    *)
      echo "Error: Unknown profile '$1'"
      usage
      ;;
  esac
else
  echo "Error: Too many arguments"
  usage
fi

echo "Selected profile: $PROFILE"

# Prompt for sudo password at the beginning
echo "Please enter your sudo password:"
read -r -s SUDO_PASSWORD

# Cleanup function to ensure IGC restrictions are restored on script exit
cleanup_on_exit() {
  echo "Script interrupted. Ensuring IGC restrictions are restored..."
  if [ -f "/etc/apt/preferences.d/temp-gpu-install" ]; then
    echo "$SUDO_PASSWORD" | sudo -S rm -f /etc/apt/preferences.d/temp-gpu-install
    set_intel_repo_priorities
    echo "IGC restrictions restored."
  fi
}

# Set trap to call cleanup on script exit/interruption
trap cleanup_on_exit EXIT INT TERM

# Path to the openssl.cnf file
OPENSSL_CONF_PATH="/usr/lib/ssl/openssl.cnf"

# Backup path for the openssl.cnf file in the current directory
BACKUP_PATH="./openssl.cnf.backup"

# Create a backup of the original openssl.cnf file
if [ ! -f "$BACKUP_PATH" ]; then
  echo "Creating a backup of the original openssl.cnf file..."
  echo "$SUDO_PASSWORD" | sudo -S cp "$OPENSSL_CONF_PATH" "$BACKUP_PATH"
else
  echo "Backup already exists. Skipping backup creation."
fi

# Function to update or append a configuration line within a section
update_or_append() {
local file="$1"
local section="$2"
local setting="$3"
local value="$4"

# Check if the section exists
if ! grep -q "^\[$section\]" "$file"; then
  # Section does not exist, append it to the file
  echo -e "\n[$section]" | sudo tee -a "$file" > /dev/null
fi

# Check if the setting exists within the section
if echo "$SUDO_PASSWORD" | sudo -S grep -q -P "^\s*$setting\s*=" "$file"; then
  # Setting exists, update it in place
  echo "$SUDO_PASSWORD" | sudo -S sed -i -r "/^\[$section\]/,/^$/ s|^\s*($setting\s*=\s*).*$|\1$value|" "$file"
else
  # Setting does not exist, append it within the section
  echo "$SUDO_PASSWORD" | sudo -S sed -i "/^\[$section\]/a $setting = $value" "$file"
fi
}

# Update the openssl.cnf file with the desired settings
echo "Updating the openssl.cnf file with new TLS settings..."
update_or_append "$OPENSSL_CONF_PATH" "system_default_sect" "MinProtocol" "TLSv1.2"
update_or_append "$OPENSSL_CONF_PATH" "system_default_sect" "MaxProtocol" "TLSv1.3"
update_or_append "$OPENSSL_CONF_PATH" "system_default_sect" "Ciphersuites" "TLS_AES_256_GCM_SHA384"
update_or_append "$OPENSSL_CONF_PATH" "system_default_sect" "CipherString" "ECDHE-RSA-AES256-GCM-SHA384"
echo "OpenSSL configuration has been updated."

# Function to restore the original openssl.cnf file
restore_openssl_conf() {
if [ -f "$BACKUP_PATH" ]; then
  echo "$SUDO_PASSWORD" | sudo -S cp "$BACKUP_PATH" "$OPENSSL_CONF_PATH"
  echo "Original OpenSSL configuration has been restored from backup."
else
  echo "Backup file does not exist. Cannot restore original configuration."
fi
}

VERSION_FILE="./package-versions.txt"

# Function to get the currently installed version of a package
get_installed_version() {
  local pkg="$1"
  dpkg-query -W -f='${Version}' "$pkg" 2>/dev/null || echo ""
}

# Store the currently installed versions
echo "Storing current versions in $VERSION_FILE"
touch "$VERSION_FILE"

# function to handle critical sections
disable_strict_mode() {
  set +euo pipefail
}

enable_strict_mode() {
  set -euo pipefail
}

check_installed() {
local pkg="$1"
local current_version
current_version=$(get_installed_version "$pkg")
if [ -n "$current_version" ]; then
  echo "$pkg=$current_version" >> "$VERSION_FILE"
  echo "Stored current version of $pkg ($current_version)"
else
  echo "No currently installed version of $pkg found"
fi
}

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

# Clean up failed DKMS installation
cleanup_failed_dkms() {
  local pkg_name="$1"
  echo "Cleaning up failed DKMS installation for $pkg_name..."
  # Remove the package with force to handle broken states
  echo "$SUDO_PASSWORD" | sudo -S dpkg --remove --force-remove-reinstreq "$pkg_name" 2>/dev/null || true
  # Clean any remaining DKMS modules
  echo "$SUDO_PASSWORD" | sudo -S dkms status 2>/dev/null | grep "$pkg_name" | while read -r line; do
    module_info=$(echo "$line" | cut -d',' -f1)
    if [[ -n "$module_info" ]]; then
      echo "Removing DKMS module: $module_info"
      echo "$SUDO_PASSWORD" | sudo -S dkms remove "$module_info" --all 2>/dev/null || true
    fi
  done
  echo "DKMS cleanup completed for $pkg_name"
}

# Check if a package is installed
is_installed() {
  local pkg="$1"
  dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q "install ok installed"
}

# Function to set repository priorities and resolve conflicts
set_intel_repo_priorities() {
  echo "Setting Intel repository priorities and cleaning conflicts..."
  # Remove conflicting IGC packages (both old and new versions)
  echo "Resolving IGC package conflicts..."
  echo "$SUDO_PASSWORD" | sudo -S apt-get remove -y libigc1 libigdfcl1 libigc2 libigdfcl2 intel-igc-core intel-igc-opencl 2>/dev/null || true

  # Set repository priorities
  echo "$SUDO_PASSWORD" | sudo -S bash -c 'cat > /etc/apt/preferences.d/intel-priorities << EOF
# Intel Graphics PPA priority (highest)
Package: *
Pin: release o=LP-PPA-kobuk-team-intel-graphics
Pin-Priority: 1100

# SED repository priority
Package: *
Pin: origin eci.intel.com
Pin-Priority: 1200

# Intel OneAPI repository priority
Package: *
Pin: origin apt.repos.intel.com
Pin-Priority: 1050

# Intel GPU repository priority
Package: *
Pin: origin repositories.intel.com
Pin-Priority: 1000

# Prevent IGC conflicts (both old and new package names)
Package: libigc1 libigdfcl1 libigc2 libigdfcl2 intel-igc-core intel-igc-opencl
Pin: version *
Pin-Priority: -1
EOF'

  echo "Repository priorities set successfully"
}

# Function to check if repository priorities are set correctly
verify_repo_priorities() {
  if [ ! -f "/etc/apt/preferences.d/intel-priorities" ]; then
    echo "Warning: Intel repository priorities not set. Attempting to set them..."
    set_intel_repo_priorities
    return $?
  fi
  return 0
}

# Function to handle apt conflicts more robustly
handle_apt_conflicts() {
  local package_list="$1"
  echo "Installing packages with conflict resolution: $package_list"
  # First attempt with conflict resolution
  if ! echo "$SUDO_PASSWORD" | sudo -S apt-get install -y --allow-downgrades "$package_list"; then
    echo "First attempt failed, trying with dependency fixes..."
    echo "$SUDO_PASSWORD" | sudo -S apt-get --fix-broken install -y
    echo "$SUDO_PASSWORD" | sudo -S apt-get install -y --allow-downgrades --force-yes "$package_list"
  fi
}

# Reusable function to setup Intel repositories
setup_intel_gpu_repositories() {
  local setup_oneapi="${1:-true}"
  local setup_graphics="${2:-true}"

  if [[ "$setup_oneapi" == "true" ]]; then
    if [ ! -f "/etc/apt/sources.list.d/intel-oneapi.list" ]; then
      echo "Setting up Intel OneAPI repository..."
      wget -qO - https://apt.repos.intel.com/intel-gpg-keys/GPG-PUB-KEY-INTEL-SW-PRODUCTS.PUB | sudo gpg --yes --dearmor --output /usr/share/keyrings/intel-sw-products.gpg
      echo "deb [signed-by=/usr/share/keyrings/intel-sw-products.gpg] https://apt.repos.intel.com/oneapi all main" | sudo tee /etc/apt/sources.list.d/intel-oneapi.list
    else
      echo "Intel OneAPI repository already configured"
    fi
  fi

  if [[ "$setup_graphics" == "true" ]]; then
    if [ ! -f "/etc/apt/sources.list.d/intel-gpu-noble.list" ]; then
      echo "Setting up Intel Graphics repository..."
      wget -qO - https://repositories.intel.com/gpu/intel-graphics.key | sudo gpg --yes --dearmor --output /usr/share/keyrings/intel-graphics.gpg
      echo "deb [arch=amd64,i386 signed-by=/usr/share/keyrings/intel-graphics.gpg] https://repositories.intel.com/gpu/ubuntu noble client" | sudo tee /etc/apt/sources.list.d/intel-gpu-noble.list
    else
      echo "Intel Graphics repository already configured"
    fi
  fi

  echo "$SUDO_PASSWORD" | sudo -S apt-get update

  # Simplified verification - just check if priorities file exists
  if [ -f "/etc/apt/preferences.d/intel-priorities" ]; then
    echo "✓ Intel repository priorities configured"
  else
    echo "⚠ Warning: Intel repository priorities not found, setting them..."
    set_intel_repo_priorities
  fi
}

# Function to install Level-Zero packages with unified approach
install_level_zero_unified() {
  local context="${1:-general}"
  echo "Installing Level-Zero packages for $context..."

  # Check what's already installed - Updated logic
  if is_installed "intel-level-zero-gpu"; then
    echo "[SKIP] Intel Level-Zero GPU package already installed"
    return 0
  elif is_installed "libze1" && is_installed "libze-intel-gpu1"; then
    echo "[SKIP] LibZE Level-Zero packages already installed"
    return 0
  fi

  # Remove conflicting packages first
  echo "Removing any conflicting Level-Zero packages..."
  echo "$SUDO_PASSWORD" | sudo -S apt-get remove -y libze1 libze-dev libze-intel-gpu1 level-zero level-zero-devel 2>/dev/null || true

  # Try Method 1: Install intel-level-zero-gpu (preferred)
  echo "Attempting to install Intel Level-Zero GPU package..."
  if echo "$SUDO_PASSWORD" | sudo -S apt-get install -y --allow-downgrades intel-level-zero-gpu; then
    echo "✓ Successfully installed intel-level-zero-gpu"
    return 0
  fi

  # Try Method 2: Install libze packages (reliable fallback)
  echo "Installing LibZE Level-Zero packages as fallback..."
  if echo "$SUDO_PASSWORD" | sudo -S apt-get install -y --allow-downgrades libze1 libze-intel-gpu1; then
    echo "✓ Successfully installed LibZE Level-Zero packages"
    return 0
  fi

  # Try Method 3: Manual installation for specific contexts
  if [[ "$context" == "npu" ]]; then
    echo "Attempting manual Level-Zero installation for NPU..."
    wget_from_github "https://github.com/oneapi-src/level-zero/releases/download/v1.24.2/level-zero_1.24.2+u24.04_amd64.deb" "level-zero_1.24.2+u24.04_amd64.deb"
    if echo "$SUDO_PASSWORD" | sudo -S dpkg -i --force-overwrite level-zero*.deb; then
      echo "$SUDO_PASSWORD" | sudo -S apt --fix-broken install -y
      rm level-zero*.deb
      echo "✓ Successfully installed Level-Zero via manual method"
      return 0
    fi
    rm -f level-zero*.deb
  fi

  echo "⚠ Warning: All Level-Zero installation methods failed"
  return 1
}

# Function to manage IGC packages during installation
manage_igc_packages() {
  local action="${1:-install}"  # install, allow, restrict
  local context="${2:-general}" # general, gpu, npu, xpu

  case "$action" in
    "allow")
      echo "Temporarily allowing IGC packages for $context installation..."
      echo "$SUDO_PASSWORD" | sudo -S rm -f /etc/apt/preferences.d/intel-priorities
      echo "$SUDO_PASSWORD" | sudo -S bash -c 'cat > /etc/apt/preferences.d/temp-gpu-install << EOF
Package: libigc1 libigdfcl1 libigc2 libigdfcl2 intel-igc-core intel-igc-opencl
Pin: version *
Pin-Priority: 2000

Package: *
Pin: release o=LP-PPA-kobuk-team-intel-graphics
Pin-Priority: 1900
EOF'
      echo "$SUDO_PASSWORD" | sudo -S apt-get update
      ;;

    "install")
      echo "Installing IGC packages for $context..."
      # Try different methods in order of preference
      if echo "$SUDO_PASSWORD" | sudo -S apt-get install -y --allow-downgrades libigc2 libigdfcl2; then
        echo "✓ Installed IGC v2 packages"
      elif echo "$SUDO_PASSWORD" | sudo -S apt-get install -y --allow-downgrades libigc1 libigdfcl1; then
        echo "✓ Installed IGC v1 packages"
      else
        echo "⚠ Warning: Could not install IGC packages"
        return 1
      fi
      ;;

    "restrict")
      echo "Restoring IGC package restrictions..."
      echo "$SUDO_PASSWORD" | sudo -S rm -f /etc/apt/preferences.d/temp-gpu-install
      set_intel_repo_priorities
      echo "$SUDO_PASSWORD" | sudo -S apt-get update
      ;;
  esac
}

# Stabilize the Current kernel version at the time of installation
keep_current_kernel_version() {
  local current_kernel
  current_kernel=$(uname -r)
  echo "Keep the current kernel version: $current_kernel"
  echo "$SUDO_PASSWORD" | sudo -S apt-mark hold "linux-image-generic" "linux-headers-generic"
  echo "$SUDO_PASSWORD" | sudo -S apt-mark hold "linux-image-$current_kernel" "linux-headers-$current_kernel"
}

# Setup Grub default entry function
set_grub_default_entry() {
  local current_kernel
  current_kernel=$(uname -r)
  echo "Setting Grub default entry to current kernel..."
  # Find the exact GRUB menu entry
  ENTRY=$(echo "$SUDO_PASSWORD" | sudo -S grep -E "menuentry 'Ubuntu, with Linux $current_kernel'" /boot/grub/grub.cfg | head -1 | cut -d"'" -f2)
  if [ -n "$ENTRY" ]; then
    echo "Found GRUB entry: $ENTRY"
    echo "$SUDO_PASSWORD" | sudo -S grub-set-default "$ENTRY"
    echo "$SUDO_PASSWORD" | sudo -S update-grub
  else
    echo "Error: Could not find GRUB entry for kernel $current_kernel"
    return 1
  fi
}

install_pigz_unified() {
  local context="${1:-general}"

  # Check if pigz is already installed system-wide
  if command -v pigz >/dev/null 2>&1; then
    echo "[SKIP] pigz already installed for $context"
    return 0
  fi

  echo "Installing pigz 2.8 for $context..."

  delete_folder_if_exists "pigz_temp"
  echo "$SUDO_PASSWORD" | sudo -S apt-get install -y git
  repo_link="https://github.com/madler/pigz.git"
  git_clone "$repo_link" "./pigz_temp"
  cd pigz_temp || exit 1
  make
  echo "$SUDO_PASSWORD" | sudo -S cp pigz /usr/bin/pigz
  echo "$SUDO_PASSWORD" | sudo -S cp unpigz /usr/bin/unpigz
  cd ..
  delete_folder_if_exists "pigz_temp"
  echo "✓ pigz 2.8 installation completed for $context"
}

# Verify the device is working with the drivers
verify_gpu_installation() {
  echo "Verifying GPU driver installation..."
  # Check for IGC packages
  if dpkg-query -W -f='${Package}\n' | grep -E -q '^(libigc|libigdfcl)'; then
    echo "✓ IGC packages installed:"
    dpkg-query -W | grep -E '^(libigc|libigdfcl)'
  else
    echo "No IGC packages found"
  fi
  # Check for Level Zero
  if dpkg-query -W -f='${Package}\n' | grep -E -q '^(libze|level-zero)'; then
    echo "✓ Level Zero packages installed:"
    dpkg-query -W | grep -E '^(libze|level-zero)'
  else
    echo "⚠ Warning: No Level Zero packages found"
  fi
  # Check for OpenCL
  if dpkg-query -W | grep -i intel-opencl-icd; then
    echo "✓ Intel OpenCL ICD installed"
  else
    echo "⚠ Warning: Intel OpenCL ICD not found"
  fi
  # Test functionality
  echo "Testing GPU functionality..."
  if command -v clinfo >/dev/null 2>&1; then
    if clinfo | grep -q "Device Name"; then
      echo "✓ OpenCL devices detected:"
      clinfo | grep "Device Name" | head -3
    else
      echo "⚠ Warning: No OpenCL devices detected"
    fi
  fi
  if command -v hwinfo >/dev/null 2>&1; then
    echo "✓ GPU hardware detected:"
    hwinfo --display || echo "Hardware info not available"
  fi
}

# Geo detection and configuration function
PRC_Proxy () {
echo "In PRC_Proxy function"
echo "Detect the Geo Location"
# Check if curl command is available. Install if not.
if ! command -v curl &> /dev/null; then
  echo "curl is not available. Installing.."
  echo "$SUDO_PASSWORD" | sudo -S apt-get update -y
  echo "$SUDO_PASSWORD" | sudo -S apt-get install curl -y
  curl --version
  if curl --version &> /dev/null; then
    echo "curl installation is successful"
  else
    echo "curl installation failed!!"
  fi
else
  echo "curl is already available on the setup. Proceeding further.."
fi

# Set default region
DETECTED_REGION="OTHER"
exit_code=1

# Enhanced geo detection with timeout and fallback
geo_array=("ipinfo.io/country" "ipapi.co/country" "ifconfig.co/country-iso")
for geo_server in "${geo_array[@]}"; do
  echo "Trying geo server: $geo_server"
  for ((iteration=1;iteration<=2;iteration+=1)); do
    # Add timeout and connection timeout to prevent hanging
    country_code=$(timeout 10 curl -s --connect-timeout 5 --max-time 10 "$geo_server" 2>/dev/null | tr -d '[:space:]')
    exit_code=$?

    if [ $exit_code -eq 0 ] && [ -n "$country_code" ] && [ ${#country_code} -eq 2 ]; then
      echo "Country detection successful on attempt $iteration. Connected to a Network in $country_code"
      break
    else
      echo "Country detection failed in attempt $iteration for $geo_server"
      sleep 2
    fi
  done

  # Break if we got a valid result
  if [ $exit_code -eq 0 ] && [ -n "$country_code" ] && [ ${#country_code} -eq 2 ]; then
    break
  fi
done

# Final fallback - check for CN-specific indicators
if [ $exit_code -ne 0 ] || [ -z "$country_code" ]; then
  echo "Geo detection failed with all servers. Checking for CN-specific indicators..."

  # Check timezone
  if [ -f /etc/timezone ]; then
    timezone=$(cat /etc/timezone 2>/dev/null)
    if [[ "$timezone" == *"Shanghai"* ]] || [[ "$timezone" == *"Asia/Chongqing"* ]]; then
      echo "CN timezone detected: $timezone"
      country_code="CN"
      exit_code=0
    fi
  fi

  # Check locale if timezone check failed
  if [ $exit_code -ne 0 ]; then
    locale_info=$(locale 2>/dev/null | grep -i "zh_cn\|chinese" || true)
    if [ -n "$locale_info" ]; then
      echo "CN locale detected: $locale_info"
      country_code="CN"
      exit_code=0
    fi
  fi

  # Final fallback - assume non-CN region
  if [ $exit_code -ne 0 ]; then
    echo "Unable to detect geographical location. Assuming non-CN region for safety."
    echo "If you are in China and experience slow downloads, please set proxy manually."
    country_code="OTHER"
    exit_code=0
  fi
fi

# Set the detected region
if [ "$country_code" = "CN" ]; then
  DETECTED_REGION="CN"
  echo "CN region detected - will use CN-specific mirrors and configurations"
else
  DETECTED_REGION="OTHER"
  echo "Non-CN region detected - using standard configurations"
fi

echo "Geographical Location Detection and Configuration Completed. Region: $DETECTED_REGION"
}

# calling PRC_Proxy function as part of the template starter scripts
PRC_Proxy

# Git Clone function
git_clone () {
# arguements
local repo_url="$1"
local dest_dir="$2"
local branch="${3:-}"
local use_submodules="${4:-false}" # default: false. uses the submodule command only if this is true explicitly

local github_url="https://github.com"
local repo_path="${repo_url#"${github_url}"/}" # to extract only the repo path like intel/dlstreamer.git
#local mirror_repo="${mirror_url}/${repo_path}"
local mirror_urls=(
  "$repo_url"
  "${repo_url/github.com/gitclone.com/github.com}"
  "${repo_url/github.com/hub.gitmirror.com/github.com}"
)

#Command constructors
#1. with branch
clone_repo() {
  local branch="$1"
  local url="$2"
  local dest="$3"

  if [ "$use_submodules" = "true" ]; then
    git clone --recurse-submodules --shallow-submodules -b "$branch" --depth 1 "$url" "$dest"
  else
    git clone -b "$branch" "$url" "$dest"
  fi
}
clone_default() {
  local url="$1"
  local dest="$2"

  if [ "$use_submodules" = "true" ]; then
    git clone --recurse-submodules --shallow-submodules --depth 1 "$url" "$dest"
  else
    git clone "$url" "$dest"
  fi
}

#1. Try the original github url with branch
if [ -n "$branch" ]; then
  echo "Trying with the $repo_url..."
  if git ls-remote --heads "$repo_url" "$branch" &>/dev/null; then
    clone_repo "$branch" "$repo_url" "$dest_dir" && return 0
  else
    echo "Branch $branch not found in the repo. Trying with the default branch..."
    clone_default "$repo_url" "$dest_dir" && return 0
  fi
else
  echo "No branch specified. Cloning default branch from GitHub.."
  clone_default "$repo_url" "$dest_dir" && return 0
fi

#2. Try with mirror repository
if [ "$DETECTED_REGION" = "CN" ]; then
  echo "CN Region. Trying with the mirrors..."
  for mirror in "${mirror_urls[@]}"; do
    if [ -n "$branch" ]; then
      echo "Trying with mirror $mirror..."
      if git ls-remote --heads "$mirror" "$branch" &>/dev/null; then
        clone_repo "$branch" "$mirror" "$dest_dir" && return 0
      else
        echo "Branch $branch not found in the mirror $mirror. Trying with the default branch..."
        clone_default "$mirror" "$dest_dir" && return 0
      fi
    else
      echo "No branch specified. Cloning default branch from the Mirror..."
      clone_default "$mirror" "$dest_dir" && return 0
    fi
  done
fi

#3. Ask the user for another known mirror (Will be implemented later)
echo "Failed to clone the repo $repo_path from both GitHub and the mirror"
return 1

}

wget_from_github () {
local file_url="$1"
local output_path="$2"

local mirror_base="https://gitclone.com/github.com"
local fallback_url="${file_url/https:\/\/github.com/$mirror_base}"

echo "Downloading from: $file_url"
if wget -q --show-progress "$file_url" -O "$output_path"; then
  echo "Downloaded the file successfully..."
  return 0
else
  echo "Failed to download from GitHub. Trying with the mirror: $fallback_url"
  if wget -q --show-progress "$fallback_url" -O "$output_path"; then
    echo "Downloaded the file successfully from mirror..."
    return 0
  else
    echo "Failed to download from GitHub and mirror."
    return 1
  fi
fi
}


echo 'NTP=corp.intel.com' | sudo tee -a /etc/systemd/timesyncd.conf > /dev/null

STATUS_DIR=$(pwd)
LOGFILE="$STATUS_DIR/output.log"
exec > >(tee -a "$LOGFILE") 2>&1


declare -i proxy_build_status
declare -i disable_popup_build_status
declare -i build_dependency_build_status
declare -i pigz_build_status
declare -i jq_build_status
declare -i docker_install_build_status
declare -i docker_group_build_status
declare -i kernel_build_status
declare -i mesa_build_status
declare -i onevpl_build_status
declare -i gpu_build_status
declare -i npu_enablement_build_status
declare -i opencv_build_status
declare -i ffmpeg_build_status
declare -i openvino_native_build_status
declare -i dlstreamer_build_status
declare -i discrete_tpm_build_status
declare -i intel_xpu_manager_build_status
declare -i prometheus_build_status
declare -i grafana_build_status
declare -i node_exporter_build_status
declare -i intel_xpum_container_build_status
declare -i cadvisor_build_status
declare -i enable_restore_openssl_conf_build_status
declare -i reboot_continue_build_status

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
echo "disable_popup_build_status=0"
echo "build_dependency_build_status=0"
echo "pigz_build_status=0"
echo "jq_build_status=0"
echo "docker_install_build_status=0"
echo "docker_group_build_status=0"
echo "kernel_build_status=0"
echo "mesa_build_status=0"
echo "onevpl_build_status=0"
echo "gpu_build_status=0"
echo "npu_enablement_build_status=0"
echo "opencv_build_status=0"
echo "ffmpeg_build_status=0"
echo "openvino_native_build_status=0"
echo "dlstreamer_build_status=0"
echo "discrete_tpm_build_status=0"
echo "intel_xpu_manager_build_status=0"
echo "prometheus_build_status=0"
echo "grafana_build_status=0"
echo "node_exporter_build_status=0"
echo "intel_xpum_container_build_status=0"
echo "cadvisor_build_status=0"
echo "enable_restore_openssl_conf_build_status=0"
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
echo "If you are behind a company proxy and not an open network, please exit this installation using keyboard interrupt"
echo "Please set the below proxies in the /etc/environment file and restart the installer."
echo -e "http_proxy=\nhttps_proxy=\nno_proxy=\nftp_proxy=\nsocks_proxy=\nHTTP_PROXY=\nHTTPS_PROXY=\nNO_PROXY=\n"
# sleep for a few seconds to display this message and wait for keyboard interrupt
echo 'Installation will wait for "15" seconds to detect the keyboard interrupt.'
echo "Will continue with the installation if none given...."
sleep 15
echo "Proceeding with the installation..."
if grep -q "LD_LIBRARY_PATH" /etc/environment; then
  echo "LD_LIBRARY_PATH is already present in /etc/environment."
else
  {
    echo LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu/
  } | sudo tee -a /etc/environment > /dev/null
  echo "LD_LIBRARY_PATH is added to /etc/environment."
fi

# shellcheck source=/dev/null
source /etc/environment
export http_proxy https_proxy ftp_proxy socks_proxy no_proxy HTTP_PROXY HTTPS_PROXY NO_PROXY;

sed -i 's/proxy_build_status=0/proxy_build_status=1/g' "$STATUS_DIR_FILE_PATH"

elapsedseconds=$SECONDS
echo "proxy build time = $((elapsedseconds))" >> "$PACKAGE_BUILD_TIME_FILE"

fi

}

Install_Disable_Popup () {

echo "Installing Install_Disable_Popup"
if [ "$disable_popup_build_status" -ne 1 ]; then
SECONDS=0
echo "*************************"
echo "     Disable Popup       "
echo "*************************"
if [ -e /etc/needrestart/needrestart.conf ]; then
  echo "Disable hints on pending kernel upgrades"
  echo "$SUDO_PASSWORD" | sudo -S sed -i "s/\#\\\$nrconf{kernelhints} = -1;/\$nrconf{kernelhints} = -1;/g" /etc/needrestart/needrestart.conf
  echo "$SUDO_PASSWORD" | sudo -S sed -i "s/^#\\\$nrconf{restart} = 'i';/\$nrconf{restart} = 'a';/" /etc/needrestart/needrestart.conf
  grep "nrconf{kernelhints}" /etc/needrestart/needrestart.conf
  grep "nrconf{restart}" /etc/needrestart/needrestart.conf
fi

sed -i 's/disable_popup_build_status=0/disable_popup_build_status=1/g' "$STATUS_DIR_FILE_PATH"

elapsedseconds=$SECONDS
echo "disable_popup build time = $((elapsedseconds))" >> "$PACKAGE_BUILD_TIME_FILE"

fi

}

Install_Build_Dependencies () {

echo "Installing Install_Build_Dependencies"
if [ "$build_dependency_build_status" -ne 1 ]; then
SECONDS=0
echo "*************************"
echo "   Build Dependencies    "
echo "*************************"
echo "$SUDO_PASSWORD" | sudo -S apt-get update
echo "$SUDO_PASSWORD" | sudo -S apt-get install -y --allow-downgrades bash python3 python3-dev ca-certificates wget python3-pip git
echo "$SUDO_PASSWORD" | sudo -S apt-get -y -q install --allow-downgrades bc build-essential ccache gcc git wget xz-utils libncurses-dev flex
echo "$SUDO_PASSWORD" | sudo -S apt-get -y -q install --allow-downgrades bison openssl libssl-dev libelf-dev libudev-dev libpci-dev
echo "$SUDO_PASSWORD" | sudo -S apt-get -y -q install --allow-downgrades libiberty-dev autoconf cpio devscripts mawk cmake meson pkg-config
echo "$SUDO_PASSWORD" | sudo -S apt-get -y install --allow-downgrades lz4 debhelper unzip jq curl expect ufw automake libtool libva-dev libdrm-dev
echo "$SUDO_PASSWORD" | sudo -S apt install -y --allow-downgrades software-properties-common
echo "$SUDO_PASSWORD" | sudo -S systemctl daemon-reload

if ! dpkg -s python3-venv >/dev/null 2>&1; then
  echo "Installing python3-venv package"
  echo "$SUDO_PASSWORD" | sudo -S apt-get update
  echo "$SUDO_PASSWORD" | sudo -S apt-get install -y python3-venv
fi

# Configuring pip tool to use mirrors in PRC region
if [ "$DETECTED_REGION" = "CN" ]; then
  echo "CN region detected. Configuring pip and git global settings to use the PRC mirror"
  if [ -n "${http_proxy:-}" ]; then
    echo "Command: git config --global http.proxy $http_proxy"
    git config --global http.proxy "$http_proxy"
  fi
  if [ -n "${https_proxy:-}" ]; then
    echo "Command: git config --global https.proxy $https_proxy"
    git config --global https.proxy "$https_proxy"
  fi
  echo "Command: pip config set global.index-url https://mirrors.cloud.tencent.com/pypi/simple"
  pip config set global.index-url https://mirrors.cloud.tencent.com/pypi/simple
fi
echo \\\"Build essentials installation done\\\"

sed -i 's/build_dependency_build_status=0/build_dependency_build_status=1/g' "$STATUS_DIR_FILE_PATH"

elapsedseconds=$SECONDS
echo "build_dependency build time = $((elapsedseconds))" >> "$PACKAGE_BUILD_TIME_FILE"

fi

}

Install_pigz () {

echo "Installing Install_pigz"
if [ "$pigz_build_status" -ne 1 ]; then
SECONDS=0
echo "*************************"
echo "    Pigz Installation    "
echo "*************************"

install_pigz_unified "main"

sed -i 's/pigz_build_status=0/pigz_build_status=1/g' "$STATUS_DIR_FILE_PATH"

elapsedseconds=$SECONDS
echo "pigz build time = $((elapsedseconds))" >> "$PACKAGE_BUILD_TIME_FILE"

fi

}

Install_jq () {

echo "Installing Install_jq"
if [ "$jq_build_status" -ne 1 ]; then
SECONDS=0
echo "*************************"
echo "    jq Installation      "
echo "*************************"
if ! command -v jq &> /dev/null; then
  echo "jq is not available. Installing.."
  echo "$SUDO_PASSWORD" | sudo -S apt-get update -y
  echo "$SUDO_PASSWORD" | sudo -S apt-get install -y jq
  if jq --version &> /dev/null; then
    echo "jq installation is successful"
  else
    echo "jq installation failed!!"
  fi
else
  echo "jq is already available on the setup. Proceeding further.."
fi
sed -i 's/jq_build_status=0/jq_build_status=1/g' "$STATUS_DIR_FILE_PATH"

elapsedseconds=$SECONDS
echo "jq build time = $((elapsedseconds))" >> "$PACKAGE_BUILD_TIME_FILE"

fi

}

Install_Docker () {

echo "Installing Install_Docker"
if [ "$docker_install_build_status" -ne 1 ]; then
SECONDS=0
echo "*************************"
echo "    Docker Installation  "
echo "*************************"
echo "$SUDO_PASSWORD" | sudo -S mkdir -p /etc/systemd/system/docker.service.d
echo "$SUDO_PASSWORD" | sudo -S bash -c 'cat << EOF > /etc/systemd/system/docker.service.d/proxy.conf
[Service]
Environment="HTTP_PROXY=$http_proxy"
Environment="HTTPS_PROXY=$https_proxy"
Environment="NO_PROXY=$no_proxy"
EOF'

echo "***installing docker***"
for pkg in docker.io docker-doc docker-compose docker-compose-v2 podman-docker containerd runc; do
  check_installed $pkg
  echo "$SUDO_PASSWORD" | sudo -S apt-get -y remove $pkg;
done
echo "$SUDO_PASSWORD" | sudo -S systemctl daemon-reload

echo "$SUDO_PASSWORD" | sudo -S apt-get update
echo "$SUDO_PASSWORD" | sudo -S apt-get -y install ca-certificates curl cmake g++ wget unzip
echo "$SUDO_PASSWORD" | sudo -S install -m 0755 -d /etc/apt/keyrings
echo "$SUDO_PASSWORD" | sudo -S curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
echo "$SUDO_PASSWORD" | sudo -S chmod a+r /etc/apt/keyrings/docker.asc
#shellcheck source=/dev/null
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
echo "$SUDO_PASSWORD" | sudo -S apt-get update
echo "$SUDO_PASSWORD" | sudo -S apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
echo "$SUDO_PASSWORD" | sudo -S systemctl daemon-reload
while true; do
  # Check if the service is active
  if systemctl is-active --quiet docker; then
    echo "docker is running."
    break
  else
    echo "docker is not running. Attempting to restart..."
    # Attempt to restart the service
    if echo "$SUDO_PASSWORD" | sudo -S systemctl restart docker; then
      echo "docker successfully restarted."
      break
    else
      echo "Failed to restart docker. Retrying in 30 seconds..."
    fi
  fi
  # Sleep for a specified duration before checking again
  sleep 30
done
# Check if /etc/docker/daemon.json exists, create if not
DAEMON_JSON="/etc/docker/daemon.json"
if [ ! -f "$DAEMON_JSON" ]; then
  echo "$SUDO_PASSWORD" | sudo -S mkdir -p /etc/docker
  echo '{}' | sudo tee "$DAEMON_JSON" > /dev/null
fi

# Detect PRC location
# If PRC detected, configure registry mirror
if [ "$DETECTED_REGION" = "CN" ]; then
  echo "PRC detected, configuring Docker registry mirror..."
  # Use jq to update daemon.json with registry-mirror
  echo "$SUDO_PASSWORD" | sudo -S bash -c "jq '. + {\"registry-mirrors\": [\"https://docker.m.daocloud.io\", \
  \"https://registry.cn-hangzhou.aliyuncs.com\", \
  \"https://docker.mirrors.ustc.edu.cn\"]}' $DAEMON_JSON > /tmp/daemon.json && mv -f /tmp/daemon.json $DAEMON_JSON"
fi

# Reload Docker daemon
echo "Reloading Docker daemon..."
sudo systemctl daemon-reload
sudo systemctl restart docker

sed -i 's/docker_install_build_status=0/docker_install_build_status=1/g' "$STATUS_DIR_FILE_PATH"

elapsedseconds=$SECONDS
echo "docker_install build time = $((elapsedseconds))" >> "$PACKAGE_BUILD_TIME_FILE"

fi

}

Configure_Docker_Group () {

echo "Installing Configure_Docker_Group"
if [ "$docker_group_build_status" -ne 1 ]; then
SECONDS=0
echo "*************************"
echo "   Docker Group Setup    "
echo "*************************"
GROUP_NAME="docker"

read -r -p "Would you like to add a custom username to the docker group? type yes | no: " choice
if [[ "$choice" == *"no"* ]]; then
  echo "Current user will be added to the docker group"
  USER_NAME="$USER"  # Default to the current user; change as needed
elif [[ "$choice" == *"yes"* ]]; then
  read -r -p "Please enter the username: " USER_NAME
  echo "Username $USER_NAME will be added to the docker group"
else
  echo "Invalid input. By default, the current user will be added to the docker group"
  USER_NAME="$USER"
fi
unset choice

# Check if the group exists, create it if it doesn't
if getent group "$GROUP_NAME"; then
  echo "Group '$GROUP_NAME' already exists."
else
  echo "Group '$GROUP_NAME' does not exist. Creating group..."
  echo "$SUDO_PASSWORD" | sudo -S groupadd "$GROUP_NAME"
  echo "Group '$GROUP_NAME' created."
fi

# Check if the user is in the group, add if not
if id -nG "$USER_NAME" | grep -qw "$GROUP_NAME"; then
  echo "User '$USER_NAME' is already in the group '$GROUP_NAME'."
else
  echo "User '$USER_NAME' is not in the group '$GROUP_NAME'. Adding user to the group..."
  echo "$SUDO_PASSWORD" | sudo -S usermod -aG "$GROUP_NAME" "$USER_NAME"
  echo "User '$USER_NAME' added to the group '$GROUP_NAME'."
fi

echo "$SUDO_PASSWORD" | sudo -S apt-get install acl -y
echo "$SUDO_PASSWORD" | sudo -S setfacl -m user:"$USER_NAME":rw /var/run/docker.sock
unset USER_NAME

sed -i 's/docker_group_build_status=0/docker_group_build_status=1/g' "$STATUS_DIR_FILE_PATH"

elapsedseconds=$SECONDS
echo "docker_group build time = $((elapsedseconds))" >> "$PACKAGE_BUILD_TIME_FILE"

fi

}

Install_Kernel () {

echo "Installing Install_Kernel"
if [ "$kernel_build_status" -ne 1 ]; then
SECONDS=0
cd "$STATUS_DIR"
if [ "$PROFILE" != "vpp" ] && [ "$PROFILE" != "tfcc" ]; then
  # Fetch and display the system default kernel
  current_kernel=$(uname -r)
  echo "Skipping kernel installation for profile $PROFILE"
  echo "System default kernel version: $current_kernel"
  # Avoid auto-upgrades of the kernel even though there is a newer version available from the distribution
  # to make sure the other components are compatible with the default kernel at the time of the first installation and reboot.
  keep_current_kernel_version
  set_grub_default_entry
  sed -i 's/kernel_build_status=0/kernel_build_status=1/g' "$STATUS_DIR_FILE_PATH"
  elapsedseconds=$SECONDS
  echo "kernel build time = $((elapsedseconds))" >> "$PACKAGE_BUILD_TIME_FILE"
  return
else
  if [ "$PROFILE" = "tfcc" ]; then
    echo "Kernel installation will proceed for profile $PROFILE"
    echo "*************************"
    echo " Installing the required Kernel "
    echo "*************************"
    # Define kernel package versions
    KERNEL_MAJOR_VERSION="6.16"
    local apt_kernel=""
    local target_version=""
    local found_via_apt="false"
    echo "Required Kernel Version: $KERNEL_MAJOR_VERSION"

    # Check if the required kernel is already installed
    if uname -r | grep -Eq "^${KERNEL_MAJOR_VERSION//./\\.}"; then
      echo "Required kernel version ${KERNEL_MAJOR_VERSION} is already installed and active."
      return 0
    fi

    # Check if the kernel is available in the package manager
    echo "Searching APT repositories for kernel version starting with $KERNEL_MAJOR_VERSION..."
    apt_kernel="$(apt-cache search "linux-image-${KERNEL_MAJOR_VERSION}" | awk '{print $1}' \
    | grep -E "^linux-image-${KERNEL_MAJOR_VERSION//./\\.}" \
    | sort -V | tail -n 1 || true)"
    if [ -n "$apt_kernel" ]; then
      found_via_apt="true"
      echo "Kernel package $apt_kernel found in apt."
    else
      echo "No matching kernel package found in apt for version $KERNEL_MAJOR_VERSION."
    fi
    if [ "$found_via_apt" = "true" ]; then
      echo "Installing kernel package $apt_kernel and its headers from apt..."
      local header_package="${apt_kernel/linux-image/linux-headers}"

      if echo "$SUDO_PASSWORD" | sudo -S apt-get update -qq && \
         echo "$SUDO_PASSWORD" | sudo -S apt-get install -y "$apt_kernel" "$header_package"; then
         echo "Kernel package $apt_kernel and headers $header_package installed successfully."
        return 0
      else
        echo "Error: Failed to install kernel package $apt_kernel or headers $header_package."
        found_via_apt="false"
      fi
    fi

    # Ubuntu Mainline Kernel Installation
    if [ "$found_via_apt" = "false" ]; then
      if ! command -v mainline >/dev/null 2>&1; then
      echo "Installing mainline tool for Ubuntu mainline kernel management..."
      echo "$SUDO_PASSWORD" | sudo -S add-apt-repository -y ppa:cappelikan/ppa >/dev/null 2>&1 || true
      echo "$SUDO_PASSWORD" | sudo -S apt-get update -qq
      echo "$SUDO_PASSWORD" | sudo -S apt-get install -y mainline || {
        echo "Error: Failed to install mainline tool."
        return 1
      }
      fi
      echo "Using mainline tool to search for latest kernel version starting with $KERNEL_MAJOR_VERSION..."
      target_version="$(mainline --list | grep -E "^ *${KERNEL_MAJOR_VERSION//./\\.}\.[0-9]+" \
      | awk '{print $1}' | sort -V | tail -n 1)"

      if [ -z "$target_version" ]; then
        echo "Error: No matching kernel version found in mainline tool for version $KERNEL_MAJOR_VERSION."
        echo "Installing manually via .deb packages... "
        delete_folder_if_exists "intel_kernel"
        create_folder "intel_kernel"
        cd intel_kernel || exit 1

        EN_DEFAULT_KERNEL="6.16.0-061600-generic"
        kernel_version=$(uname -r)
        echo "Kernel Version = $kernel_version"
        if [ "$kernel_version" = "$EN_DEFAULT_KERNEL" ]; then
          echo "Target Kernel Version already installed."
        else
          echo "Target kernel ${EN_DEFAULT_KERNEL} is not installed. Proceeding with installation..."
          # Install kernel build dependencies
          echo "Installing kernel build dependencies..."
          echo "$SUDO_PASSWORD" | sudo -S apt-get install -y build-essential linux-source bc kmod cpio flex libncurses5-dev libelf-dev libssl-dev dwarves bison quilt debhelper

          # --- Example: Download kernel source and overlay (commented for reference) ---
          # KERNEL_URL="https://github.com/intel/linux-intel-lts/archive/refs/tags/lts-v6.12.36-linux-250711T071314Z.tar.gz"
          # KERNEL_TARBALL="lts-v6.12.36-linux-250711T071314Z.tar.gz"
          # KERNEL_SRC_DIR="linux-intel-lts-lts-v6.12.36-linux-250711T071314Z"
          # echo "Downloading kernel source from $KERNEL_URL..."
          # wget -q "$KERNEL_URL" -O "$KERNEL_TARBALL"
          # tar -xzf "$KERNEL_TARBALL"
          # rm -f "$KERNEL_TARBALL"
          # git_clone "https://github.com/intel/linux-kernel-overlay.git" "linux-kernel-overlay"
          # cd linux-kernel-overlay || { echo "Failed to enter linux-kernel-overlay directory."; exit 1; }
          # git checkout lts-overlay-v6.12.36-ubuntu-250711T071314Z
          # ./build.sh -r no -t vpptfcc 1

          # --- Example: Install kernel packages (commented for reference) ---
          # IMG_DEB=$(find . -maxdepth 1 -name "linux-image-6.12.36-nonrt-vpptfcc_6.12.36-0_amd64.deb" -print -quit)
          # HDR_DEB=$(find . -maxdepth 1 -name "linux-headers-6.12.36-nonrt-vpptfcc_6.12.36-0_amd64.deb" -print -quit)
          # LIBC_DEB=$(find . -maxdepth 1 -name "linux-libc-dev_6.12.36-0_amd64.deb" -print -quit)

          # --- Example: Download kernel image and headers (commented for reference) ---
          # KERNEL_IMG_URL="https://download.01.org/intel-linux-overlay/ubuntu/pool/kernels/l/linux-intel-6.12/linux-image-6.12-intel_250711t071314z-r2_amd64.deb"
          # KERNEL_HDR_URL="https://download.01.org/intel-linux-overlay/ubuntu/pool/kernels/l/linux-intel-6.12/linux-headers-6.12-intel_250711t071314z-r2_amd64.deb"
          # wget -q --show-progress "$KERNEL_IMG_URL" -O linux-image-6.12-intel_250711t071314z-r2_amd64.deb
          # wget -q --show-progress "$KERNEL_HDR_URL" -O linux-headers-6.12-intel_250711t071314z-r2_amd64.deb
          # Define kernel package versions and filenames
          KERNEL_VERSION="6.16.0-061600"
          KERNEL_DATE="202507272138"
          BASE_URL="https://kernel.ubuntu.com/mainline/v6.16/amd64"

          IMG_DEB="linux-image-unsigned-${KERNEL_VERSION}-generic_${KERNEL_VERSION}.${KERNEL_DATE}_amd64.deb"
          HDR_Gen_DEB="linux-headers-${KERNEL_VERSION}-generic_${KERNEL_VERSION}.${KERNEL_DATE}_amd64.deb"
          HDR_DEB="linux-headers-${KERNEL_VERSION}_${KERNEL_VERSION}.${KERNEL_DATE}_all.deb"
          MOD_DEB="linux-modules-${KERNEL_VERSION}-generic_${KERNEL_VERSION}.${KERNEL_DATE}_amd64.deb"

          # Download Ubuntu mainline kernel packages if not already present
          for pkg in "$HDR_Gen_DEB" "$HDR_DEB" "$IMG_DEB" "$MOD_DEB"; do
            if [ ! -f "$pkg" ]; then
              wget -q --show-progress "${BASE_URL}/$pkg"
            else
              echo "$pkg already exists, skipping download."
            fi
          done

          echo "Kernel image package: $IMG_DEB"
          echo "Kernel header package: $HDR_DEB"
          echo "Kernel generic header package: $HDR_Gen_DEB"
          echo "Kernel modules package: $MOD_DEB"

          # Verify that all required files were downloaded
          if [[ ! -f "$IMG_DEB" || ! -f "$HDR_DEB" || ! -f "$HDR_Gen_DEB" || ! -f "$MOD_DEB" ]]; then
            echo "Error: Failed to download kernel packages. Installation aborted."
            exit 1
          fi

          # Install kernel image and headers
          echo "Installing kernel image and headers..."
          echo "$SUDO_PASSWORD" | sudo -S dpkg -i "$MOD_DEB" "$IMG_DEB" "$HDR_DEB" "$HDR_Gen_DEB"

          # # --- Example: Copy kernel config if needed (commented for reference) ---
          # # if [ -f /boot/config-6.12.36-nonrt-vpptfcc ]; then
          # #   echo "$SUDO_PASSWORD" | sudo -S cp /boot/config-6.12.36-nonrt-vpptfcc /usr/src/linux-headers-6.12.36-nonrt-vpptfcc/.config
          # # else
          # #   echo "kernelconfig file not found, skipping copy."
          # # fi

          # Update GRUB to set new kernel as default
          new_kernel=$(uname -r)
          if [ "$new_kernel" == "$EN_DEFAULT_KERNEL" ]; then
            echo "Setting GRUB_DEFAULT to new kernel: $EN_DEFAULT_KERNEL"
            echo "$SUDO_PASSWORD" | sudo -S sed -i "s|GRUB_DEFAULT=.*|GRUB_DEFAULT=\"Advanced options for Ubuntu>Ubuntu, with Linux $EN_DEFAULT_KERNEL\"|" /etc/default/grub
            echo "$SUDO_PASSWORD" | sudo -S update-grub
          else
            echo "Failed to retrieve installed kernel version for GRUB update."
          fi

          echo "Intel kernel installation completed."
          cd ../..
          delete_folder_if_exists "intel_kernel"
        fi
      else
        echo "Installing kernel $target_version using mainline tool..."
        if echo "$SUDO_PASSWORD" | sudo -S mainline install "$target_version"; then
          echo "Kernel version $target_version installed successfully via mainline tool."
        else
          echo "Error: Failed to install kernel version $target_version via mainline tool."
          exit 1
        fi
      fi
    fi
  else # if PROFILE is vpp
    echo "Kernel installation will proceed for profile $PROFILE"
    echo "*************************"
    EXT_KERNEL_URL="https://download.01.org/intel-linux-overlay/ubuntu/pool/kernels/l/"
    EXT_KERNEL_DIR="linux-intel-6.12"
    VPP_KERNEL_VERSION="6.12-intel"
    # list of Downloadables
    FULL_URL="${EXT_KERNEL_URL}${EXT_KERNEL_DIR}/"
    DEB_FILES=$(curl -s "$FULL_URL" | grep -oP 'linux-(image|headers)[^"]+\.deb' | uniq)
    # Exit if no .deb files found
    if [ -z "$DEB_FILES" ]; then
      echo "No .deb files found at $FULL_URL"
      exit 1
    else
      echo "Found the following .deb files:"
      echo "$DEB_FILES"
    fi

    DEB_IMG_URL=$(echo "$DEB_FILES" | grep -Ei '^linux-image-[0-9].*amd64\.deb$' | grep -v dbg | head -1)
    DEB_HDR_URL=$(echo "$DEB_FILES" | grep -Ei '^linux-headers-[0-9].*amd64\.deb$' | grep -v dbg | head -1)
    #DEB_LIBC_URL=$(echo "$DEB_FILES" | grep -Ei '^linux-libc-dev_[0-9].*amd64\.deb$' | head -1)

    delete_folder_if_exists "vpp_kernel"
    create_folder "vpp_kernel"
    cd vpp_kernel || exit 1

    if [[ -z "$DEB_IMG_URL" || -z "$DEB_HDR_URL" ]]; then
      echo "Could not find all required .deb files."
      exit 1
    else
      echo "All required .deb files found."
      echo "Linux Image: $DEB_IMG_URL"
      echo "Linux Headers: $DEB_HDR_URL"
      for pkg in "$DEB_HDR_URL" "$DEB_IMG_URL"; do
        if [ ! -f "$pkg" ]; then
          wget -q --show-progress "${FULL_URL}/$pkg"
        else
          echo "$pkg already exists, skipping download."
        fi
      done
    fi
    echo "Installing downloaded kernel packages..."
    # Install kernel image and headers
    echo "$SUDO_PASSWORD" | sudo -S dpkg -i ./*.deb
    echo "$SUDO_PASSWORD" | sudo -s update-initramfs -c -k "$VPP_KERNEL_VERSION"
    echo "Updating GRUB to set new kernel as default..."
    echo "$SUDO_PASSWORD" | sudo -S update-grub
    # Find the latest installed kernel matching the VPP kernel version (not necessarily the currently running kernel)
    latest_installed_kernel=$(find /boot -maxdepth 1 -name "vmlinuz-*${VPP_KERNEL_VERSION}*" -type f 2> /dev/null | tail -n 1 | sed 's|.*/vmlinuz-||')
    if [[ -n "$latest_installed_kernel" && "$latest_installed_kernel" == *"$VPP_KERNEL_VERSION"* ]]; then
      echo "Setting GRUB_DEFAULT to newly installed kernel: $latest_installed_kernel"
      echo "$SUDO_PASSWORD" | sudo -S sed -i "s|GRUB_DEFAULT=.*|GRUB_DEFAULT=\"Advanced options for Ubuntu>Ubuntu, with Linux $latest_installed_kernel\"|" /etc/default/grub
      echo "$SUDO_PASSWORD" | sudo -S update-grub
    else
      echo "Warning: Could not determine a valid installed kernel version for GRUB update. Skipping GRUB_DEFAULT modification."
    fi
    echo "Intel kernel installation completed."
    cd ..
    delete_folder_if_exists "vpp_kernel"
    # For VPP profile, configure force_probe before reboot
    if [ "$PROFILE" = "vpp" ]; then
      echo "Configuring GPU force_probe settings for VPP profile before reboot..."
      # Clean up existing modprobe configs
      echo "$SUDO_PASSWORD" | sudo -S rm -f /etc/modprobe.d/i915.conf
      echo "$SUDO_PASSWORD" | sudo -S rm -f /etc/modprobe.d/xe.conf

      # Classify GPUs and configure appropriate drivers
      igpu_ids=()
      dgpu_ids=()
      gpu_found=false

      # Process each Intel GPU
      while IFS= read -r line; do
        if [[ -n "$line" ]]; then
          gpu_found=true
          gpu_id=$(echo "$line" | awk -F '8086:' '{print $2}' | awk '{print $1}' | sed 's/]$//')
          device_type=$(echo "$line" | grep -o 'VGA\|Display')
          device_name="${line##*: }"
          echo "Found GPU: ID=$gpu_id, Type=$device_type, Name=$device_name"

          # Classify GPU based on known patterns
          if [[ "$device_name" =~ (Arc|DG2|Ponte|Flex|Max|ATS-M) ]] || [[ "$device_type" == "Display" && "$device_name" =~ (Data Center|Flex) ]]; then
            dgpu_ids+=("$gpu_id")
            echo "  → Classified as dGPU (will use xe driver)"
          elif [[ "$device_name" =~ (UHD|Iris|Graphics|GT1|GT2) ]] && [[ "$device_type" == "VGA" ]]; then
            igpu_ids+=("$gpu_id")
            echo "  → Classified as iGPU (will use i915 driver)"
          else
            # Enhanced fallback logic for VPP
            case "$gpu_id" in
              # Known iGPU IDs
              "a721"|"7d51"|"46b3"|"9a49"|"a780"|"7dd5"|"7d67"|"7d41"|"7d45"|"7d40"|"7d55")
                igpu_ids+=("$gpu_id")
                echo "  → Classified as iGPU (known ID, will use i915 driver)"
                ;;
              # Known dGPU IDs
              "56a0"|"56c0"|"56a5"|"e20b"|"e211")
                dgpu_ids+=("$gpu_id")
                echo "  → Classified as dGPU (known ID, will use xe driver)"
                ;;
              *)
                # Final fallback: VGA=iGPU, Display=dGPU
                if [[ "$device_type" == "VGA" ]]; then
                  igpu_ids+=("$gpu_id")
                  echo "  → Classified as iGPU (VGA fallback, will use i915 driver)"
                else
                  dgpu_ids+=("$gpu_id")
                  echo "  → Classified as dGPU (Display fallback, will use xe driver)"
                fi
                ;;
            esac
          fi
        fi
      done < <(lspci -nn | grep -Ei 'VGA|DISPLAY' | grep '8086')

      if [[ "$gpu_found" == "false" ]]; then
        echo "Warning: No Intel GPU devices found. Skipping force_probe configuration."
      else
        # Configure i915 for iGPUs
        if [[ ${#igpu_ids[@]} -gt 0 ]]; then
          igpu_list=$(IFS=,; echo "${igpu_ids[*]}")
          echo "Configuring i915 driver for iGPU(s): ${igpu_ids[*]}"
          echo "$SUDO_PASSWORD" | sudo -S bash -c "echo 'options i915 force_probe=$igpu_list' > /etc/modprobe.d/i915.conf"
          echo "Created /etc/modprobe.d/i915.conf with force_probe=$igpu_list"
        fi
        # Configure xe for dGPUs
        if [[ ${#dgpu_ids[@]} -gt 0 ]]; then
          dgpu_list=$(IFS=,; echo "${dgpu_ids[*]}")
          echo "Configuring xe driver for dGPU(s): ${dgpu_ids[*]}"
          echo "$SUDO_PASSWORD" | sudo -S bash -c "echo 'options xe force_probe=$dgpu_list' > /etc/modprobe.d/xe.conf"
          echo "Created /etc/modprobe.d/xe.conf with force_probe=$dgpu_list"
        fi
      fi
    fi
  fi
  # Reboot the platform after installing the kernel
  echo "Upgradation to the supported Kernel version completed."
  echo "A Reboot is required to apply the changes."
  echo "Rebooting the system..."
  echo -e "\n*** Initiating system reboot... ***"
  echo "$SUDO_PASSWORD" | sudo -S reboot
fi

sed -i 's/kernel_build_status=0/kernel_build_status=1/g' "$STATUS_DIR_FILE_PATH"

elapsedseconds=$SECONDS
echo "kernel build time = $((elapsedseconds))" >> "$PACKAGE_BUILD_TIME_FILE"

fi

}

Install_Media_Tools () {

echo "Installing Install_Media_Tools"
if [ "$mesa_build_status" -ne 1 ]; then
SECONDS=0
echo "*************************"
echo "  Installing Media Tools "
echo "*************************"
cd "$STATUS_DIR"

# Set repository priorities first
set_intel_repo_priorities

echo "$SUDO_PASSWORD" | sudo -S apt-get update
echo "$SUDO_PASSWORD" | sudo -S apt-get -y install --allow-downgrades \
  libgl1-mesa-dri \
  libglx-mesa0 \
  libglapi-mesa \
  libglu1-mesa \
  libglu1-mesa-dev \
  mesa-vulkan-drivers \
  mesa-utils

sed -i 's/mesa_build_status=0/mesa_build_status=1/g' "$STATUS_DIR_FILE_PATH"

elapsedseconds=$SECONDS
echo "mesa build time = $((elapsedseconds))" >> "$PACKAGE_BUILD_TIME_FILE"

fi
if [ "$onevpl_build_status" -ne 1 ]; then
SECONDS=0
echo "*************************"
echo "  Installing OneVPL      "
echo "*************************"
cd "$STATUS_DIR"
if [ -d vpl-gpu-rt ]; then
  rm -rf vpl-gpu-rt
fi

# Install dependencies for oneVPL: LIBVA
LIBVA_VERSION="2.22.0"
LIBVA_REPO="https://github.com/intel/libva.git"
LIBVA_DIR="libva"

echo "Cloning and building libva version $LIBVA_VERSION..."
delete_folder_if_exists "$LIBVA_DIR"
git_clone "$LIBVA_REPO" "$LIBVA_DIR"
cd "$LIBVA_DIR" || exit 1
git checkout "$LIBVA_VERSION"
./autogen.sh --prefix=/usr --libdir=/usr/lib/x86_64-linux-gnu
make -j "$(nproc)"
echo "$SUDO_PASSWORD" | sudo -S make install
cd ..
delete_folder_if_exists "$LIBVA_DIR"

# Build and install oneVPL GPU runtime
ONEVPL_VERSION="intel-onevpl-25.4.2"
ONEVPL_REPO="https://github.com/intel/vpl-gpu-rt"
ONEVPL_DIR="vpl-gpu-rt"

echo "Cloning and building oneVPL GPU runtime version $ONEVPL_VERSION..."
delete_folder_if_exists "$ONEVPL_DIR"
git_clone "$ONEVPL_REPO" "$ONEVPL_DIR" "$ONEVPL_VERSION"
cd "$ONEVPL_DIR" || exit 1
git checkout "$ONEVPL_VERSION"
mkdir -p build && cd build
cmake ..
make -j "$(nproc)"
echo "$SUDO_PASSWORD" | sudo -S make install
cd ../..
delete_folder_if_exists "$ONEVPL_DIR"

sed -i 's/onevpl_build_status=0/onevpl_build_status=1/g' "$STATUS_DIR_FILE_PATH"

elapsedseconds=$SECONDS
echo "onevpl build time = $((elapsedseconds))" >> "$PACKAGE_BUILD_TIME_FILE"

fi
if [ "$gpu_build_status" -ne 1 ]; then
SECONDS=0
echo "*************************"
echo "  Installing GPU Drivers "
echo "*************************"
os_version=$(grep 'VERSION_ID' /etc/os-release | cut -d '"' -f 2)
processor_type=$(lscpu | grep 'Model name:' | awk '{for(i=3;i<=NF;i++) if(tolower($i) ~ /(core|xeon|genuine|atom|celeron|n97|n95|n150|n355)/) print $i}')
source /etc/environment

# Set repository priorities first
set_intel_repo_priorities

# Function to check if custom Intel kernel is running
is_custom_intel_kernel() {
  local kernel_version
  kernel_version=$(uname -r)
  echo "Current kernel: $kernel_version"
  # Check for Intel custom kernel patterns
  if [[ "$kernel_version" =~ (intel|vpptfcc|nonrt) ]] || [[ "$kernel_version" == *"6.12"* && "$kernel_version" != *"generic"* ]]; then
    echo "Custom Intel kernel detected: $kernel_version"
    return 0
  else
    echo "Generic/standard kernel detected: $kernel_version"
    return 1
  fi
}

# Enhanced GPU detection and classification
get_gpu_info() {
  # Get all Intel GPU devices with their IDs and types
  lspci -nn | grep -Ei 'VGA|DISPLAY' | grep '8086' | while read -r line; do
    # Extract GPU ID
    gpu_id=$(echo "$line" | awk -F '8086:' '{print $2}' | awk '{print $1}' | sed 's/]$//')
    # Extract device type and name
    device_type=$(echo "$line" | grep -o 'VGA\|Display')
    # device_name=$(echo "$line" | sed 's/.*: //')
    device_name="${line##*: }"
    echo "GPU_ID:$gpu_id|TYPE:$device_type|NAME:$device_name"
  done
}

# Classify GPU as iGPU or dGPU based on device type and known patterns
classify_gpu() {
  local gpu_id="$1"
  local device_type="$2"
  local device_name="$3"
  # Known dGPU patterns (Arc series, Data Center GPUs, Flex)
  if [[ "$device_name" =~ (Arc|DG2|Ponte|Flex|Max|ATS-M) ]] || [[ "$device_type" == "Display" && "$device_name" =~ (Data Center|Flex) ]]; then
    echo "dGPU"
  elif [[ "$device_name" =~ (UHD|Iris|Graphics|GT1|GT2) ]] && [[ "$device_type" == "VGA" ]]; then
    echo "iGPU"
  else
    # Enhanced fallback logic based on your system examples
    case "$gpu_id" in
      # Known iGPU IDs from your systems
      "a721"|"7d51"|"46b3"|"9a49"|"a780"|"7dd5"|"7d67"|"7d41"|"7d45"|"7d40"|"7d55")
        echo "iGPU"
        ;;
      # Known dGPU IDs from your systems
      "56a0"|"56c0"|"56a5"|"e20b"|"e211")
        echo "dGPU"
        ;;
      *)
        # Final fallback: For Intel, VGA is typically iGPU, Display is typically dGPU
        if [[ "$device_type" == "VGA" ]]; then
          echo "iGPU"
        else
          echo "dGPU"
        fi
        ;;
    esac
  fi
}

# Enhanced force_probe configuration (only for custom Intel kernels)
configure_force_probe() {
  # Check if we're running a custom Intel kernel
  if ! is_custom_intel_kernel; then
    echo "Skipping force_probe configuration - using generic/standard kernel"
    echo "Force_probe is only needed for custom Intel kernels"
    return 0
  fi

  echo "Configuring GPU force_probe settings for custom Intel kernel..."
  # Clean up existing modprobe configs
  echo "$SUDO_PASSWORD" | sudo -S rm -f /etc/modprobe.d/i915.conf
  echo "$SUDO_PASSWORD" | sudo -S rm -f /etc/modprobe.d/xe.conf

  local igpu_ids=()
  local dgpu_ids=()
  local gpu_found=false
  # Process each GPU
  while IFS= read -r gpu_info; do
    if [[ -n "$gpu_info" ]]; then
      gpu_found=true
      gpu_id=$(echo "$gpu_info" | cut -d'|' -f1 | cut -d':' -f2)
      device_type=$(echo "$gpu_info" | cut -d'|' -f2 | cut -d':' -f2)
      device_name=$(echo "$gpu_info" | cut -d'|' -f3 | cut -d':' -f2)
      gpu_class=$(classify_gpu "$gpu_id" "$device_type" "$device_name")
      echo "Found GPU: ID=$gpu_id, Type=$device_type, Name=$device_name, Class=$gpu_class"
      if [[ "$gpu_class" == "iGPU" ]]; then
        igpu_ids+=("$gpu_id")
      elif [[ "$gpu_class" == "dGPU" ]]; then
        dgpu_ids+=("$gpu_id")
      fi
    fi
  done < <(get_gpu_info)
  if [[ "$gpu_found" == "false" ]]; then
    echo "No Intel GPU devices found."
    return 1
  fi

  # Configure i915 for iGPUs ONLY (separate from dGPU exclusions)
  if [[ ${#igpu_ids[@]} -gt 0 ]]; then
    echo "Configuring i915 driver for iGPU(s): ${igpu_ids[*]}"
    igpu_list=$(IFS=,; echo "${igpu_ids[*]}")
    echo "$SUDO_PASSWORD" | sudo -S bash -c "echo 'options i915 force_probe=$igpu_list' > /etc/modprobe.d/i915.conf"
    echo "Created /etc/modprobe.d/i915.conf with force_probe=$igpu_list"
  fi

  # Configure xe for dGPUs
  if [[ ${#dgpu_ids[@]} -gt 0 ]]; then
    echo "Configuring xe driver for dGPU(s): ${dgpu_ids[*]}"
    dgpu_list=$(IFS=,; echo "${dgpu_ids[*]}")
    echo "$SUDO_PASSWORD" | sudo -S bash -c "echo 'options xe force_probe=$dgpu_list' > /etc/modprobe.d/xe.conf"
    echo "Created /etc/modprobe.d/xe.conf with force_probe=$dgpu_list"
  fi

  # Update initramfs after force_probe configuration
  echo "Updating initramfs after force_probe configuration..."
  echo "$SUDO_PASSWORD" | sudo -S update-initramfs -u -k all

  # Display current modprobe configurations
  echo "=== Current GPU Driver Configuration ==="
  if [[ -f /etc/modprobe.d/i915.conf ]]; then
    echo "i915.conf:"
    cat /etc/modprobe.d/i915.conf
  fi
  if [[ -f /etc/modprobe.d/xe.conf ]]; then
    echo "xe.conf:"
    cat /etc/modprobe.d/xe.conf
  fi

  # Show hardware info if available
  if command -v hwinfo >/dev/null 2>&1; then
    hwinfo --display
  fi
}

get_gpu_id() {
  lspci -nn | grep -Ei 'VGA|DISPLAY' | grep '8086' | awk -F '8086:' '{print $2}' | awk '{print $1}' | sed 's/]$//' | sort -u
}

# Legacy enable_force_probe function (updated with kernel check)
enable_force_probe() {
  local gpu_id="$1"

  # Check if we're running a custom Intel kernel
  if ! is_custom_intel_kernel; then
    echo "Skipping legacy force_probe configuration - using generic/standard kernel"
    return 0
  fi
  if [ -n "$gpu_id" ]; then
    echo "Legacy force_probe configuration for GPU ID: $gpu_id"
    echo "$SUDO_PASSWORD" | sudo -S bash -c "echo 'options i915 force_probe=$gpu_id' > /etc/modprobe.d/i915.conf"
    echo "$SUDO_PASSWORD" | sudo -S update-initramfs -u -k all
    hwinfo --display
  else
    echo "Unable to determine GPU ID, GPU device not connected."
  fi
}

if [[ "${processor_type,,}" == *"xeon"* ]]; then
  echo -e "\nProcessor: $processor_type, Installing dGPU drivers..."
  # Use reusable repository setup function
  setup_intel_gpu_repositories true true

  # Use unified IGC management
  manage_igc_packages "allow" "gpu"

  # Install keyring and update package list
  echo "$SUDO_PASSWORD" | sudo -S apt install -y gpg-agent gnupg wget
  source /etc/os-release
  if [[ ! " jammy noble " =~ \ ${VERSION_CODENAME}\  ]]; then
      echo "Ubuntu version ${VERSION_CODENAME} not supported"
  else
      wget "https://repositories.intel.com/gpu/ubuntu/dists/${VERSION_CODENAME}/lts/2523/intel-gpu-ubuntu-${VERSION_CODENAME}-2523.run"
      chmod +x "intel-gpu-ubuntu-${VERSION_CODENAME}-2523.run"
      echo "$SUDO_PASSWORD" | sudo -S "./intel-gpu-ubuntu-${VERSION_CODENAME}-2523.run"
  fi

  # Install IGC packages
  manage_igc_packages "install" "gpu"

  # Fix any broken dependencies
  echo "Fixing broken dependencies..."
  echo "$SUDO_PASSWORD" | sudo -S apt --fix-broken install -y

  # Install compute runtime packages (excluding DKMS initially)
  echo "Installing basic compute runtime packages..."
  echo "$SUDO_PASSWORD" | sudo -S apt install -y \
    "linux-headers-$(uname -r)" \
    "linux-modules-extra-$(uname -r)" \
    flex bison \
    intel-fw-gpu xpu-smi

  # Install Intel i915 DKMS separately with kernel compatibility check
  kernel_version=$(uname -r)
  if [[ "$kernel_version" =~ (intel|vpptfcc|nonrt) ]] || [[ "$kernel_version" == *"6.12"* && "$kernel_version" != *"generic"* ]]; then
    echo "Intel custom kernel detected: $kernel_version"
    echo "Installing Intel i915 DKMS module..."
    if ! echo "$SUDO_PASSWORD" | sudo -S apt install -y intel-i915-dkms; then
      echo "WARNING: Intel i915 DKMS installation failed"
      cleanup_failed_dkms "intel-i915-dkms"
      echo "Continuing with installation..."
    else
      echo "Intel i915 DKMS module installed successfully"
    fi
  else
    echo "Generic/standard kernel detected: $kernel_version"
    echo "Skipping Intel i915 DKMS installation (incompatible with generic kernels)"
    echo ""
    echo "Note: Intel DKMS module is designed for Intel custom kernels"
    echo "Generic kernel drivers are already available and will be used"
    echo "For optimal Intel GPU performance, consider using Intel custom kernel (VPP/TFCC profile)"
  fi

  # Install Compute and Media runtime packages
  echo "Installing Compute and Media runtime packages..."
  if ! echo "$SUDO_PASSWORD" | sudo -S apt install -y \
    intel-opencl-icd libze-intel-gpu1 libze1 \
    intel-media-va-driver-non-free libmfx-gen1 libvpl2 \
    libegl-mesa0 libegl1-mesa-dev libgbm1 libgl1-mesa-dev libgl1-mesa-dri \
    libglapi-mesa libgles2-mesa-dev libglx-mesa0 libigdgmm12 libxatracker2 mesa-va-drivers \
    mesa-vdpau-drivers mesa-vulkan-drivers va-driver-all vainfo hwinfo clinfo \
    libigc-dev intel-igc-cm libigdfcl-dev libigfxcmrt-dev libze-dev; then

    echo "Some packages failed to install. Attempting individual installation..."
    # Try to install critical packages individually
    for pkg in intel-opencl-icd libze-intel-gpu1 libze1 intel-media-va-driver-non-free; do
      echo "Installing $pkg..."
      echo "$SUDO_PASSWORD" | sudo -S apt install -y "$pkg" || echo "Warning: Failed to install $pkg"
    done
  fi

  # Restore IGC restrictions
  manage_igc_packages "restrict" "gpu"

  # Skip if already configured during VPP kernel installation
  if [[ "$PROFILE" = "vpp" && (-f /etc/modprobe.d/i915.conf || -f /etc/modprobe.d/xe.conf) ]]; then
    echo "Force_probe already configured during VPP kernel installation, skipping..."
  else
    configure_force_probe
  fi

else
  echo -e "\nProcessor: $processor_type, Installing Client GPU drivers..."
  platform=$(grep "model name" /proc/cpuinfo | uniq | awk -F: '{print $2}' | xargs)
  echo "Platform: $platform"
  # ubuntu 24.04
  if [[ "$os_version" == "24.04" ]]; then
    # Use reusable repository setup function
    setup_intel_gpu_repositories true true

    # Update package cache
    echo "$SUDO_PASSWORD" | sudo -S apt-get update
    # Add the intel-graphics PPA.
    echo "$SUDO_PASSWORD" | sudo -S add-apt-repository -y ppa:kobuk-team/intel-graphics
    echo "$SUDO_PASSWORD" | sudo -S apt update

    # Use unified IGC management
    manage_igc_packages "allow" "gpu"

    # Install IGC packages first
    manage_igc_packages "install" "gpu"

    # Install unified Level-Zero
    install_level_zero_unified "gpu"

    # Install the compute-related packages.
    echo "Installing compute packages..."
    echo "$SUDO_PASSWORD" | sudo -S apt-get install -y --allow-downgrades \
      linux-headers-"$(uname -r)" \
      opencl-headers opencl-dev intel-fw-gpu \
      libgdal-dev libpugixml-dev libopencv-dev intel-metrics-discovery intel-gsc clinfo \
      intel-gpu-tools x11-xserver-utils powercap-utils cpufrequtils || true
    # Some dependencies might be missing, try to fix them
    echo "$SUDO_PASSWORD" | sudo -S apt-get --fix-broken install -y

    # Install OpenCL packages
    echo "Installing OpenCL packages..."
    if ! echo "$SUDO_PASSWORD" | sudo -S apt-get install -y --allow-downgrades intel-opencl-icd; then
      echo "OpenCL installation failed, trying to fix dependencies..."
      echo "$SUDO_PASSWORD" | sudo -S apt-get --fix-broken install -y
      echo "$SUDO_PASSWORD" | sudo -S apt-get install -y --allow-downgrades intel-opencl-icd || true
    fi

    # Install the media-related packages
    echo "Installing media packages..."
    echo "$SUDO_PASSWORD" | sudo -S apt-get install -y --allow-downgrades \
      intel-media-va-driver-non-free libmfx1 libmfx-gen1 libvpl2 libvpl-tools libva-glx2 va-driver-all vainfo hwinfo

    # Restore IGC restrictions
    manage_igc_packages "restrict" "gpu"

    # Skip if already configured during VPP kernel installation
    if [[ "$PROFILE" = "vpp" && (-f /etc/modprobe.d/i915.conf || -f /etc/modprobe.d/xe.conf) ]]; then
      echo "Force_probe already configured during VPP kernel installation, skipping..."
    else
      configure_force_probe
    fi
  else
    echo "Unsupported OS version for GPU driver installation: $os_version"
    exit 1
  fi

fi

# Add user to video and render groups
for grp in video render; do
  if ! id -nG "$USER" | grep -qw "$grp"; then
    echo "Adding current user to '$grp' group"
    echo "$SUDO_PASSWORD" | sudo -S usermod -aG "$grp" "$USER"
  fi
done

# Call GPU verification
verify_gpu_installation

sed -i 's/gpu_build_status=0/gpu_build_status=1/g' "$STATUS_DIR_FILE_PATH"

elapsedseconds=$SECONDS
echo "gpu build time = $((elapsedseconds))" >> "$PACKAGE_BUILD_TIME_FILE"

fi
if [ "$npu_enablement_build_status" -ne 1 ]; then
SECONDS=0
echo "*************************"
echo "    Installing NPU       "
echo "*************************"

os_version=$(grep 'VERSION_ID' /etc/os-release | cut -d '"' -f 2)
if [[ "$os_version" == *"24.04"* ]]; then
  echo -e "\nOS version is $os_version. Proceeding with NPU installation..."

  delete_folder_if_exists "npu"
  create_folder "npu"
  cd npu

  # Use unified Level-Zero installation
  install_level_zero_unified "npu"

  # Install NPU drivers
  echo "Installing NPU drivers and firmware..."
  echo "$SUDO_PASSWORD" | sudo -S dpkg --purge --force-remove-reinstreq intel-driver-compiler-npu intel-fw-npu intel-level-zero-npu 2>/dev/null || true

  wget_from_github "https://github.com/intel/linux-npu-driver/releases/download/v1.24.0/linux-npu-driver-v1.24.0.20251003-18218973328-ubuntu2404.tar.gz" "./linux-npu-driver-v1.24.0.20251003-18218973328-ubuntu2404.tar.gz"
  tar -xf linux-npu-driver-v1.24.0.20251003-18218973328-ubuntu2404.tar.gz

  echo "$SUDO_PASSWORD" | sudo -S apt update
  echo "$SUDO_PASSWORD" | sudo -S apt --fix-broken install -y
  echo "$SUDO_PASSWORD" | sudo -S apt install -y libtbb12
  echo "$SUDO_PASSWORD" | sudo -S dpkg -i ./*.deb

  # Set up udev rules
  echo "Setting up udev rules for NPU..."
  echo "$SUDO_PASSWORD" | sudo -S bash -c "echo 'SUBSYSTEM==\"accel\", KERNEL==\"accel*\", GROUP=\"render\", MODE=\"0660\"' > /etc/udev/rules.d/10-intel-vpu.rules"
  echo "$SUDO_PASSWORD" | sudo -S udevadm control --reload-rules
  echo "$SUDO_PASSWORD" | sudo -S udevadm trigger --subsystem-match=accel

  # Install compute runtime if NPU device exists
  # if [ -e /dev/accel/accel0 ]; then
    echo "NPU device found. Installing compute runtime..."
    # Allow IGC packages temporarily
    manage_igc_packages "allow" "npu"

    delete_folder_if_exists "neo"
    create_folder "neo"
    cd neo

    echo "$SUDO_PASSWORD" | sudo -S apt install -y ocl-icd-libopencl1
    # Install compatible compute runtime packages
    wget_from_github "https://github.com/intel/intel-graphics-compiler/releases/download/v2.18.5/intel-igc-core-2_2.18.5+19820_amd64.deb" "./intel-igc-core-2_2.18.5+19820_amd64.deb"
    wget_from_github "https://github.com/intel/intel-graphics-compiler/releases/download/v2.18.5/intel-igc-opencl-2_2.18.5+19820_amd64.deb" "./intel-igc-opencl-2_2.18.5+19820_amd64.deb"
    wget_from_github "https://github.com/intel/compute-runtime/releases/download/25.35.35096.9/intel-ocloc-dbgsym_25.35.35096.9-0_amd64.ddeb" "./intel-ocloc-dbgsym_25.35.35096.9-0_amd64.ddeb"
    wget_from_github "https://github.com/intel/compute-runtime/releases/download/25.35.35096.9/intel-ocloc_25.35.35096.9-0_amd64.deb" "./intel-ocloc_25.35.35096.9-0_amd64.deb"
    wget_from_github "https://github.com/intel/compute-runtime/releases/download/25.35.35096.9/libigdgmm12_22.8.1_amd64.deb" "./libigdgmm12_22.8.1_amd64.deb"
    echo "$SUDO_PASSWORD" | sudo -S dpkg -i --force-overwrite ./*.deb
    echo "$SUDO_PASSWORD" | sudo -S apt --fix-broken install -y

    cd ..
    delete_folder_if_exists "neo"

    # Restore IGC restrictions
    manage_igc_packages "restrict" "npu"
  # fi

  cd ..
  delete_folder_if_exists "npu"
else
  echo "Unsupported OS version: $os_version. NPU requires Ubuntu 24.04."
fi

sed -i 's/npu_enablement_build_status=0/npu_enablement_build_status=1/g' "$STATUS_DIR_FILE_PATH"

elapsedseconds=$SECONDS
echo "npu_enablement build time = $((elapsedseconds))" >> "$PACKAGE_BUILD_TIME_FILE"

fi

}

Install_AI_Tools () {

echo "Installing Install_AI_Tools"
if [ "$opencv_build_status" -ne 1 ]; then
SECONDS=0
echo "*************************"
echo "   Installing OpenCV     "
echo "*************************"
OPENCV_VERSION="4.12.0"
cd "$STATUS_DIR"
echo "$SUDO_PASSWORD" | sudo -S apt-get update
echo "$SUDO_PASSWORD" | sudo -S apt-get install -y cmake g++ wget unzip

# Remove existing opencv directory if present
if [ -d opencv ]; then
  rm -rf opencv
fi

repo_link="https://github.com/opencv/opencv.git"
# Clone the specified version of OpenCV
git_clone "$repo_link" "./opencv" "$OPENCV_VERSION"
cd opencv
mkdir -p build
cd build || exit 1

# Configure and build OpenCV
cmake ..
cmake --build . -- -j "$(nproc)"
echo "$SUDO_PASSWORD" | sudo -S make install

# Ensure cmake config is available at /usr/local/cmake/
echo "$SUDO_PASSWORD" | sudo -S mkdir -p /usr/local/cmake/
echo "$SUDO_PASSWORD" | sudo -S ln -sf /usr/local/lib/cmake/opencv4/* /usr/local/cmake/

cd ../..
rm -rf opencv

sed -i 's/opencv_build_status=0/opencv_build_status=1/g' "$STATUS_DIR_FILE_PATH"

elapsedseconds=$SECONDS
echo "opencv build time = $((elapsedseconds))" >> "$PACKAGE_BUILD_TIME_FILE"

fi
if [ "$ffmpeg_build_status" -ne 1 ]; then
SECONDS=0
echo "*************************"
echo "   Installing FFmpeg     "
echo "*************************"
cd "$STATUS_DIR"
# Install libvpl with fallback mechanism
echo "Attempting to install libvpl..."
LIBVPL_SUCCESS=0
if [ -d libvpl ]; then
  rm -rf libvpl
fi
# Try to install libvpl from system packages first
if echo "$SUDO_PASSWORD" | sudo -S apt-get install -y --allow-downgrades libvpl-dev libvpl2 2>/dev/null; then
  echo "libvpl installed from system packages"
  LIBVPL_SUCCESS=1
else
  echo "System packages not available, trying to build from source..."
  repo_link="https://github.com/intel/libvpl"
  if git_clone "$repo_link" "./libvpl"; then
    cd libvpl || exit 1
    # Try minimal dependency installation
    if echo "$SUDO_PASSWORD" | sudo -S apt-get install -y --allow-downgrades cmake pkg-config; then
      if echo "$SUDO_PASSWORD" | sudo -S script/bootstrap 2>/dev/null; then
        if cmake -B _build && cmake --build _build -- -j "$(nproc)"; then
          if echo "$SUDO_PASSWORD" | sudo -S cmake --install _build; then
            echo "$SUDO_PASSWORD" | sudo -S ldconfig
            LIBVPL_SUCCESS=1
            echo "libvpl built and installed successfully"
          fi
        fi
      fi
    fi
    cd .. || exit 1
    rm -rf libvpl
  fi
fi

if [ $LIBVPL_SUCCESS -eq 0 ]; then
  echo "Warning: libvpl installation failed. FFmpeg will be built without libvpl support."
  echo "This may affect some video processing capabilities."
fi

# Install cartwheel-ffmpeg
echo "*** Installing cartwheel-ffmpeg ***"
echo "$SUDO_PASSWORD" | sudo -S apt-get install -y yasm nasm
if [ -d cartwheel-ffmpeg ]; then
  rm -rf cartwheel-ffmpeg
fi
repo_link="https://github.com/intel/cartwheel-ffmpeg.git"
git_clone "$repo_link" "cartwheel-ffmpeg" "2025q1" true
cd cartwheel-ffmpeg/ffmpeg || exit 1
git checkout -b main
git config user.name "test"
git config user.email "test@intel.com"
git am ../patches/*.patch

if [ -f "configure" ]; then
  ./configure --enable-shared --enable-vaapi --enable-libvpl
  make -j "$(nproc)"
  echo "$SUDO_PASSWORD" | sudo -S make install
fi

cd ../.. || exit 1
rm -rf cartwheel-ffmpeg

sed -i 's/ffmpeg_build_status=0/ffmpeg_build_status=1/g' "$STATUS_DIR_FILE_PATH"

elapsedseconds=$SECONDS
echo "ffmpeg build time = $((elapsedseconds))" >> "$PACKAGE_BUILD_TIME_FILE"

fi
if [ "$openvino_native_build_status" -ne 1 ]; then
SECONDS=0
echo "*************************"
echo "   Installing OpenVINO   "
echo "*************************"
cd "$STATUS_DIR"
OPENVINO_VERSION="2025.3.0"
echo "*** installing openvino_$OPENVINO_VERSION ***"

# Create and activate a Python virtual environment
python3 -m venv profile_venv
# shellcheck source=/dev/null
source profile_venv/bin/activate

# Upgrade pip and install Python requirements
python3 -m pip install --upgrade pip

# Download and extract OpenVINO package
echo "$SUDO_PASSWORD" | sudo -S apt-get install -y curl
curl -L https://storage.openvinotoolkit.org/repositories/openvino/packages/2025.3/linux/openvino_toolkit_ubuntu24_2025.3.0.19807.44526285f24_x86_64.tgz --output openvino_$OPENVINO_VERSION.tgz
tar -xf openvino_$OPENVINO_VERSION.tgz
rm -f openvino_$OPENVINO_VERSION.tgz

# Remove any previous OpenVINO installation
if [ -d /opt/intel/openvino_$OPENVINO_VERSION ]; then
  echo "$SUDO_PASSWORD" | sudo -S rm -rf /opt/intel/openvino*
fi

# Move extracted files to target directory and set up symlinks
echo "$SUDO_PASSWORD" | sudo -S mkdir -p /opt/intel/openvino_$OPENVINO_VERSION
echo "$SUDO_PASSWORD" | sudo -S mv -f openvino_toolkit_ubuntu24_2025.3.0.19807.44526285f24_x86_64/* /opt/intel/openvino_$OPENVINO_VERSION
echo "$SUDO_PASSWORD" | sudo -S ln -sf /opt/intel/openvino_$OPENVINO_VERSION /opt/intel/openvino_2025
echo "$SUDO_PASSWORD" | sudo -S ln -sf /opt/intel/openvino_$OPENVINO_VERSION /opt/intel/openvino

# Patch install script for non-interactive install
echo "$SUDO_PASSWORD" | sudo -S sed -i 's/apt-get install/apt-get -y install/g' /opt/intel/openvino_2025.3.0/install_dependencies/install_openvino_dependencies.sh

# Install OpenVINO dependencies
echo "$SUDO_PASSWORD" | sudo -S /opt/intel/openvino/install_dependencies/install_openvino_dependencies.sh

# Install Python requirements for OpenVINO
python3 -m pip install -r /opt/intel/openvino/python/requirements.txt

# Source OpenVINO environment variables
# Temporarily disable strict error checking for the setupvars.sh script
disable_strict_mode
# shellcheck source=/dev/null
source /opt/intel/openvino_2025.3.0/setupvars.sh
# Re-enable strict error checking
enable_strict_mode

# Clean up extracted directory
rm -rf openvino_toolkit_ubuntu24_2025.3.0.19807.44526285f24_x86_64/

sed -i 's/openvino_native_build_status=0/openvino_native_build_status=1/g' "$STATUS_DIR_FILE_PATH"

elapsedseconds=$SECONDS
echo "openvino_native build time = $((elapsedseconds))" >> "$PACKAGE_BUILD_TIME_FILE"

fi
if [ "$dlstreamer_build_status" -ne 1 ]; then
SECONDS=0
echo "*************************"
echo "  Installing DL Streamer "
echo "*************************"
# Check if OpenCV is installed
opencv_config="/usr/local/cmake/OpenCVConfig-version.cmake"
if [[ -f "$opencv_config" ]]; then
  opencv_version=$(awk '/OpenCV_VERSION/ {print $2}' "$opencv_config" | sed 's/)//g')
  echo "OpenCV is installed. Version: $opencv_version"
else
  echo "OpenCV is required for DL Streamer. Please install OpenCV."
  exit 1
fi

# Check if OpenVINO is installed
openvino_setup="/opt/intel/openvino/setupvars.sh"
if [[ -f "$openvino_setup" ]]; then
  echo "OpenVINO is already installed."
else
  echo "OpenVINO is required for DL Streamer. Please install OpenVINO."
  exit 1
fi

# Check for HW compatibility
platform=$(grep "model name" /proc/cpuinfo | uniq | awk -F: '{print $2}' | xargs)
cpu_model=$(lscpu | awk -F: '/Model:/ {gsub(/ /, "", $2); print $2}')
if [[ -z "$cpu_model" ]]; then
  echo "Error: Unable to retrieve CPU model number."
  exit 1
fi

if [[ $cpu_model -eq 106 ]]; then
  echo "DLStreamer: Unsupported Platform: IceLake-$platform"
else
  echo "DLStreamer: Supported Platform: $platform"
  # Download Prerequisites Installation Script
  # DIR_NAME="dlstreamer_gst"
  # delete_folder_if_exists "$DIR_NAME"
  # create_folder "$DIR_NAME"
  # cd "$DIR_NAME"

  # echo "Downloading DLS prerequisites installation script..."
  # wget "https://github.com/dlstreamer/dlstreamer/raw/master/scripts/DLS_install_prerequisites.sh
  # echo "$SUDO_PASSWORD" | sudo -S chmod +x DLS_install_prerequisites.sh

  # echo "Modifying the prerequisites installation script to avoid reboot at run-time..."
  # Temporary workaround for the deb file list retrieval failure with wget function from compute-runtime repo latest release
  # Should remove it once that is fixed in open source.
  # sed -i '/^update_gpu_setup()/,/^}/ {/DEB_URLS2=/s/get_deb_urls_wget/get_deb_urls_no_api/}' DLS_install_prerequisites.sh
  # sed -i '/setup_npu/{n;s/need_to_reboot=1/need_to_reboot=0/;}' DLS_install_prerequisites.sh

  # echo "Executing Dprerequisites installation script..."
  # yes | ./DLS_install_prerequisites.sh

  # Setup Intel Repositories for DL Streamer Pipeline Framework
  echo "Setting up Intel repositories for DL Streamer installation..."

  # Set repository priorities first
  set_intel_repo_priorities

  echo "$SUDO_PASSWORD" | sudo -S wget -O- https://apt.repos.intel.com/intel-gpg-keys/GPG-PUB-KEY-INTEL-SW-PRODUCTS.PUB | gpg --dearmor | sudo tee /usr/share/keyrings/oneapi-archive-keyring.gpg > /dev/null
  echo "$SUDO_PASSWORD" | sudo -S wget -O- https://eci.intel.com/sed-repos/gpg-keys/GPG-PUB-KEY-INTEL-SED.gpg | sudo tee /usr/share/keyrings/sed-archive-keyring.gpg > /dev/null

  # Configure SED repository for Intel products
  echo "Configuring SED repository..."
  source /etc/os-release
  echo "$SUDO_PASSWORD" | sudo -S echo "deb [signed-by=/usr/share/keyrings/sed-archive-keyring.gpg] https://eci.intel.com/sed-repos/$VERSION_CODENAME sed main" | sudo tee /etc/apt/sources.list.d/sed.list
  # echo "$SUDO_PASSWORD" | sudo -S bash -c 'echo -e "Package: *\nPin: origin eci.intel.com\nPin-Priority: 1000" > /etc/apt/preferences.d/sed'
  echo "$SUDO_PASSWORD" | sudo -S bash -c 'echo -e "Package: *\nPin: origin eci.intel.com\nPin-Priority: 1200" > /etc/apt/preferences.d/sed'

  # Add repositories for Ubuntu 24
  echo "Configuring repository for Intel OpenVINO 2025 on Ubuntu24.04"
  echo "$SUDO_PASSWORD" | sudo -S bash -c 'echo "deb [signed-by=/usr/share/keyrings/oneapi-archive-keyring.gpg] https://apt.repos.intel.com/openvino/2025 ubuntu24 main" | sudo tee /etc/apt/sources.list.d/intel-openvino-2025.list'

  # Install Intel DL Streamer Pipeline Framework
  echo "$SUDO_PASSWORD" | sudo -S apt update
  echo "Installing Intel DL Streamer Pipeline Framework..."
  # echo "$SUDO_PASSWORD" | sudo -S apt-get install intel-dlstreamer=2025.1.2 -y
  echo "$SUDO_PASSWORD" | sudo -S apt-get install -y --allow-downgrades intel-dlstreamer=2025.1.2

  echo "Verifying installed packages for Intel DL Streamer..."
  echo "$SUDO_PASSWORD" | sudo -S dpkg -l | grep dlstreamer
  echo "Intel® DL Streamer installation completed successfully."
  fi

sed -i 's/dlstreamer_build_status=0/dlstreamer_build_status=1/g' "$STATUS_DIR_FILE_PATH"

elapsedseconds=$SECONDS
echo "dlstreamer build time = $((elapsedseconds))" >> "$PACKAGE_BUILD_TIME_FILE"

fi

}

Install_TPM () {

echo "Installing Install_TPM"
if [ "$discrete_tpm_build_status" -ne 1 ]; then
SECONDS=0
install_pigz_unified "TPM"

echo "****************************"
echo "    Installing TPM          "
echo "****************************"
cd "$STATUS_DIR"
docker pull ghcr.io/tpm2-software/ubuntu-22.04

sed -i 's/discrete_tpm_build_status=0/discrete_tpm_build_status=1/g' "$STATUS_DIR_FILE_PATH"

elapsedseconds=$SECONDS
echo "discrete_tpm build time = $((elapsedseconds))" >> "$PACKAGE_BUILD_TIME_FILE"

fi

}

Observability_Stack_Baremetal_OS () {

echo "Installing Observability_Stack_Baremetal_OS"
if [ "$intel_xpu_manager_build_status" -ne 1 ]; then
SECONDS=0
echo "*************************"
echo "   Installing XPU SMI    "
echo "*************************"
cd "$STATUS_DIR"

# Check if XPU SMI is already installed
if command -v xpu-smi >/dev/null 2>&1; then
  echo "[SKIP] XPU SMI is already installed"
  xpu-smi version 2>/dev/null || echo "XPU SMI available (requires GPU devices for full functionality)"
  sed -i 's/intel_xpu_manager_build_status=0/intel_xpu_manager_build_status=1/g' "$STATUS_DIR_FILE_PATH"

  elapsedseconds=$SECONDS
  echo "intel_xpu_manager build time = $((elapsedseconds))" >> "$PACKAGE_BUILD_TIME_FILE"
else
  # Use reusable repository setup function
  setup_intel_gpu_repositories true true

  delete_folder_if_exists "xpu-smi"
  create_folder "xpu-smi"
  cd xpu-smi

  # Allow IGC packages temporarily
  manage_igc_packages "allow" "xpu"

  echo "Installing XPU SMI dependencies..."
  echo "$SUDO_PASSWORD" | sudo -S apt-get install -y --allow-downgrades intel-gsc libmetee-dev intel-metrics-library

  # Use unified Level-Zero installation
  install_level_zero_unified "xpu"

  # Install IGC packages
  manage_igc_packages "install" "xpu"

  # Download and install XPU SMI
  xpu_smi_url="https://github.com/intel/xpumanager/releases/download/v1.3.3/xpu-smi_1.3.3_20250926.101214.8a6b6526.u24.04_amd64.deb"
  echo "Downloading and installing XPU SMI..."

  if wget_from_github "$xpu_smi_url" "xpu-smi_1.3.3_20250926.101214.8a6b6526.u24.04_amd64.deb"; then
    echo "$SUDO_PASSWORD" | sudo -S dpkg -i ./*.deb || {
      echo "$SUDO_PASSWORD" | sudo -S apt-get --fix-broken install -y
      echo "$SUDO_PASSWORD" | sudo -S dpkg -i ./*.deb
    }
    echo "✓ XPU SMI installed successfully"
  else
    echo "✗ Failed to download XPU SMI package"
  fi

  # Restore IGC restrictions
  manage_igc_packages "restrict" "xpu"

  cd ..
  delete_folder_if_exists "xpu-smi"

  # Verify installation
  if command -v xpu-smi >/dev/null 2>&1; then
    echo "✓ XPU SMI command available"
    xpu-smi version 2>/dev/null || echo "XPU SMI installed (requires GPU devices for full functionality)"
  fi
fi

sed -i 's/intel_xpu_manager_build_status=0/intel_xpu_manager_build_status=1/g' "$STATUS_DIR_FILE_PATH"

elapsedseconds=$SECONDS
echo "intel_xpu_manager build time = $((elapsedseconds))" >> "$PACKAGE_BUILD_TIME_FILE"

fi
if [ "$prometheus_build_status" -ne 1 ]; then
SECONDS=0
echo "*************************"
echo " Installing Prometheus   "
echo "*************************"

# Disable strict mode for the critical file operations
disable_strict_mode

install_pigz_unified "Prometheus"

# Set variables
SERVICE_FILE="/etc/systemd/system/prometheus.service"
PROMETHEUS_BIN="/usr/local/bin/prometheus"
CONFIG_FILE="/usr/local/prometheus/prometheus.yml"
REPO_URL="https://api.github.com/repos/prometheus/prometheus/releases/latest"

# Try to get latest version with timeout and fallback
echo "Attempting to fetch latest Prometheus version..."
DOWNLOAD_URL=""
ATTEMPT=0
MAX_ATTEMPTS=3

while [ -z "$DOWNLOAD_URL" ] && [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
  echo "Attempt $((ATTEMPT + 1)) of $MAX_ATTEMPTS to fetch release info..."
  DOWNLOAD_URL=$(timeout 30 curl -s --connect-timeout 10 --max-time 30 "$REPO_URL" | grep "browser_download_url.*linux-amd64.tar.gz" | cut -d '"' -f 4 | head -n1)

  if [ -z "$DOWNLOAD_URL" ]; then
    echo "Failed to fetch latest version info, trying again..."
    ATTEMPT=$((ATTEMPT + 1))
    sleep 5
  else
    echo "Successfully retrieved download URL: $DOWNLOAD_URL"
    break
  fi
done

# Fallback to known stable version if API calls fail
if [ -z "$DOWNLOAD_URL" ]; then
  echo "API requests failed, using fallback version..."
  DOWNLOAD_URL="https://github.com/prometheus/prometheus/releases/download/v3.5.0/prometheus-3.5.0.linux-amd64.tar.gz"
fi

TARBALL_NAME=$(basename "$DOWNLOAD_URL")
# Download the release tarball with progress and timeout
echo "Downloading Prometheus from $DOWNLOAD_URL..."
if ! timeout 600 curl -L --connect-timeout 30 --max-time 600 --progress-bar "$DOWNLOAD_URL" -o "$TARBALL_NAME"; then
  echo "Download failed. Trying alternative download method..."
  if ! timeout 600 wget --timeout=30 --tries=3 --progress=bar:force "$DOWNLOAD_URL" -O "$TARBALL_NAME"; then
    echo "ERROR: Failed to download Prometheus. Please check your internet connection."
    exit 1
  fi
fi

# Verify the download
if [ ! -f "$TARBALL_NAME" ] || [ ! -s "$TARBALL_NAME" ]; then
  echo "ERROR: Downloaded file is missing or empty"
  exit 1
fi

# Extract the tarball
echo "Extracting $TARBALL_NAME..."
if ! tar -xzf "$TARBALL_NAME"; then
  echo "ERROR: Failed to extract $TARBALL_NAME"
  exit 1
fi

# echo "Checking and deleting any previous instance of /usr/local/prometheus"
# if [[ -d "/usr/local/prometheus" ]]; then
  # echo "Found a previous instance of /usr/local/prometheus folder. Deleting it.."
  # echo "$SUDO_PASSWORD" | sudo -S rm -rf /usr/local/prometheus
# fi

echo "Checking and deleting any previous instance of /usr/local/prometheus"
if [[ -d "/usr/local/prometheus" ]]; then
  echo "Found a previous instance of /usr/local/prometheus folder. Deleting it.."
  if ! echo "$SUDO_PASSWORD" | sudo -S rm -rf /usr/local/prometheus; then
    echo "ERROR: Failed to remove existing /usr/local/prometheus directory"
    exit 1
  fi
else
  echo "No previous instance found. Proceeding with installation."
fi

# Move the binaries to the install directory
EXTRACTED_DIR=$(tar -tzf "$TARBALL_NAME" | head -1 | cut -f1 -d"/")
echo "Moving extracted directory: $EXTRACTED_DIR"
echo "$SUDO_PASSWORD" | sudo -S mv -f "$EXTRACTED_DIR" /usr/local/prometheus
echo "$SUDO_PASSWORD" | sudo -S ln -sf /usr/local/prometheus/prometheus  /usr/local/bin/prometheus
echo "$SUDO_PASSWORD" | sudo -S ln -sf /usr/local/prometheus/promtool  /usr/local/bin/promtool

# Clean up
rm -rf "$TARBALL_NAME" "$EXTRACTED_DIR"

# Checking version
echo "***Checking version***"
if prometheus --version; then
  echo "***prometheus installed successfully***"
else
  echo "ERROR: Prometheus installation verification failed"
  exit 1
fi

# Configure Prometheus Service
# check if the Prometheus binary exists
if [[ ! -f "$PROMETHEUS_BIN" ]]; then
  echo "ERROR: Prometheus binary not found at $PROMETHEUS_BIN"
  exit 1
fi

# create the Prometheus systemd service file
echo "Creating systemd service file for Prometheus..."

# Create a System Group for Prometheus if it doesn't exist
if ! getent group prometheus > /dev/null; then
  echo "Creating prometheus group..."
  echo "$SUDO_PASSWORD" | sudo -S groupadd --system prometheus
else
  echo "Group 'prometheus' already exists. Skipping group creation."
fi

# Create a System User for Prometheus if it doesn't exist
if ! id -u prometheus > /dev/null 2>&1; then
  echo "Creating prometheus user..."
  echo "$SUDO_PASSWORD" | sudo -S useradd -s /sbin/nologin --system -g prometheus prometheus
else
  echo "User 'prometheus' already exists. Skipping user creation."
fi

# Create Directories for Prometheus
echo "$SUDO_PASSWORD" | sudo -S mkdir -p /etc/prometheus
echo "$SUDO_PASSWORD" | sudo -S mkdir -p /var/lib/prometheus

# Copy binary files and configuration Files & Set Owner
echo "$SUDO_PASSWORD" | sudo -S chown prometheus:prometheus /usr/local/bin/prometheus
echo "$SUDO_PASSWORD" | sudo -S chown prometheus:prometheus /usr/local/bin/promtool

echo "$SUDO_PASSWORD" | sudo -S cp -r /usr/local/prometheus/prometheus.yml /etc/prometheus

echo "$SUDO_PASSWORD" | sudo -S chown prometheus:prometheus /etc/prometheus
echo "$SUDO_PASSWORD" | sudo -S chown -R prometheus:prometheus /var/lib/prometheus

# Create the service file content
echo "$SUDO_PASSWORD" | sudo -S bash -c "cat > $SERVICE_FILE <<EOF
[Unit]
Description=Prometheus
Wants=network-online.target
After=network-online.target

[Service]
User=prometheus
Group=prometheus
Type=simple
ExecStart=$PROMETHEUS_BIN \\
    --config.file $CONFIG_FILE \\
    --storage.tsdb.path /var/lib/prometheus/

[Install]
WantedBy=multi-user.target
EOF"

if [[ -f "$SERVICE_FILE" ]]; then
  echo "Service file created successfully at $SERVICE_FILE"
else
  echo "ERROR: Failed to create service file."
  exit 1
fi

# reload systemd, enable and start the service
echo "Reloading systemd and starting Prometheus service..."
# Reload systemd configuration to recognize the new service
echo "$SUDO_PASSWORD" | sudo -S systemctl daemon-reload
# Enable the Prometheus service to start on boot
echo "$SUDO_PASSWORD" | sudo -S systemctl enable prometheus.service
# Start the Prometheus service
echo "$SUDO_PASSWORD" | sudo -S systemctl start prometheus.service
# Check the status of the Prometheus service
systemctl status prometheus.service --no-pager

if systemctl is-active --quiet prometheus.service; then
  echo "Prometheus service started successfully."
else
  echo "ERROR: Failed to start Prometheus service."
  systemctl status prometheus.service --no-pager
  exit 1
fi

# Re-enable strict mode after the critical section
enable_strict_mode

sed -i 's/prometheus_build_status=0/prometheus_build_status=1/g' "$STATUS_DIR_FILE_PATH"

elapsedseconds=$SECONDS
echo "prometheus build time = $((elapsedseconds))" >> "$PACKAGE_BUILD_TIME_FILE"

fi
if [ "$grafana_build_status" -ne 1 ]; then
SECONDS=0
echo "****************************"
echo "   Installing Grafana       "
echo "****************************"
# Define variables
SERVICE_FILE="/etc/systemd/system/grafana-server.service"
GRAFANA_USER="grafana"
GRAFANA_GROUP="grafana"
GRAFANA_BIN="/usr/share/grafana/bin/grafana"
GRAFANA_CONFIG="/etc/grafana/grafana.ini"
GRAFANA_PID="/run/grafana/grafana-server.pid"
GRAFANA_LOG="/var/log/grafana"
GRAFANA_DATA="/var/lib/grafana"
GRAFANA_PLUGINS="/var/lib/grafana/plugins"
PROVISIONING_DIR="/etc/grafana/provisioning"
TMPFILES_CONF="/etc/tmpfiles.d/grafana.conf"
DASHBOARD_DIR="/usr/share/grafana/public/dashboards/"

echo \"Source Ref. https://grafana.com/docs/grafana/latest/setup-grafana/installation/bma/\"
cd "$STATUS_DIR"

echo \"***Installing the prerequisite packages***\"
echo "$SUDO_PASSWORD" | sudo -S apt-get install -y apt-transport-https software-properties-common wget
# Importing the GPG key
echo \"***Importing the GPG key***\"
mkdir -p /etc/apt/keyrings/
wget -q -O - https://apt.grafana.com/gpg.key | gpg --dearmor | sudo tee /etc/apt/keyrings/grafana.gpg > /dev/null

# Check if the repository entry already exists
echo "***Checking if Grafana repository exists***"
REPO_LINE="deb [signed-by=/etc/apt/keyrings/grafana.gpg] https://apt.grafana.com stable main"
GRAFANA_LIST="/etc/apt/sources.list.d/grafana.list"
if [ -f "$GRAFANA_LIST" ] && grep -Fxq "$REPO_LINE" "$GRAFANA_LIST"; then
  echo "Grafana repository already exists in $GRAFANA_LIST"
else
  echo "***Adding a repository for latest stable releases***"
  echo "$REPO_LINE" | sudo tee -a "$GRAFANA_LIST"
  echo "Grafana repository added successfully"
fi

# Updating the list of available packages
echo \"***Updating the list of available packages***\"
echo "$SUDO_PASSWORD" | sudo -S apt-get update

# Installing the latest Grafana OSS release
echo \"***Installing the latest Grafana OSS release***\"
echo "$SUDO_PASSWORD" | sudo -S apt-get install grafana -y
echo "$SUDO_PASSWORD" | sudo -S ln -sf /usr/share/grafana/bin/grafana  /usr/local/bin/grafana
echo "$SUDO_PASSWORD" | sudo -S ln -sf /usr/share/grafana/bin/grafana-cli  /usr/local/bin/grafana-cli
echo "$SUDO_PASSWORD" | sudo -S ln -sf /usr/share/grafana/bin/grafana-server  /usr/local/bin/grafana-server

# Checking version
echo "***Checking version***"
grafana --version
echo "***Grafana installed successfully***"

# create systemd service file
echo "Creating systemd service file for Grafana..."
cat <<EOF | sudo tee $SERVICE_FILE > /dev/null
[Unit]
Description=Grafana instance
Documentation=http://docs.grafana.org
Wants=network-online.target
After=network-online.target

[Service]
EnvironmentFile=-/etc/default/grafana-server
User=$GRAFANA_USER
Group=$GRAFANA_GROUP
Type=simple
ExecStart=$GRAFANA_BIN server \\
  --homepath=/usr/share/grafana \\
  --config=$GRAFANA_CONFIG \\
  --pidfile=$GRAFANA_PID \\
  --packaging=deb \\
  cfg:default.paths.logs=$GRAFANA_LOG \\
  cfg:default.paths.data=$GRAFANA_DATA \\
  cfg:default.paths.plugins=$GRAFANA_PLUGINS \\
  cfg:default.paths.provisioning=$PROVISIONING_DIR
Restart=on-failure
RestartSec=5
LimitNOFILE=10000
TimeoutStopSec=20
SyslogIdentifier=grafana

[Install]
WantedBy=multi-user.target
EOF

# Create the PID directory and set permissions
# echo "Creating PID directory and setting permissions..."
# mkdir -p /run/grafana
# chown $GRAFANA_USER:$GRAFANA_GROUP /run/grafana

# Enable write permissions to the PID file
# touch /run/grafana/grafana-server.pid
# chown $GRAFANA_USER:$GRAFANA_GROUP /run/grafana/grafana-server.pid

# Configure tmpfiles.d for /run/grafana directory
echo "Configuring tmpfiles.d for /run/grafana..."
cat <<EOF | sudo tee $TMPFILES_CONF > /dev/null
d /run/grafana 0755 $GRAFANA_USER $GRAFANA_GROUP -
EOF

# Reload tmpfiles and create /run/grafana directory
echo "$SUDO_PASSWORD" | sudo -S systemd-tmpfiles --create

# Check and create provisioning directory
if [ ! -d "$PROVISIONING_DIR/datasources" ]; then
  echo "Creating provisioning directory..."
  echo "$SUDO_PASSWORD" | sudo -S mkdir -p $PROVISIONING_DIR/datasources
  echo "$SUDO_PASSWORD" | sudo -S chown -R $GRAFANA_USER:$GRAFANA_GROUP /etc/grafana/provisioning
fi

# Check and create dashboard directory
if [ ! -d "$PROVISIONING_DIR/dashboard" ]; then
  echo "Creating dashboard directory..."
  echo "$SUDO_PASSWORD" | sudo -S mkdir -p $PROVISIONING_DIR/dashboard
  echo "$SUDO_PASSWORD" | sudo -S chown -R $GRAFANA_USER:$GRAFANA_GROUP /etc/grafana/provisioning
fi

echo "Creating Prometheus data source configuration..."
echo "$SUDO_PASSWORD" | sudo -S touch $PROVISIONING_DIR/datasources/prometheus.yaml
echo "$SUDO_PASSWORD" | sudo -S chown $GRAFANA_USER:$GRAFANA_GROUP $PROVISIONING_DIR/datasources/prometheus.yaml
cat <<EOF | sudo tee $PROVISIONING_DIR/datasources/prometheus.yaml > /dev/null
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://localhost:9090
    isDefault: true
EOF

# Create dashboard provider configuration
echo "Creating dashboard provider configuration..."
cat <<EOF | sudo tee $PROVISIONING_DIR/dashboards/default.yaml > /dev/null
apiVersion: 1
providers:
  - name: 'default'
    orgId: 1
    folder: ''
    type: file
    disableDeletion: false
    updateIntervalSeconds: 10
    options:
      path: $DASHBOARD_DIR
EOF

# add the node exporter data source and dashboard to the grafana configuration
# URL to download the Node Exporter JSON for Grafana
URL="https://grafana.com/api/dashboards/1860/revisions/37/download"
# Output file name
OUTPUT_FILE="node_exporter_grafana-dashboard.json"

# Download the file using curl
curl -L $URL -o $OUTPUT_FILE
curl_exit_code=$?

# Check if the download was successful
if [ $curl_exit_code -eq 0 ]; then
  echo "Dashboard downloaded successfully as $OUTPUT_FILE"
else
  echo "Failed to download the dashboard."
  exit 1
fi

# Move the downloaded JSON file to the provisioning directory
echo "$SUDO_PASSWORD" | sudo -S mv $OUTPUT_FILE /usr/share/grafana/public/dashboards/home.json


# reload systemd daemon
echo "$SUDO_PASSWORD" | sudo -S systemctl daemon-reload
# enable Grafana service
echo "$SUDO_PASSWORD" | sudo -S systemctl enable grafana-server.service
# start Grafana service
echo "$SUDO_PASSWORD" | sudo -S systemctl start grafana-server.service
# check Grafana service status
echo "Checking Grafana service status..."
echo "$SUDO_PASSWORD" | sudo -S systemctl status grafana-server.service

# Configure firewall
echo "Configuring firewall..."
echo "$SUDO_PASSWORD" | sudo -S ufw allow ssh
echo "$SUDO_PASSWORD" | sudo -S ufw allow 3000/tcp
echo "y" | sudo ufw enable

echo "Grafana installation and setup completed successfully."

sed -i 's/grafana_build_status=0/grafana_build_status=1/g' "$STATUS_DIR_FILE_PATH"

elapsedseconds=$SECONDS
echo "grafana build time = $((elapsedseconds))" >> "$PACKAGE_BUILD_TIME_FILE"

fi
if [ "$node_exporter_build_status" -ne 1 ]; then
SECONDS=0
echo "****************************"
echo "  Installing Node Exporter  "
echo "****************************"
# Define variables
NODE_EXPORTER_VERSION="1.9.1"
NODE_EXPORTER_URL="https://github.com/prometheus/node_exporter/releases/download/v${NODE_EXPORTER_VERSION}/node_exporter-${NODE_EXPORTER_VERSION}.linux-amd64.tar.gz"
#NODE_EXPORTER_DIR="/usr/local/bin/node_exporter-${NODE_EXPORTER_VERSION}.linux-amd64"
NODE_EXPORTER_BIN="/usr/local/bin/node_exporter"
WORK_DIR="$HOME/node_exporter"
#DASHBOARD_JSON_PATH="/usr/share/grafana/public/dashboards/home.json"
GRAFANA_CONFIG="/etc/grafana/grafana.ini"
PROMETHEUS_CONFIG="/usr/local/prometheus/prometheus.yml"

# Create working directory
mkdir -p "${WORK_DIR}"

# Download Node Exporter
echo "Downloading Node Exporter version ${NODE_EXPORTER_VERSION}..."
wget_from_github "${NODE_EXPORTER_URL}" "${WORK_DIR}"/node_exporter-"${NODE_EXPORTER_VERSION}".linux-amd64.tar.gz

# Extract tar file 
echo "Extracting Node Exporter..."
tar -xzf "${WORK_DIR}"/node_exporter-"${NODE_EXPORTER_VERSION}".linux-amd64.tar.gz -C "${WORK_DIR}"

# Move the binary to /usr/local/bin
echo "Installing Node Exporter..."
echo "$SUDO_PASSWORD" | sudo -S mv "${WORK_DIR}"/node_exporter-"${NODE_EXPORTER_VERSION}".linux-amd64/node_exporter "${NODE_EXPORTER_BIN}"
echo "$SUDO_PASSWORD" | sudo -S chmod +x "${NODE_EXPORTER_BIN}"

# Clean up
echo "Cleaning up..."
rm -rf "${WORK_DIR}"/node_exporter-"${NODE_EXPORTER_VERSION}".linux-amd64
rm -f "${WORK_DIR}"/node_exporter-"${NODE_EXPORTER_VERSION}".linux-amd64.tar.gz

# Create node_exporter user and group
if getent group "node_exporter"; then
  echo "Group 'node_exporter' already exists."
else
  echo "Group 'node_exporter' does not exist. Creating group..."
  echo "$SUDO_PASSWORD" | sudo -S groupadd "node_exporter"
  echo "Group 'node_exporter' created."
fi
# Check if the node_exporter user exists
if ! id -u node_exporter > /dev/null 2>&1; then
  echo "Creating node_exporter user..."
  echo "$SUDO_PASSWORD" | sudo -S useradd --no-create-home --shell /bin/false --system -g node_exporter node_exporter
else
  echo "User 'node_exporter' already exists. Skipping user creation."
fi

# Change ownership of the node_exporter binary
echo "$SUDO_PASSWORD" | sudo -S chown node_exporter:node_exporter "${NODE_EXPORTER_BIN}"

# Create systemd service file
echo "Creating systemd service file..."
echo "$SUDO_PASSWORD" | sudo -S bash -c "cat > /etc/systemd/system/node_exporter.service <<'EOL'
[Unit]
Description=Node Exporter
Wants=network-online.target
After=network-online.target

[Service]
User=node_exporter
Group=node_exporter
ExecStart=${NODE_EXPORTER_BIN}
Restart=on-failure

[Install]
WantedBy=default.target
EOL"

# Reload systemd, enable and start Node Exporter service
echo "Enabling and starting Node Exporter service..."
echo "$SUDO_PASSWORD" | sudo -S systemctl daemon-reload
echo "$SUDO_PASSWORD" | sudo -S systemctl enable node_exporter.service
echo "$SUDO_PASSWORD" | sudo -S systemctl start node_exporter.service

# Check the status of the service
echo "Checking Node Exporter service status..."
echo "$SUDO_PASSWORD" | sudo -S systemctl status node_exporter.service
echo "Node Exporter installation done."

# add node exporter to Prometheus Configuration File
if [ -f /usr/local/prometheus/prometheus.yml ]; then
echo "Adding node_exporter scrape config to Prometheus..."
echo "
  - job_name: 'node_exporter'
    static_configs:
      - targets: ['localhost:9100']
" | sudo tee -a $PROMETHEUS_CONFIG > /dev/null

# Restart Prometheus Service to apply changes
echo "Restarting Prometheus service to apply new scrape configuration..."
echo "$SUDO_PASSWORD" | sudo -S systemctl daemon-reload
#echo "$SUDO_PASSWORD" | sudo -S systemctl restart prometheus.service

if echo "$SUDO_PASSWORD" | sudo -S systemctl restart prometheus.service; then
  echo " Prometheus service restarted successfully."
else
  echo "Failed to restart Prometheus service."
  exit 1
fi
echo "Node Exporter: Prometheus configuration completed ."
else
  echo "Prometheus.yml does not exist."
fi

sed -i 's/node_exporter_build_status=0/node_exporter_build_status=1/g' "$STATUS_DIR_FILE_PATH"

elapsedseconds=$SECONDS
echo "node_exporter build time = $((elapsedseconds))" >> "$PACKAGE_BUILD_TIME_FILE"

fi
if [ "$intel_xpum_container_build_status" -ne 1 ]; then
SECONDS=0
echo "****************************"
echo " Installing XPUM Container  "
echo "****************************"

# Define variables
PROMETHEUS_CONFIG="/usr/local/prometheus/prometheus.yml"
XPUM_REPO="https://github.com/intel/xpumanager.git"
XPUM_SRC_ROOT="$(pwd)/xpumanager"
XPUM_IMAGE="intel/xpumanager:latest"
#PRC_XPUM_IMAGE="docker.m.daocloud.io/intel/xpumanager:latest"
REST_CONF_DIR="$(pwd)/rest/conf"
REST_PORT=12345
CONTAINER_NAME="xpum_container"
DAEMON_JSON="/etc/docker/daemon.json"

MIRRORS=$(jq -r '."registry-mirrors" // [] | join (", ")' "$DAEMON_JSON")
if [ -z "$MIRRORS" ]; then
  echo "No Mirrors specified"
else
  echo "Current registry-mirrors in $DAEMON_JSON"
  echo "$MIRRORS"
fi

# Generate a random password
XPUM_API_PASSWORD=$(openssl rand -base64 12)
export XPUM_API_PASSWORD

echo "$SUDO_PASSWORD" | sudo -S apt-get install expect -y
echo "Setting up XPUM docker container..."
# Check if xpumanager directory exists and remove it
if [ -d "$XPUM_SRC_ROOT" ]; then
  echo "Removing existing xpumanager directory..."
  rm -rf "$XPUM_SRC_ROOT"
fi

# Clone the xpumanager repository
echo "Cloning xpumanager repository..."
#git clone function
git_clone "$XPUM_REPO" "./xpumanager"

# Create rest configuration directory
echo "Creating rest configuration directory..."
mkdir -p "$REST_CONF_DIR"
echo "$SUDO_PASSWORD" | sudo -S "$XPUM_SRC_ROOT"/install/tools/rest/keytool.sh --owner=root --group=root
# Run rest_config.py script with expect to automate password entry
echo "Running rest_config.py script..."
expect <<EOF
spawn sudo $XPUM_SRC_ROOT/install/tools/rest/rest_config.py --owner=root --group=root
expect "password for"
send "$SUDO_PASSWORD\r"
expect "Please enter password for REST API user xpumadmin, min 8 characters"
send "$XPUM_API_PASSWORD\r"
expect "Confirm password:"
send "$XPUM_API_PASSWORD\r"
expect eof
EOF


if docker pull "$XPUM_IMAGE"; then
  echo "Image is pulled successfully."
else
  echo "Tried with the Mirrors $MIRRORS and docker.io"
  echo "Failed to pull the Intel xpumanager image"
  read -r -p "Please enter another known mirror for XPUM image (example:, https://registry.docker-cn.com): " USER_MIRROR
  echo "$SUDO_PASSWORD" | sudo -S jq --arg user_mirror "$USER_MIRROR"   '."registry-mirrors" = (."registry-mirrors" // []) + [$user_mirror] | ."registry-mirrors" |= unique' \
  "$DAEMON_JSON" | tee tmp_daemon.json > /dev/null && echo "$SUDO_PASSWORD" | sudo -S mv -f tmp_daemon.json "$DAEMON_JSON"

  echo "$SUDO_PASSWORD" | sudo -S systemctl daemon-reload
  echo "$SUDO_PASSWORD" | sudo -S systemctl restart docker
  if docker pull "$XPUM_IMAGE"; then
    echo "xpumanager image has been downloaded successfully"
  else
    echo "None of the known mirrors worked."
    echo "Please try to pull the image offline with other known mirrors and retry the execution"
    exit 1
  fi
fi

# Stop any existing container with the same name
echo "Stopping any existing XPUM docker container..."
docker stop "$CONTAINER_NAME" 2>/dev/null || true
docker rm "$CONTAINER_NAME" 2>/dev/null || true

# Run the XPUM docker container in the background
echo "Running XPUM docker container in the background..."
echo "$SUDO_PASSWORD" | sudo -S docker run -d --name "$CONTAINER_NAME" --cap-drop ALL --cap-add=SYS_ADMIN \
    --network host \
    --device /dev/dri:/dev/dri \
    -v "$REST_CONF_DIR:/usr/lib/xpum/rest/conf:ro" \
    -e XPUM_REST_NO_TLS=1 \
    -e XPUM_REST_PORT="$REST_PORT" \
    --restart unless-stopped \
    "$XPUM_IMAGE"

echo "XPUM docker container setup and systemd service creation completed successfully."
# Edit Prometheus Configuration File
if [ -f /usr/local/prometheus/prometheus.yml ]; then
echo "Editing Prometheus configuration file: $PROMETHEUS_CONFIG"
# Adding node_exporter config under scrape_configs
echo "Adding xpu_exporter scrape config to Prometheus..."

printf "
  - job_name: 'xpu-gpu-exporter'
    scheme: http
    basic_auth:
      username: 'xpumadmin'
      password: '%s'
    tls_config:
      insecure_skip_verify: true

    static_configs:
      - targets: ['localhost:12345']
" "$XPUM_API_PASSWORD" | sudo tee -a $PROMETHEUS_CONFIG > /dev/null

# Restart Prometheus Service to apply changes
echo "Restarting Prometheus service to apply new scrape configuration..."
echo "$SUDO_PASSWORD" | sudo -S systemctl daemon-reload
#echo "$SUDO_PASSWORD" | sudo -S systemctl restart prometheus.service

if echo "$SUDO_PASSWORD" | sudo -S systemctl restart prometheus.service; then
  echo " Prometheus service restarted successfully."
else
  echo "Failed to restart Prometheus service."
  exit 1
fi
echo "XPU Exporter: Prometheus configuration completed"
else
  echo "Prometheus does not exist."
fi

# add xpu manager dashboard to grafana dashboard location
# add xpu dashboard
echo "$SUDO_PASSWORD" | sudo -S cp "$XPUM_SRC_ROOT"/rest/grafana-dashboard.json /usr/share/grafana/public/dashboards
# Define file path variable
GRAFANA_DASHBOARD_FILE="/usr/share/grafana/public/dashboards/grafana-dashboard.json"
# Check if the file exists
if [[ ! -f "$GRAFANA_DASHBOARD_FILE" ]]; then
  echo "ERROR: Grafana dashboard file not found at $GRAFANA_DASHBOARD_FILE"
  exit 1
fi

# Backup the original file
echo "$SUDO_PASSWORD" | sudo -S cp "$GRAFANA_DASHBOARD_FILE" "$GRAFANA_DASHBOARD_FILE.bak"
echo "Backup created at $GRAFANA_DASHBOARD_FILE.bak"

# Modify the definition and query fields within the templating section
# Use sed and jq to perform replacements in the JSON file
# Replace the definition value with instance"
echo "$SUDO_PASSWORD" | sudo -S sed -i 's|"definition": "label_values(xpum_power_watts, node)"|"definition": "label_values(instance)"|' "$GRAFANA_DASHBOARD_FILE"

# Replace the query value with instance"
echo "$SUDO_PASSWORD" | sudo -S jq '.templating.list[].query.query = "label_values(instance)"' "$GRAFANA_DASHBOARD_FILE" | sudo tee temp.json > /dev/null && echo "$SUDO_PASSWORD" | sudo -S mv temp.json "$GRAFANA_DASHBOARD_FILE"

echo "Updated grafana-dashboard.json file."
# reload systemd daemon
echo "$SUDO_PASSWORD" | sudo -S systemctl daemon-reload
echo "$SUDO_PASSWORD" | sudo -S systemctl restart grafana-server.service
# check Grafana service status
echo "Checking Grafana service status..."
echo "$SUDO_PASSWORD" | sudo -S systemctl status grafana-server.service

sed -i 's/intel_xpum_container_build_status=0/intel_xpum_container_build_status=1/g' "$STATUS_DIR_FILE_PATH"

elapsedseconds=$SECONDS
echo "intel_xpum_container build time = $((elapsedseconds))" >> "$PACKAGE_BUILD_TIME_FILE"

fi
if [ "$cadvisor_build_status" -ne 1 ]; then
SECONDS=0
echo "****************************"
echo "   Installing CADVISOR      "
echo "****************************"
cd "$STATUS_DIR"
VERSION=v0.49.1
CONTAINER_NAME="cadvisor"
CADVISOR_IMG="gcr.io/cadvisor/cadvisor"
PRC_GCR_IMAGE="swr.cn-north-4.myhuaweicloud.com/ddn-k8s/gcr.io/cadvisor/cadvisor-amd64"
if [ "$DETECTED_REGION" = "CN" ]; then
  if docker inspect "$CADVISOR_IMG:$VERSION" > /dev/null 2>&1; then
    echo "$CADVISOR_IMG:$VERSION already available locally"
  else
    echo "Trying to pull cadvisor image from $PRC_GCR_IMAGE with $VERSION tag"
    if docker pull "$PRC_GCR_IMAGE:$VERSION"; then
      docker tag "$PRC_GCR_IMAGE:$VERSION" "$CADVISOR_IMG:$VERSION"
      echo "Image is pulled successfully from Huawei cloud mirror and re-tagged to the original one."
    else
      echo "Failed to pull the image from Huawei mirror"
      read -r -p "Enter known mirror for cadvisor image with full name and tag (example:, registry.cn/cadvisor:tag): " USER_IMAGE
      if docker pull "$USER_IMAGE"; then
        echo "User provided image: $USER_IMAGE"
        docker tag "$USER_IMAGE" "$CADVISOR_IMG:$VERSION"
        echo "Pull from the new mirror and tagging successful"
      else
        echo "Failed to pull the image from the provided mirror"
        exit 1
      fi
    fi
  fi
else
  echo "Regular profile setup continues"
fi

# Stop any existing container with the same name
echo "Stopping any existing cadvisor docker container instance..."
docker stop "$CONTAINER_NAME" 2>/dev/null || true
docker rm "$CONTAINER_NAME" 2>/dev/null || true
echo \"***Running cAdvisor in a Docker Container***\"

echo "$SUDO_PASSWORD" | sudo -S docker run \
  --volume=/:/rootfs:ro \
  --volume=/var/run:/var/run:ro \
  --volume=/sys:/sys:ro \
  --volume=/var/lib/docker/:/var/lib/docker:ro \
  --volume=/dev/disk/:/dev/disk:ro \
  --publish=8080:8080 \
  --detach=true \
  --name=cadvisor \
  --privileged \
  --device=/dev/kmsg \
  --restart=unless-stopped \
  gcr.io/cadvisor/cadvisor:$VERSION

# Check the cadvisor Docker Container
echo \"***Check the cadvisor Docker Container***\"
docker ps | grep "$CONTAINER_NAME"

sed -i 's/cadvisor_build_status=0/cadvisor_build_status=1/g' "$STATUS_DIR_FILE_PATH"

elapsedseconds=$SECONDS
echo "cadvisor build time = $((elapsedseconds))" >> "$PACKAGE_BUILD_TIME_FILE"

fi

}

Validation_Report_Generation () {

echo "Installing Validation_Report_Generation"

}

HW_BOM () {

echo "Installing HW_BOM"

}

Secure_Boot () {

echo "Installing Secure_Boot"

}

execute_restore_openssl_conf () {

echo "Installing execute_restore_openssl_conf"
if [ "$enable_restore_openssl_conf_build_status" -ne 1 ]; then
SECONDS=0
restore_openssl_conf
sed -i 's/enable_restore_openssl_conf_build_status=0/enable_restore_openssl_conf_build_status=1/g' "$STATUS_DIR_FILE_PATH"

elapsedseconds=$SECONDS
echo "enable_restore_openssl_conf build time = $((elapsedseconds))" >> "$PACKAGE_BUILD_TIME_FILE"

fi

}

reboot_continue_installation () {

echo "Installing reboot_continue_installation"
if [ "$reboot_continue_build_status" -ne 1 ]; then
SECONDS=0
echo "***********************"
echo "         Reboot        "
echo "***********************"
echo -e "\nThe EEF module installation has been completed successfully."
echo -e "A system reboot is required to ensure that all modifications take effect.\n"
# Interactive prompt for user choice
read -r -p "Do you want to reboot the system now? (y/n): " choice
if [[ "$choice" == "y" || "$choice" == "Y" ]]; then
  echo -e "\n*** Initiating system reboot... ***"
  echo "$SUDO_PASSWORD" | sudo -S reboot
else
  echo -e "\nReboot has been canceled. Continuing with the module installation..."
  echo -e "\nNote: A system reboot is required after the installation is complete to apply the changes.\n"
fi
# Set the sudo password variable to null at the end
SUDO_PASSWORD=""

sed -i 's/reboot_continue_build_status=0/reboot_continue_build_status=1/g' "$STATUS_DIR_FILE_PATH"

elapsedseconds=$SECONDS
echo "reboot_continue build time = $((elapsedseconds))" >> "$PACKAGE_BUILD_TIME_FILE"

fi

}


Proxy_Settings
Install_Disable_Popup
Install_Build_Dependencies
Install_pigz
Install_jq
Install_Docker
Configure_Docker_Group
Install_Kernel
Install_Media_Tools
Install_AI_Tools
Install_TPM
Observability_Stack_Baremetal_OS
Validation_Report_Generation
HW_BOM
Secure_Boot
execute_restore_openssl_conf
reboot_continue_installation
