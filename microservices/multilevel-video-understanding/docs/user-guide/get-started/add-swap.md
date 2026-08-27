# Adding Swap Space

`Qwen3.5-35B-A3B` in FP8 with a 60k context window is memory-hungry on a shared-RAM host. On the on-device PTL profile, provide at least **32 GB of swap** so the weight load and KV cache can spill under peak pressure without the OOM killer stepping in. On an NVMe SSD (~3 GB/s) the model load is slower under swap, but it will not OOM.

## Step 1. Check current swap

```bash
swapon --show
```

If swap is not enabled, or the total is less than 32 GB, add a swap file as below.

## Step 2. Create a temporary swap file

```bash
# Create a 32 GB swap file
sudo fallocate -l 32G /swapfile_temp
sudo chmod 600 /swapfile_temp
sudo mkswap /swapfile_temp
sudo swapon /swapfile_temp

# Verify
swapon --show
# e.g. an existing /swap.img (8G) + /swapfile_temp (32G) = 40G total swap
```

## Step 3. Lower swappiness

Tell the kernel to use swap only when necessary, avoiding unnecessary paging:

```bash
sudo sysctl vm.swappiness=10
```

To persist this setting across reboots (idempotent):

```bash
echo 'vm.swappiness=10' | sudo tee /etc/sysctl.d/99-swap.conf
sudo sysctl -q vm.swappiness=10
```

## Keeping or removing the swap file

**Recommended: keep the swap file as a safety net.** Once it is active, restarting the services does not require setting up temporary swap again.

To make the swap file survive reboots, add it to `/etc/fstab`:

```bash
echo '/swapfile_temp none swap sw 0 0' | sudo tee -a /etc/fstab
```

To remove the temporary swap when you no longer need it:

```bash
# Remove the temporary swap
sudo swapoff /swapfile_temp
sudo rm /swapfile_temp

# Restore default swappiness
sudo sysctl vm.swappiness=60
```

> **Note:** If you added the swap file to `/etc/fstab`, also remove its line there before deleting the file, otherwise the next boot will fail to mount it.

## Supporting Resources

- [Get Started](../get-started.md)
- [System Requirements](./system-requirements.md)
