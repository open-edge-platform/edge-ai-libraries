
### Introduction

This directory contains common functions for coding OEP installer components. 

### Linux OS Common Functions

| Function Name |  Description |
|:--------------|:-------------|
|[`ensure_disk_size`](linux/ensure_disk_size)|Check disk size and fail if free disk size is less than specified. The unit size is `MB`. |
|[`ensure_fetch`](linux/ensure_fetch)|Robustly fetch an URL and save to a file or to `stdout`.|
|[`ensure_git`](linux/ensure-git)|Git clone or export to a directory. Support full git clone or sparse clone.|
|[`ensure_group_add`](linux/ensure_group_add)|Robustly create specified groups and add the current user to the groups.|
|[`ensure_hf_token`](linux/ensure_hf_token)|Check if specified models are gated. If so, search a list of know locations for `HF_TOKEN` and export if as environment variable.|
|[`ensure_ip`](linux/ensure_ip)|Return the current host IP address.|
|[`ensure_ports_open`](linux/ensure_ports_open)|Check network port status. If any of the ports is not open (listenable), try terminating the listening process.|
|[`ensure_project_path`](linux/ensure_project_path)|Return the component workspace path.|
|[`ensure_prop`](linux/ensure_prop)|Set, get, or remove component specific property key value pairs, used for guarding multiple installations or for inter-component communication.|
|[`ensure_ram_size`](linux/ensure_ram_size)|Check RAM (and SWAP) size and fail if the total RAM (/SWAP) size is less than specified. The unit size is `MiB`. |
|[`ensure_rm`](linux/ensure_rm)|Robustly remove files or directories.|
|[`ensure_sbom_format`](linux/ensure_sbom)|Format SBOM elements.|
|[`ensure_select_device`](linux/ensure_select_device)|Parse command line for device selection: `--gpu`, `--npu`, or `--cpu`. |
|[`ensure_skills`](linux/ensure_skills)|Add/remove skill files.|
|[`ensure_sudo`](linux/ensure_sudo)|Robustly invoke `sudo`. The proxy settings of the current user are passed along with the sudo command.|
|[`ensure_tmpdir`](linux/ensure_tmpdir)|Robustly create and destroy a temporary directory.|
|[`ensure_trap`](linux/ensure_trap)|Set/reset trap commands. Support nested trap.|

### Debian Functions

| Function Name |  Description |
|:--------------|:-------------|
|[`ensure_apt`](debian/ensure_apt)|Invoke `apt` with additional checks, for example, ensuring `update` execute only once and removing non-exist components from `remove|autoremove|purge|autopurge`. |
|[`ensure_apt_is_installed`](debian/ensure_apt)|Check if a list of `apt` packages is installed.|
|[`ensure_apt_allow_downgrades`](debian/ensure_apt)|Check if the degraded components of an installation command is within an expected list.|
|[`ensure_apt_key`](debian/ensure_apt_key)|Download and add a trusted key to the apt key ring.|
|[`ensure_apt_install_package`](debian/ensure_apt_package)<br>[`ensure_apt_remove_package`](debian/ensure_apt_package)|Glue functions for installing/removing apt packages.|
|[`ensure_apt_preference`](debian/ensure_apt_preference)|Create an apt preference file.|
|[`ensure_apt_source`](debian/ensure_apt_source)<br>[`ensure_apt_source_remove`](debian/ensure_apt_source)|Create/remove an apt source file.|

### Fedora Functions

| Function Name |  Description |
|:--------------|:-------------|
|[`ensure_dnf`](fedora/ensure_dnf)|Invoke `dnf` with additional checks.|
|[`ensure_dnf_is_installed`](fedora/ensure_dnf)|Check if a list of `dnf` packages is installed.|
|[`ensure_dnf_enable_epel`](fedora/ensure_dnf)|Enable the `epel` repository.|
|[`ensure_dnf_install_package`](fedora/ensure_dnf_package)<br>[`ensure_dnf_remove_package`](fedora/ensure_dnf_package)|Glue functions for installing/removing dnf packages.|







