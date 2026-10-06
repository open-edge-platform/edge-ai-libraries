#!/bin/bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Enable SR-IOV with 7 virtual functions
echo 7 > /sys/bus/pci/devices/0000:00:02.0/sriov_numvfs

# Wait a moment for VFs to be created
sleep 2

# Base path for the device
device="0000:00:02.0"
gt_base="/sys/kernel/debug/dri/$device"

echo "Configuring device: $device"

if [ -d "$gt_base" ]; then
    # Loop through all gt* directories
    for gt_dir in "$gt_base"/gt*; do
        if [ -d "$gt_dir" ]; then
            gt_name=$(basename "$gt_dir")
            echo "  Processing $gt_name"
            
            # Loop through all VFs (vf1 to vf7)
            for vf_num in {1..7}; do
                vf_path="$gt_dir/vf$vf_num"
                if [ -d "$vf_path" ]; then
                    echo "    Configuring vf$vf_num"
                    
                    # Set exec_quantum_ms
                    if [ -f "$vf_path/exec_quantum_ms" ]; then
                        echo 128 | sudo tee "$vf_path/exec_quantum_ms" > /dev/null
                        actual_quantum=$(cat "$vf_path/exec_quantum_ms" 2>/dev/null)
                        echo "      Set $vf_path/exec_quantum_ms to 128 (actual: $actual_quantum)"
                    fi
                    
                    # Set preempt_timeout_us
                    if [ -f "$vf_path/preempt_timeout_us" ]; then
                        echo 256000 | sudo tee "$vf_path/preempt_timeout_us" > /dev/null
                        actual_timeout=$(cat "$vf_path/preempt_timeout_us" 2>/dev/null)
                        echo "      Set $vf_path/preempt_timeout_us to 256000 (actual: $actual_timeout)"
                    fi
                else
                    echo "    Warning: vf$vf_num directory not found in $gt_name"
                fi
            done
        fi
    done
else
    echo "  Error: Debug directory not found for $device"
    exit 1
fi

echo ""
echo "Configuration complete!"
echo ""
echo "=== Validation Summary ==="

# Verify SR-IOV configuration
numvfs=$(cat /sys/bus/pci/devices/0000:00:02.0/sriov_numvfs 2>/dev/null)
echo "SR-IOV VFs enabled: $numvfs"

echo ""
echo "Configured parameters:"
# Loop through gt directories again for validation
for gt_dir in "$gt_base"/gt*; do
    if [ -d "$gt_dir" ]; then
        gt_name=$(basename "$gt_dir")
        echo ""
        echo "GT: $gt_name"
        
        # Loop through all VFs
        for vf_num in {1..7}; do
            vf_path="$gt_dir/vf$vf_num"
            if [ -d "$vf_path" ]; then
                quantum=$(cat "$vf_path/exec_quantum_ms" 2>/dev/null)
                timeout=$(cat "$vf_path/preempt_timeout_us" 2>/dev/null)
                echo "  $vf_path:"
                echo "    exec_quantum_ms=$quantum"
                echo "    preempt_timeout_us=$timeout"
            fi
        done
    fi
done

echo ""
echo "Configuration complete!"
#!/bin/bash

# Enable SR-IOV with 7 virtual functions
echo 7 > /sys/bus/pci/devices/0000:00:02.0/sriov_numvfs

# Wait a moment for VFs to be created
sleep 2

# Base path for the device
device="0000:00:02.0"
gt_base="/sys/kernel/debug/dri/$device"

echo "Configuring device: $device"

if [ -d "$gt_base" ]; then
    # Loop through all gt* directories
    for gt_dir in "$gt_base"/gt*; do
        if [ -d "$gt_dir" ]; then
            gt_name=$(basename "$gt_dir")
            echo "  Processing $gt_name"
            
            # Loop through all VFs (vf1 to vf7)
            for vf_num in {1..7}; do
                vf_path="$gt_dir/vf$vf_num"
                if [ -d "$vf_path" ]; then
                    echo "    Configuring vf$vf_num"
                    
                    # Set exec_quantum_ms
                    if [ -f "$vf_path/exec_quantum_ms" ]; then
                        echo 128 | sudo tee "$vf_path/exec_quantum_ms" > /dev/null
                        actual_quantum=$(cat "$vf_path/exec_quantum_ms" 2>/dev/null)
                        echo "      Set $vf_path/exec_quantum_ms to 128 (actual: $actual_quantum)"
                    fi
                    
                    # Set preempt_timeout_us
                    if [ -f "$vf_path/preempt_timeout_us" ]; then
                        echo 256000 | sudo tee "$vf_path/preempt_timeout_us" > /dev/null
                        actual_timeout=$(cat "$vf_path/preempt_timeout_us" 2>/dev/null)
                        echo "      Set $vf_path/preempt_timeout_us to 256000 (actual: $actual_timeout)"
                    fi
                else
                    echo "    Warning: vf$vf_num directory not found in $gt_name"
                fi
            done
        fi
    done
else
    echo "  Error: Debug directory not found for $device"
    exit 1
fi

echo ""
echo "Configuration complete!"
echo ""
echo "=== Validation Summary ==="

# Verify SR-IOV configuration
numvfs=$(cat /sys/bus/pci/devices/0000:00:02.0/sriov_numvfs 2>/dev/null)
echo "SR-IOV VFs enabled: $numvfs"

echo ""
echo "Configured parameters:"
# Loop through gt directories again for validation
for gt_dir in "$gt_base"/gt*; do
    if [ -d "$gt_dir" ]; then
        gt_name=$(basename "$gt_dir")
        echo ""
        echo "GT: $gt_name"
        
        # Loop through all VFs
        for vf_num in {1..7}; do
            vf_path="$gt_dir/vf$vf_num"
            if [ -d "$vf_path" ]; then
                quantum=$(cat "$vf_path/exec_quantum_ms" 2>/dev/null)
                timeout=$(cat "$vf_path/preempt_timeout_us" 2>/dev/null)
                echo "  $vf_path:"
                echo "    exec_quantum_ms=$quantum"
                echo "    preempt_timeout_us=$timeout"
            fi
        done
    fi
done

echo ""
echo "Configuration complete!"

