.. _OS_Setup:

OS Setup
##########

To leverage all |top_name| features, the target system should meet the :ref:`recommended system requirements <Target_System>`. Also, The target system must have a compatible OS (`Ubuntu 22.04 Desktop`) so that you can install Deb packages from SDK. This section explains the procedure to install a compatible OS on the target system.

Do the following to prepare the target system:

#. Follow with `Ubuntu Installation Guide <https://ubuntu.com/tutorials/install-ubuntu-desktop>`_ to install Ubuntu 22.04 Desktop with  **64bits** variant on to the target system.

   .. attention::

      Please review `Canoncial Intellectual property rights policy <https://ubuntu.com/legal/intellectual-property-policy>`_ regarding |Ubuntu|. Note that any redistribution of modified versions of |Ubuntu| must be approved, certified or provided by Canonical if you are going to associate it with the Trademarks. Otherwise you must remove and replace the Trademarks and will need to recompile the source code to create your own binaries.

#. To achieve real-time determinism and utilize the available |Intel| silicon features, you need to configure certain BIOS settings. Reboot the target system and access the BIOS(press the :kbd:`delete` or :kbd:`F2` keys while booting to open the BIOS menu).

#. Select **Restore Defaults** or **Load Defaults**, and then select **Save Changes and Reset**. As the target system boots, access the BIOS again.

#. Modify the BIOS configuration as listed in the following table.

   **Note**: The available configurations depend on the platform, BIOS in use, or both. Modify as many configurations as possible.

   .. include:: bios-generic.rst

Set locale
-----------

.. include:: Ubuntu-Set-Locale.rst


Set Date and Time
------------------

Use the ``date`` command to display the current date and time. If it shows the Linux time and date is wrong, follow below command to set it to current date and time.

.. code-block:: bash

   $ date
   $ sudo date -s "2025-03-30 12:00"

Setup Sources
--------------

.. include:: Apt-Repositories.rst

