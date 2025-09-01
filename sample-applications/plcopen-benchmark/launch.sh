#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation

# Parse arguments
helpFunction()
{
   echo ""
   echo "Usage: $0 -n <nic_num> -a <cpu_affinity> -f <igpu_frequency>"
   echo "\t-n Network interface (has to be igb/igc), e.g. enp2s0"
   echo "\t-a CPU core affinity to run real-time thread, e.g. 1"
   echo "\t-f Set iGPU frequency, e.g. 200"
   exit 1 # Exit script after printing help
}

while getopts n:a:f:h flag
do
    case "${flag}" in
        n) nic=${OPTARG};;
        a) affinity=${OPTARG};;
        f) freq=${OPTARG};;
        h) helpFunction;;
        ?) helpFunction;;
    esac
done

if [ -z "${nic}" ]; then
  echo "Error: no NIC specified. Please use -n argument to specify NIC name, e.g. enp2s0."
  exit 1
fi

if [ -z "${affinity}" ]; then
  affinity=1
fi

if [ -z "${freq}" ]; then
  freq=200
fi

echo "Network interface: $nic"
echo "CPU core affinity: $affinity"
echo "iGPU frequency: $freq"

if [ "$EUID" -ne 0 ]; then 
  echo "Please run as root"
  exit 1
fi

# Install depends
echo "Install dependent Debian packages..."
apt update && apt install -y eci-softplc dmidecode msr-tools stress-ng
echo "Done install dependencies"

# Find MAC address
mac=$(ifconfig ${nic} | grep -o -E '([[:xdigit:]]{1,2}:){5}[[:xdigit:]]{1,2}')
if [ -z "${mac}" ]; then
  # Check if EtherCAT master has been started
  master_status=$(ethercat master | grep "attached")
  ret=$?
  if [ "$ret" -ne 0 || -z "$master_status" ]; then
    echo "Error: Not get MAC address of the network device."
    exit 1
  fi
fi
echo "MAC address: $mac"

# Find PCIE device slot
echo "Configure EtherCAT..."
slot=$(dmesg | grep ${nic} | grep -o -E '([[:xdigit:]]{1,4}:){2}[[:xdigit:]]{1,2}.[[:xdigit:]]{1,1}' | head -n 1)
if [ -z "${slot}" ]; then
  echo "Error: Not get network device slot name."
  exit 1
else
  echo "NIC device slot: $slot"
fi

# Find NIC kernel driver name
driver=$(dmesg | grep ${nic} | grep -o -E 'ig[b,c]' | head -n 1)
if [ -z "${driver}" ]; then
  echo "Error: Not get network device kernel driver name."
  exit 1
else
  echo "NIC device kernel driver: $driver"
fi

# Configure EtherCAT
ethercat_config_script_path="/etc/sysconfig/ethercat"
if [ -e ${ethercat_config_script_path} ]; then
  echo "Configure the EtherCAT MAC address..."
  sed -i "s/MASTER0_DEVICE=\".*\"/MASTER0_DEVICE=\"$mac\"/" /etc/sysconfig/ethercat

  echo "Configure the EtherCAT device module..."
  sed -i "s/DEVICE_MODULES=\".*\"/DEVICE_MODULES=\"$driver\"/" /etc/sysconfig/ethercat

  echo "Configure the EtherCAT device slot..."
  sed -i "s/REBIND_NICS=\".*\"/REBIND_NICS=\"$slot\"/" /etc/sysconfig/ethercat
else
  echo "Error: cannot find the file /etc/sysconfig/ethercat."
  exit 1
fi
echo "Done configure EtherCAT"

# Real-time tuning
echo "Make real-time configurations"
# Move all IRQs to core 0.
for i in `cat /proc/interrupts | grep '^ *[0-9]*[0-9]:' | awk {'print $1'} | sed 's/:$//' `;
do
   echo setting $i to affine for core zero
   echo 1 > /proc/irq/$i/smp_affinity
done

# Disable kernel machine check interrupt
#echo 0 > /sys/devices/system/machinecheck/machinecheck0/check_interval

# Disable rc6
# echo 0 > /sys/class/drm/card0/gt_rc6_enable

echo -1 > /proc/sys/kernel/sched_rt_runtime_us

#Move all rcu tasks to core 0.
for i in `pgrep rcu`; do taskset -pc 0 $i; done
 
#Change realtime attribute of all rcu tasks to SCHED_OTHER and priority 0
for i in `pgrep rcu`; do chrt -v -o -p 0 $i; done
 
#Change realtime attribute of all tasks on core 1 to SCHED_OTHER and priority 0
for i in `pgrep /1`; do chrt -v -o -p 0 $i; done
 
#Change realtime attribute of all tasks to SCHED_OTHER and priority 0
for i in `ps -A -o pid`; do chrt -v -o -p 0 $i; done

# Set iGPU frequency
echo "Set iGPU frequency as $freq MHz"
echo $freq > /sys/class/drm/card0/gt_max_freq_mhz
echo $freq > /sys/class/drm/card0/gt_min_freq_mhz

# Stop timers
systemctl stop *timer

# Disabling timer migration
echo 0 > /proc/sys/kernel/timer_migration
echo "Done real-time configurations"

# Setup PMUs to capture cache miss
echo "Setting up cache miss PMUs..."

# Setting up User Mode access to PMU
echo "Setting up User Mode access to PMU..."
echo 2 > /sys/bus/event_source/devices/cpu/rdpmc

# Setting up PMU events for CPU Core #1, running RT workload
echo "Setting up PMU evnets..."
# MEM_LOAD_RETIRED.L2_HIT
wrmsr -p 1 0x186 0x4302d1
# MEM_LOAD_RETIRED.L2_MISS
wrmsr -p 1 0x187 0x4310d1
# MEM_LOAD_RETIRED.L3_HIT
wrmsr -p 1 0x188 0x4304d1
# MEM_LOAD_RETIRED.L3_MISS
wrmsr -p 1 0x189 0x4320d1

echo "Done setting cache miss PMUs"

# Check EtherCAT master status
echo "Check EtherCAT master status..."
master_status=$(ethercat master | grep "attached")
ret=$?
if [ "$ret" -ne 0 ]; then
  echo "EtherCAT master is not started yet"

  # Re-start EtherCAT master stack
  /etc/init.d/ethercat start
  ret=$?
  if [ "$ret" -ne 0 ]; then
    echo "Failed to start EtherCAT master stack"
    exit 1
  else
    # Check master status again
    master_status=$(ethercat master | grep "attached")
    if [ -z "$master_status" ]; then
      echo "Ethernet divice is not successfully bounded to EtherCAT master stack"
      exit 1
    fi
  fi
else
  if [ -z "$master_status" ]; then
    echo "Ethernet divice is not successfully bounded to EtherCAT master stack"
    exit 1
  fi
fi
echo "Done check EtherCAT master status"

# Check EtherCAT slave status
echo "Check EtherCAT slave status..."
sleep 8
slave_num=$(ethercat slaves | wc -l)
if [ "$slave_num" -ne 6 ]; then
  echo "Failed to get slave status"
  exit 1
fi
echo "Done check EtherCAT slave status"

# Launch benchmark program
echo "Launch the benchmark program..."
benchmark_path="/opt/plcopen/plcopen_benchmark"
if [ ! -e "$benchmark_path" ]; then
  echo "PLCopen benchmark program doesn't exist"
  exit 1
fi

os_type=$(uname -a)
# Preempt RT
if [[ -n $(echo $os_type | grep "intel-ese-standard-lts-rt") ]]; then
  echo "Running on Preempt RT system"
  /opt/plcopen/plcopen_benchmark -n /opt/plcopen/inovance_six_1ms.xml -i 1000 -a $affinity -m 6 -t 259200 -l -o -r -c
fi

# Xenomai
if [[ -n $(echo $os_type | grep "intel-ese-standard-lts-dovetail") ]]; then
  echo "Running on Xenomai system"
  echo 0 > /proc/xenomai/clock/coreclk
  /opt/plcopen/plcopen_benchmark -n /opt/plcopen/inovance_six_1ms.xml -i 1000 -a $affinity -m 6 -t 86400 -l -o -r -c
fi