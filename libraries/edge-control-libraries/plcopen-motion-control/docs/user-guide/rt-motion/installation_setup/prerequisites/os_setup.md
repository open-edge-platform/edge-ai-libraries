# OS Setup

To leverage all PLCopen Motion Control features, the target system should meet the [recommended system requirements](./system_requirement.md). Also, the target system must have a compatible OS (`Ubuntu 22.04 Desktop`) so that you can install Deb packages from SDK. This section explains the procedure to install a compatible OS on the target system.

Do the following to prepare the target system:

1. Follow the [Ubuntu Installation Guide](https://ubuntu.com/tutorials/install-ubuntu-desktop) to install Ubuntu 22.04 Desktop with the **64bits** variant on to the target system.

   > **Attention:**
   > Please review [Canonical Intellectual property rights policy](https://ubuntu.com/legal/intellectual-property-policy) regarding Canonical® Ubuntu®. Note that any redistribution of modified versions of Canonical® Ubuntu® must be approved, certified or provided by Canonical if you are going to associate it with the Trademarks. Otherwise you must remove and replace the Trademarks and will need to recompile the source code to create your own binaries.

2. To achieve real-time determinism and utilize the available Intel® silicon features, you need to configure certain BIOS settings. Reboot the target system and access the BIOS (press the `Delete` or `F2` keys while booting to open the BIOS menu).

3. Select **Restore Defaults** or **Load Defaults**, and then select **Save Changes and Reset**. As the target system boots, access the BIOS again.

4. Modify the BIOS configuration as listed in the following table.

   **Note**: The available configurations depend on the platform, BIOS in use, or both. Modify as many configurations as possible.

   <!--hide_directive ::::{tab-set} hide_directive-->
   <!--hide_directive :::{tab-item} hide_directive--> **Real-time Optimization**

   | Setting Name | Option | Setting Menu |
   | --- | --- | --- |
   | Hyper-Threading | Disabled | Intel Advanced Menu ⟶ CPU Configuration |
   | Intel (VMX) Virtualization | Enabled | Intel Advanced Menu ⟶ CPU Configuration |
   | X2APIC | Enabled | Intel Advanced Menu ⟶ CPU Configuration |
   | Active SOC-North Efficient-cores | 0 | Intel Advanced Menu ⟶ CPU Configuration |
   | Intel(R) SpeedStep | Enabled | Intel Advanced Menu ⟶ Power & Performance ⟶ CPU - Power Management Control |
   | Intel(R) Shift Technology | Enabled | Intel Advanced Menu ⟶ Power & Performance ⟶ CPU - Power Management Control |
   | Intel(R) Turbo Mode | Enabled | Intel Advanced Menu ⟶ Power & Performance ⟶ CPU - Power Management Control |
   | C States | Enabled | Intel Advanced Menu ⟶ Power & Performance ⟶ CPU - Power Management Control |
   | RC6 (Render Standby) | Disabled | Intel Advanced Menu ⟶ Power & Performance ⟶ GT - Power Management Control |
   | MC6 (Media Standby) | Enabled | Intel Advanced Menu ⟶ Power & Performance ⟶ GT - Power Management Control |
   | Disable Turbo GT frequency | Disabled | Intel Advanced Menu ⟶ Power & Performance ⟶ GT - Power Management Control |
   | Maximum GT frequency | Default Max Frequency | Intel Advanced Menu ⟶ Power & Performance ⟶ GT - Power Management Control |
   | Page Close Idle Timeout | Disabled | Intel Advanced Menu ⟶ Memory Configuration |
   | Power Down Mode | Disabled | Intel Advanced Menu ⟶ Memory Configuration |
   | SA GV | Disabled | Intel Advanced Menu ⟶ Memory Configuration |
   | VT-d | Enabled | Intel Advanced Menu ⟶ System Agent (SA) Configuration |
   | ACPI S3 Support | Disabled | Intel Advanced Menu ⟶ ACPI Settings |
   | Low Power S0 Idle Capability | Disabled | Intel Advanced Menu ⟶ ACPI Settings |
   | Native ASPM | Disabled | Intel Advanced Menu ⟶ ACPI Settings |
   | Legacy IO Low Latency | Enabled | Intel Advanced Menu ⟶ PCH-IO Configuration |

   <!--hide_directive ::: hide_directive-->
   <!--hide_directive :::{tab-item} hide_directive--> **Generic (non-real-time)**

   | Setting Name | Option | Setting Menu |
   | --- | --- | --- |
   | Hyper-Threading | Enabled | Intel Advanced Menu ⟶ CPU Configuration |
   | Intel (VMX) Virtualization | Enabled | Intel Advanced Menu ⟶ CPU Configuration |
   | X2APIC | Enabled | Intel Advanced Menu ⟶ CPU Configuration |
   | Active SOC-North Efficient-cores | All | Intel Advanced Menu ⟶ CPU Configuration |
   | Intel(R) SpeedStep | Enabled | Intel Advanced Menu ⟶ Power & Performance ⟶ CPU - Power Management Control |
   | Intel(R) Shift Technology | Enabled | Intel Advanced Menu ⟶ Power & Performance ⟶ CPU - Power Management Control |
   | Intel(R) Turbo Mode | Enabled | Intel Advanced Menu ⟶ Power & Performance ⟶ CPU - Power Management Control |
   | C States | Enabled | Intel Advanced Menu ⟶ Power & Performance ⟶ CPU - Power Management Control |
   | RC6 (Render Standby) | Enabled | Intel Advanced Menu ⟶ Power & Performance ⟶ GT - Power Management Control |
   | MC6 (Media Standby) | Enabled | Intel Advanced Menu ⟶ Power & Performance ⟶ GT - Power Management Control |
   | Disable Turbo GT frequency | Disabled | Intel Advanced Menu ⟶ Power & Performance ⟶ GT - Power Management Control |
   | Maximum GT frequency | Default Max Frequency | Intel Advanced Menu ⟶ Power & Performance ⟶ GT - Power Management Control |
   | Page Close Idle Timeout | Enabled | Intel Advanced Menu ⟶ Memory Configuration |
   | Power Down Mode | Auto | Intel Advanced Menu ⟶ Memory Configuration |
   | SA GV | Enabled | Intel Advanced Menu ⟶ Memory Configuration |
   | VT-d | Enabled | Intel Advanced Menu ⟶ System Agent (SA) Configuration |
   | ACPI S3 Support | Enabled | Intel Advanced Menu ⟶ ACPI Settings |
   | Low Power S0 Idle Capability | Disabled | Intel Advanced Menu ⟶ ACPI Settings |
   | Native ASPM | Auto | Intel Advanced Menu ⟶ ACPI Settings |
   | Legacy IO Low Latency | Disabled | Intel Advanced Menu ⟶ PCH-IO Configuration |

   <!--hide_directive
   :::
   ::::
   hide_directive-->

## Set locale

Make sure you have a locale which supports `UTF-8`.
If you are in a minimal environment (such as a Docker container), the locale may be something minimal like `POSIX`.
We test with the following settings. However, it should be fine if you are using a different UTF-8 supported locale.

```bash
locale  # check for UTF-8

sudo apt update && sudo apt install locales
sudo locale-gen en_US en_US.UTF-8
sudo update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
export LANG=en_US.UTF-8

locale  # verify settings
```

## Set Date and Time

Use the `date` command to display the current date and time. If the Linux OS time and date is incorrect, set it to current date and time:

```bash
date
sudo date -s "2025-03-30 12:00"
```

## Set up ECI APT Repository

This section explains the procedure to configure the APT package manager to use the hosted ECI APT repository.

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
