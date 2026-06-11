This section explains the procedure to configure the APT package manager to use the hosted ECI APT repository.

Make sure that you have the right [OS Setup](os_setup.md).

# Set up ECI APT Repository

1. Open a terminal prompt which will be used to execute the remaining steps.

2. Download the ECI APT key to the system keyring:

   ```bash
   sudo -E wget -O- https://eci.intel.com/repos/gpg-keys/GPG-PUB-KEY-INTEL-ECI.gpg | sudo tee /usr/share/keyrings/eci-archive-keyring.gpg > /dev/null
   ```

3. Add the signed entry to APT sources and configure the APT client to use the ECI APT repository:

   ```bash
   echo "deb [signed-by=/usr/share/keyrings/eci-archive-keyring.gpg] https://eci.intel.com/repos/$(source /etc/os-release && echo $VERSION_CODENAME) isar main" | sudo tee /etc/apt/sources.list.d/eci.list
   echo "deb-src [signed-by=/usr/share/keyrings/eci-archive-keyring.gpg] https://eci.intel.com/repos/$(source /etc/os-release && echo $VERSION_CODENAME) isar main" | sudo tee -a /etc/apt/sources.list.d/eci.list
   ```

   **Note**: The auto upgrade feature in Canonical® Ubuntu® will change the deployment environment over time. If you do not want to auto upgrade, execute the following commands to disable the feature:

   ```bash
   sudo sed -i "s/APT::Periodic::Update-Package-Lists \"1\"/APT::Periodic::Update-Package-Lists \"0\"/g" "/etc/apt/apt.conf.d/20auto-upgrades"
   sudo sed -i "s/APT::Periodic::Unattended-Upgrade \"1\"/APT::Unattended-Upgrade \"0\"/g" "/etc/apt/apt.conf.d/20auto-upgrades"
   ```

4. Configure the ECI APT repository to have higher priority over other repositories:

   ```bash
   sudo bash -c 'echo -e "Package: *\nPin: origin eci.intel.com\nPin-Priority: 1000" >> /etc/apt/preferences.d/isar'
   sudo bash -c 'echo -e "Package: libze-intel-gpu1,libze1,intel-opencl-icd,libze-dev,intel-ocloc\nPin: origin repositories.intel.com/gpu/ubuntu\nPin-Priority: 1000" >> /etc/apt/preferences.d/isar'
   ```
