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

<!--hide_directive
```{include} bios_generic.md
```
hide_directive-->

## Set locale

<!--hide_directive
```{include} Ubuntu-Set-Locale.md
```
hide_directive-->

## Set Date and Time

Use the `date` command to display the current date and time. If the Linux OS time and date is incorrect, set it to current date and time:

```bash
date
sudo date -s "2025-03-30 12:00"
```

## Setup Sources

<!--hide_directive
:::{include} Apt-Repositories.md
:heading-offset: 1
:::
hide_directive-->
