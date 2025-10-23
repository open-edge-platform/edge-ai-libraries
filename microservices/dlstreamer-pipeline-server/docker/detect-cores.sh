#!/bin/bash

# Detect core types with multi-tier redundancy:
# Confirm Multi-Socker (Xeon, assume all P-Cores across all sockets)
# Use CPUID to determine Intel Core vs Intel Atom (Guarantee P-Cores)
# Opportunistically check sysfs for core/atom/lowpower assignments (Guarantee P-Cores)
# Fallback to L1d cache size drop detection and topology (Guarantee LP-E Cores)
# Fallback SMT pair detection in topology (Guarantee P-Cores)

# set VERBOSE=1 to enable debug output
debug_print() {
    if [[ "$VERBOSE" == "1" ]]; then
        echo "$@"
    fi
}

# Global variables for core-types
all_core_ids=()
remaining_core_ids=()
p_cores=()
e_cores=()
lpe_cores=()
cpu_data=()

# Initialize total core list from lscpu data
initialize_core_tracking() {
    local lscpu_output
    cpu_data=()
    all_core_ids=()
    remaining_core_ids=()

    lscpu_output=$(lscpu --all --extended 2>/dev/null)
    if [[ $? -ne 0 || -z "$lscpu_output" ]]; then
        return 1
    fi
    
    # Parse CPU data and build core ID list
    while IFS= read -r line; do
        if [[ "$line" =~ ^[[:space:]]*[0-9]+ ]]; then
            local cpu_num=$(echo "$line" | awk '{print $1}')
            local cache_topo=$(echo "$line" | awk '{print $5}')
            
            if [[ "$cpu_num" =~ ^[0-9]+$ && -n "$cache_topo" ]]; then
                cpu_data+=("$cpu_num:$cache_topo")
                all_core_ids+=("$cpu_num")
                remaining_core_ids+=("$cpu_num")
            fi
        fi
    done <<< "$lscpu_output"
    
    debug_print "DEBUG: Total cores found: ${#all_core_ids[@]} (${all_core_ids[*]})"
    return 0
}

# Helper function to remove cores from remaining list
remove_from_remaining() {
    local cores_to_remove=("$@")
    local new_remaining=()
    
    for remaining_core in "${remaining_core_ids[@]}"; do
        local should_keep=true
        for remove_core in "${cores_to_remove[@]}"; do
            if [[ "$remaining_core" == "$remove_core" ]]; then
                should_keep=false
                break
            fi
        done
        if [[ "$should_keep" == true ]]; then
            new_remaining+=("$remaining_core")
        fi
    done
    
    remaining_core_ids=("${new_remaining[@]}")
}

# Check if system is multi-socket (Xeon))
check_xeon() {
    local socket_count=$(grep "physical id" /proc/cpuinfo 2>/dev/null | sort | uniq | wc -l)
    
    if [[ $socket_count -gt 1 ]]; then
        debug_print "DEBUG: Multi-socket Xeon detected ($socket_count sockets) - assigning all cores as P-cores"
        p_cores=("${remaining_core_ids[@]}")
        remaining_core_ids=()
        return 0
    fi
    
    debug_print "DEBUG: Single socket system detected, continuing with hybrid detection"
    return 1
}

# Use taskset+cpuid to detect core types
check_cpuid() {
    # Check if cpuid is available
    if ! command -v cpuid >/dev/null 2>&1; then
        debug_print "DEBUG: cpuid not available, skipping cpuid detection"
        return 1
    fi
    
    debug_print "DEBUG: Starting cpuid detection on ${#remaining_core_ids[@]} remaining cores"
    
    local cpuid_assigned=()
    local cpuid_failed=()
    
    # Process remaining cores with cpuid
    for core_id in "${remaining_core_ids[@]}"; do
        local cache_pattern=""
        for entry in "${cpu_data[@]}"; do
            if [[ "${entry%%:*}" == "$core_id" ]]; then
                cache_pattern="${entry#*:}"
                break
            fi
        done
        
        local colon_count=$(echo "$cache_pattern" | tr -cd ':' | wc -c)
        
        # Check for LPE cores first
        if [[ $colon_count -eq 2 ]]; then
            lpe_cores+=("$core_id")
            cpuid_assigned+=("$core_id")
            continue
        fi
        
        # Use cpuid for non-LPE cores
        local core_type=$(taskset -c "$core_id" cpuid -1 -l 0x1a 2>/dev/null | grep "core type" | cut -d'=' -f2 | sed 's/^[[:space:]]*//')
        
        if [[ -n "$core_type" ]]; then
            if [[ "$core_type" == "Intel Core" ]]; then
                p_cores+=("$core_id")
                cpuid_assigned+=("$core_id")
            elif [[ "$core_type" == "Intel Atom" ]]; then
                e_cores+=("$core_id")
                cpuid_assigned+=("$core_id")
            else
                cpuid_failed+=("$core_id")
            fi
        else
            cpuid_failed+=("$core_id")
        fi
    done
    
    if [[ ${#cpuid_assigned[@]} -gt 0 ]]; then
        remove_from_remaining "${cpuid_assigned[@]}"
        debug_print "DEBUG: cpuid assigned ${#cpuid_assigned[@]} cores, failed on ${#cpuid_failed[@]} cores"
    else
        debug_print "DEBUG: cpuid failed on all cores"
    fi
    
    debug_print "DEBUG: Cores remaining: ${#remaining_core_ids[@]} (${remaining_core_ids[*]})"
    [[ ${#cpuid_assigned[@]} -gt 0 ]]
}

# Use L1d cache size drop detection
check_lscpu() {
    if [[ ${#remaining_core_ids[@]} -eq 0 ]]; then
        debug_print "DEBUG: No cores remaining for L1d cache detection"
        return 0
    fi
    
    debug_print "DEBUG: Starting L1d cache drop detection on ${#remaining_core_ids[@]} remaining cores"
    
    local remaining_entries=()
    for core_id in "${remaining_core_ids[@]}"; do
        for entry in "${cpu_data[@]}"; do
            if [[ "${entry%%:*}" == "$core_id" ]]; then
                remaining_entries+=("$entry")
                break
            fi
        done
    done
    
    # Check for two-colon LPE cache architecture
    local lscpu_assigned=()
    local non_lpe_entries=()
    
    for entry in "${remaining_entries[@]}"; do
        local core_id="${entry%%:*}"
        local cache_pattern="${entry#*:}"
        local colon_count=$(echo "$cache_pattern" | tr -cd ':' | wc -c)
        
        if [[ $colon_count -eq 2 ]]; then
            lpe_cores+=("$core_id")
            lscpu_assigned+=("$core_id")
        else
            non_lpe_entries+=("$entry")
        fi
    done
    
    # Process remaining non-LPE cores with L1d drop detection
    if [[ ${#non_lpe_entries[@]} -gt 0 ]]; then
        local prev_l1d=""
        local found_drop=false
        
        for entry in "${non_lpe_entries[@]}"; do
            local cache_pattern="${entry#*:}"
            local l1d=$(echo "$cache_pattern" | cut -d':' -f1)

            if [[ -n "$prev_l1d" && "$l1d" -lt "$prev_l1d" ]]; then
                found_drop=true
                break
            fi
            prev_l1d="$l1d"
        done
        
        if [[ "$found_drop" == true ]]; then
            debug_print "DEBUG: L1d cache drop detected, classifying cores"
            prev_l1d=""
            found_drop=false
            for entry in "${non_lpe_entries[@]}"; do
                local core_id="${entry%%:*}"
                local cache_pattern="${entry#*:}"
                local l1d=$(echo "$cache_pattern" | cut -d':' -f1)

                if [[ -n "$prev_l1d" && "$l1d" -lt "$prev_l1d" ]]; then
                    found_drop=true
                fi
                
                if [[ "$found_drop" == true ]]; then
                    e_cores+=("$core_id")
                else
                    p_cores+=("$core_id")
                fi
                lscpu_assigned+=("$core_id")
                prev_l1d="$l1d"
            done
        else
            debug_print "DEBUG: No L1d cache drop detected, leaving for SMT detection"
        fi
    fi

    if [[ ${#lscpu_assigned[@]} -gt 0 ]]; then
        remove_from_remaining "${lscpu_assigned[@]}"
        debug_print "DEBUG: L1d detection assigned ${#lscpu_assigned[@]} cores"
    else
        debug_print "DEBUG: L1d detection assigned no cores"
    fi
    
    debug_print "DEBUG: Cores remaining: ${#remaining_core_ids[@]} (${remaining_core_ids[*]})"
    
    [[ ${#lscpu_assigned[@]} -gt 0 ]]
}

# Use sysfss validation for guaranteed assignments if available
check_sysfs() {
    if [[ ${#remaining_core_ids[@]} -eq 0 ]]; then
        debug_print "DEBUG: No cores remaining for sysfs validation"
        return 0
    fi
    
    debug_print "DEBUG: Starting sysfs validation on ${#remaining_core_ids[@]} remaining cores"
    
    local sysfs_assigned=()
    local guaranteed_p_cores=()
    local guaranteed_lpe_cores=()
    local remaining_atom_cores=()

    local has_core_dir=false
    local has_atom_dir=false
    local has_lowpower_dir=false
    
    [[ -d "/sys/devices/cpu_core" ]] && has_core_dir=true
    [[ -d "/sys/devices/cpu_atom" ]] && has_atom_dir=true
    [[ -d "/sys/devices/cpu_lowpower" ]] && has_lowpower_dir=true
    
    debug_print "DEBUG: sysfs availability - core:$has_core_dir atom:$has_atom_dir lowpower:$has_lowpower_dir"
    if [[ "$has_core_dir" == false && "$has_atom_dir" == false && "$has_lowpower_dir" == false ]]; then
        debug_print "DEBUG: No sysfs core type directories found, skipping validation"
        return 1
    fi
    
    # Process each remaining core
    for core_id in "${remaining_core_ids[@]}"; do
        local assigned=false
        if [[ "$has_core_dir" == true ]]; then
            if [[ -f "/sys/devices/cpu_core/cpus" ]]; then
                local core_cpus=$(cat "/sys/devices/cpu_core/cpus" 2>/dev/null || echo "")
                if [[ -n "$core_cpus" ]]; then
                    local expanded_cores=$(echo "$core_cpus" | sed 's/,/ /g' | xargs -n1 | while read range; do
                        if [[ "$range" =~ ^([0-9]+)-([0-9]+)$ ]]; then
                            seq "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}"
                        else
                            echo "$range"
                        fi
                    done)
                    
                    if echo "$expanded_cores" | grep -q "^${core_id}$"; then
                        guaranteed_p_cores+=("$core_id")
                        sysfs_assigned+=("$core_id")
                        assigned=true
                    fi
                fi
            fi
        fi
        if [[ "$assigned" == false && "$has_lowpower_dir" == true ]]; then
            if [[ -f "/sys/devices/cpu_lowpower/cpus" ]]; then
                local lowpower_cpus=$(cat "/sys/devices/cpu_lowpower/cpus" 2>/dev/null || echo "")
                if [[ -n "$lowpower_cpus" ]]; then
                    local expanded_cores=$(echo "$lowpower_cpus" | sed 's/,/ /g' | xargs -n1 | while read range; do
                        if [[ "$range" =~ ^([0-9]+)-([0-9]+)$ ]]; then
                            seq "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}"
                        else
                            echo "$range"
                        fi
                    done)
                    
                    if echo "$expanded_cores" | grep -q "^${core_id}$"; then
                        guaranteed_lpe_cores+=("$core_id")
                        sysfs_assigned+=("$core_id")
                        assigned=true
                    fi
                fi
            fi
        fi
        if [[ "$assigned" == false && "$has_atom_dir" == true ]]; then
            if [[ -f "/sys/devices/cpu_atom/cpus" ]]; then
                local atom_cpus=$(cat "/sys/devices/cpu_atom/cpus" 2>/dev/null || echo "")
                if [[ -n "$atom_cpus" ]]; then
                    local expanded_cores=$(echo "$atom_cpus" | sed 's/,/ /g' | xargs -n1 | while read range; do
                        if [[ "$range" =~ ^([0-9]+)-([0-9]+)$ ]]; then
                            seq "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}"
                        else
                            echo "$range"
                        fi
                    done)
                    
                    if echo "$expanded_cores" | grep -q "^${core_id}$"; then
                        remaining_atom_cores+=("$core_id")
                    fi
                fi
            fi
        fi
    done
    if [[ ${#guaranteed_p_cores[@]} -gt 0 ]]; then
        p_cores+=("${guaranteed_p_cores[@]}")
        debug_print "DEBUG: sysfs assigned ${#guaranteed_p_cores[@]} guaranteed P-cores: ${guaranteed_p_cores[*]}"
    fi
    
    if [[ ${#guaranteed_lpe_cores[@]} -gt 0 ]]; then
        lpe_cores+=("${guaranteed_lpe_cores[@]}")
        debug_print "DEBUG: sysfs assigned ${#guaranteed_lpe_cores[@]} guaranteed LPE-cores: ${guaranteed_lpe_cores[*]}"
    fi
    
    # Filter E-Core vs LPE-Core
    if [[ ${#remaining_atom_cores[@]} -gt 0 ]]; then
        debug_print "DEBUG: Processing ${#remaining_atom_cores[@]} remaining atom cores for E vs LPE classification"
        local atom_entries=()
        for core_id in "${remaining_atom_cores[@]}"; do
            for entry in "${cpu_data[@]}"; do
                if [[ "${entry%%:*}" == "$core_id" ]]; then
                    atom_entries+=("$entry")
                    break
                fi
            done
        done
        
        for entry in "${atom_entries[@]}"; do
            local core_id="${entry%%:*}"
            local cache_pattern="${entry#*:}"
            local colon_count=$(echo "$cache_pattern" | tr -cd ':' | wc -c)
            
            if [[ $colon_count -eq 2 ]]; then
                lpe_cores+=("$core_id")
                debug_print "DEBUG: Classified atom core $core_id as LPE (cache pattern: $cache_pattern)"
            else
                e_cores+=("$core_id")
                debug_print "DEBUG: Classified atom core $core_id as E (cache pattern: $cache_pattern)"
            fi
            sysfs_assigned+=("$core_id")
        done
    fi
    
    if [[ ${#sysfs_assigned[@]} -gt 0 ]]; then
        remove_from_remaining "${sysfs_assigned[@]}"
        debug_print "DEBUG: sysfs validation assigned ${#sysfs_assigned[@]} total cores"
    else
        debug_print "DEBUG: sysfs validation assigned no cores"
    fi
    
    debug_print "DEBUG: Cores remaining: ${#remaining_core_ids[@]} (${remaining_core_ids[*]})"
    
    [[ ${#sysfs_assigned[@]} -gt 0 ]]
}
check_smt() {
    if [[ ${#remaining_core_ids[@]} -eq 0 ]]; then
        debug_print "DEBUG: No cores remaining for SMT detection"
        return 0
    fi
    
    debug_print "DEBUG: Starting SMT pair detection on ${#remaining_core_ids[@]} remaining cores"
    local remaining_entries=()
    for core_id in "${remaining_core_ids[@]}"; do
        for entry in "${cpu_data[@]}"; do
            if [[ "${entry%%:*}" == "$core_id" ]]; then
                remaining_entries+=("$entry")
                break
            fi
        done
    done
    
    local processed=()
    local has_smt_pairs=false
    local smt_assigned=()
    
    for entry in "${remaining_entries[@]}"; do
        local core_id="${entry%%:*}"
        local cache_pattern="${entry#*:}"
        
        local already_done=false
        for proc in "${processed[@]}"; do
            if [[ "$core_id" == "$proc" ]]; then
                already_done=true
                break
            fi
        done
        [[ "$already_done" == true ]] && continue
        
        local consecutive_cpu=$((core_id + 1))
        local found_smt=false
        
        # Look for SMT pair
        for other_entry in "${remaining_entries[@]}"; do
            local other_cpu="${other_entry%%:*}"
            local other_cache="${other_entry#*:}"
            
            if [[ "$other_cpu" == "$consecutive_cpu" && "$other_cache" == "$cache_pattern" ]]; then
                p_cores+=("$core_id" "$consecutive_cpu")
                processed+=("$core_id" "$consecutive_cpu")
                smt_assigned+=("$core_id" "$consecutive_cpu")
                found_smt=true
                has_smt_pairs=true
                break
            fi
        done
        
        if [[ "$found_smt" == false ]]; then
            if [[ "$has_smt_pairs" == true ]]; then
                e_cores+=("$core_id")
            else
                p_cores+=("$core_id")
            fi
            processed+=("$core_id")
            smt_assigned+=("$core_id")
        fi
    done
    
    if [[ ${#smt_assigned[@]} -gt 0 ]]; then
        remove_from_remaining "${smt_assigned[@]}"
        debug_print "DEBUG: SMT detection assigned ${#smt_assigned[@]} cores"
    fi
    
    debug_print "DEBUG: Cores remaining: ${#remaining_core_ids[@]} (${remaining_core_ids[*]})"
    
    return 0
}

# Main function
detect_cores() {
    
    # Create list of core IDs
    if ! initialize_core_tracking; then
        echo "ERROR: Failed to initialize core tracking"
        return 1
    fi
    
    if check_xeon; then
        debug_print "DEBUG: Xeon detection completed all assignments"
        return 0
    fi
    check_cpuid
    check_sysfs
    check_lscpu
    check_smt

    if [[ ${#remaining_core_ids[@]} -gt 0 ]]; then
        debug_print "DEBUG: Assigning ${#remaining_core_ids[@]} unclassified cores as P-cores by default"
        p_cores+=("${remaining_core_ids[@]}")
        remaining_core_ids=()
    fi    
    return 0
}

detect_cores "$1"
[ ${#p_cores[@]} -eq 0 ] || echo "p-cores:  ${p_cores[@]}"
[ ${#e_cores[@]} -eq 0 ] || echo "e-cores:  ${e_cores[@]}"
[ ${#lpe_cores[@]} -eq 0 ] || echo "lpe-cores:  ${lpe_cores[@]}"
