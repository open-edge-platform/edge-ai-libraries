#!/usr/bin/env bash
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

set -Eeuo pipefail

NATIVE_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
CONFIG_DIR=/etc/metrics-manager
EXAMPLES_DIR=/usr/share/doc/metrics-manager/examples
OPTIONS=(RAPL POWERSTAT_EXTRA TURBOSTAT TEMPERATURE INTERRUPTS NETWORK NETWORK_VIRTUAL STORAGE)
RUNTIME_OPTIONS=(TURBOSTAT_INTERVAL TURBOSTAT_BIN METRICS_MANAGER_HOSTNAME)
declare -A settings destinations examples runtime

fail() {
    printf 'configure-metrics.sh: %s\n' "$*" >&2
    exit 1
}

run() {
    if (( EUID == 0 )); then
        "$@"
    else
        sudo -- "$@"
    fi
}

exists() {
    [[ -e "$1" || -L "$1" ]]
}

read_options() {
    local file=$1 line key value number=0
    [[ -r "$file" ]] || fail "Cannot read options file: $file"
    local -A seen=()
    runtime=()
    for key in "${OPTIONS[@]}"; do
        settings[$key]=auto
    done
    while IFS= read -r line || [[ -n "$line" ]]; do
        number=$((number + 1))
        line=${line%$'\r'}
        [[ "$line" =~ ^[[:space:]]*(#.*)?$ ]] && continue
        if [[ ! "$line" =~ ^[[:space:]]*([A-Z_]+)[[:space:]]*=[[:space:]]*([^#]*)(#.*)?$ ]]; then
            fail "$file:$number: Expected KEY=value"
        fi
        key=${BASH_REMATCH[1]}
        value=${BASH_REMATCH[2]}
        value="${value%"${value##*[![:space:]]}"}"
        [[ ! -v "seen[$key]" ]] || fail "$file:$number: Duplicate option $key"
        seen[$key]=1
        case "$key" in
            ENABLE_*)
                [[ -v "settings[${key#ENABLE_}]" ]] || fail "$file:$number: Unknown option $key"
                [[ "$value" =~ ^(true|false|auto)$ ]] ||
                    fail "$file:$number: Expected ENABLE_OPTION=true|false|auto"
                settings[${key#ENABLE_}]=$value
                ;;
            TURBOSTAT_INTERVAL|TURBOSTAT_BIN|METRICS_MANAGER_HOSTNAME)
                validate_runtime "$key" "$value" "$file:$number"
                runtime[$key]=$value
                ;;
            *) fail "$file:$number: Unknown option $key" ;;
        esac
    done < "$file"
}

validate_runtime() {
    local key=$1 value=$2 context=$3
    case "$key" in
        TURBOSTAT_INTERVAL)
            [[ "$value" =~ ^[1-9][0-9]*$ ]] ||
                fail "$context: TURBOSTAT_INTERVAL must be a positive integer in seconds"
            ;;
        TURBOSTAT_BIN)
            [[ "$value" =~ ^/[a-zA-Z0-9_./+-]+$ ]] ||
                fail "$context: TURBOSTAT_BIN must be an absolute path without spaces or shell expansion"
            ;;
        METRICS_MANAGER_HOSTNAME)
            [[ "$value" =~ ^[a-zA-Z0-9_.:-]*$ ]] ||
                fail "$context: METRICS_MANAGER_HOSTNAME must contain only letters, digits, _, ., :, - (or be empty)"
            ;;
    esac
}

configured_turbostat() {
    local binary=/usr/bin/turbostat line value
    if [[ -v 'runtime[TURBOSTAT_BIN]' ]]; then
        binary=${runtime[TURBOSTAT_BIN]}
    elif exists "$CONFIG_DIR/metrics-manager.env"; then
        [[ -r "$CONFIG_DIR/metrics-manager.env" ]] || fail "Cannot read $CONFIG_DIR/metrics-manager.env"
        while IFS= read -r line || [[ -n "$line" ]]; do
            if [[ "$line" =~ ^[[:space:]]*TURBOSTAT_BIN[[:space:]]*=(.*)$ ]]; then
                value=${BASH_REMATCH[1]}
                value="${value#"${value%%[![:space:]]*}"}"
                value="${value%"${value##*[![:space:]]}"}"
                if [[ "$value" == \"*\" || "$value" == \'*\' ]]; then
                    value=${value:1:${#value}-2}
                fi
                validate_runtime TURBOSTAT_BIN "$value" "$CONFIG_DIR/metrics-manager.env"
                binary=$value
            fi
        done < "$CONFIG_DIR/metrics-manager.env"
    fi
    printf '%s\n' "$binary"
}

prepare_paths() {
    local key
    for key in TEMPERATURE INTERRUPTS NETWORK STORAGE; do
        destinations[$key]="$CONFIG_DIR/telegraf.d/${key,,}.conf"
        examples[$key]="$EXAMPLES_DIR/telegraf-${key,,}.conf"
    done
    destinations[NETWORK_VIRTUAL]="$CONFIG_DIR/telegraf.d/network-virtual.conf"
    examples[NETWORK_VIRTUAL]="$EXAMPLES_DIR/telegraf-network-virtual.conf"
    destinations[POWERSTAT_EXTRA]="$CONFIG_DIR/powerstat.d/extra.conf"
    examples[POWERSTAT_EXTRA]="$EXAMPLES_DIR/telegraf-powerstat-extra.conf"
    destinations[TURBOSTAT]="$CONFIG_DIR/powerstat.d/turbostat.conf"
    examples[TURBOSTAT]="$EXAMPLES_DIR/telegraf-turbostat.conf"
}

check_turbostat() {
    local binary=${1:-/usr/bin/turbostat} output
    [[ -x "$binary" ]] ||
        fail "Install $binary for the running kernel before enabling Turbostat"
    # Some versions print help to stderr and exit with status 1.
    if ! output=$("$binary" --version 2>&1); then
        fail "Cannot run $binary --version; install Turbostat tools matching the running kernel:
$output"
    fi
}

preflight() {
    local key destination binary
    command -v systemctl >/dev/null || fail "systemctl is required"
    if (( EUID != 0 )); then
        command -v sudo >/dev/null || fail "Run as root or install sudo"
    fi
    for key in "${OPTIONS[@]}"; do
        [[ "$key" == RAPL || "${settings[$key]}" == auto ]] && continue
        destination=${destinations[$key]}
        case "${settings[$key]}" in
            true)
                if ! exists "$destination" && ! exists "$destination.disabled"; then
                    [[ -r "${examples[$key]}" ]] ||
                        fail "Missing example ${examples[$key]}; install the current Metrics Manager package"
                fi
                ;;
            false)
                if exists "$destination" && exists "$destination.disabled"; then
                    fail "Both $destination and $destination.disabled exist; resolve the conflict first"
                fi
                ;;
        esac
    done
    if (( ${#runtime[@]} > 0 )); then
        [[ -r "$CONFIG_DIR/metrics-manager.env" ]] ||
            fail "Cannot read $CONFIG_DIR/metrics-manager.env; install the current Metrics Manager package"
    fi
    if [[ "${settings[TURBOSTAT]}" == true || -v 'runtime[TURBOSTAT_BIN]' ]]; then
        binary=$(configured_turbostat)
        check_turbostat "$binary"
    fi
}

configure_runtime() (
    (( ${#runtime[@]} > 0 )) || return 0
    local work key line file index=0
    local -A written=()
    local -a targets=()
    work=$(mktemp -d)
    trap 'rm -f -- "$work/environment" "$work/turbostat-0" "$work/turbostat-1"; rmdir -- "$work"' EXIT

    while IFS= read -r line || [[ -n "$line" ]]; do
        if [[ "$line" =~ ^[[:space:]]*([A-Z_]+)[[:space:]]*= ]]; then
            key=${BASH_REMATCH[1]}
            if [[ -v "runtime[$key]" ]]; then
                if [[ ! -v "written[$key]" ]]; then
                    printf '%s=%s\n' "$key" "${runtime[$key]}"
                    written[$key]=1
                fi
                continue
            fi
        fi
        printf '%s\n' "$line"
    done < "$CONFIG_DIR/metrics-manager.env" > "$work/environment"
    for key in "${RUNTIME_OPTIONS[@]}"; do
        if [[ -v "runtime[$key]" && ! -v "written[$key]" ]]; then
            printf '%s=%s\n' "$key" "${runtime[$key]}" >> "$work/environment"
        fi
    done

    if [[ -v 'runtime[TURBOSTAT_BIN]' || -v 'runtime[TURBOSTAT_INTERVAL]' ]]; then
        for file in "${destinations[TURBOSTAT]}" "${destinations[TURBOSTAT]}.disabled"; do
            exists "$file" || continue
            # Migrate only explicitly selected fields, preserving other local settings.
            if ! awk -v path="${runtime[TURBOSTAT_BIN]+set}" \
                -v interval="${runtime[TURBOSTAT_INTERVAL]+set}" '
                /^[[:space:]]*\[/ { in_turbostat = 0 }
                /^[[:space:]]*\[\[inputs\.turbostat\]\][[:space:]]*(#.*)?$/ {
                    in_turbostat = 1
                    found = 1
                    print
                    if (path) print "  path = \"${TURBOSTAT_BIN}\""
                    if (interval) print "  interval = \"${TURBOSTAT_INTERVAL}s\""
                    next
                }
                in_turbostat && path && /^[[:space:]]*path[[:space:]]*=/ { next }
                in_turbostat && interval && /^[[:space:]]*interval[[:space:]]*=/ { next }
                { print }
                END { if (!found) exit 1 }
            ' "$file" > "$work/turbostat-$index"; then
                fail "Cannot update $file: expected an [[inputs.turbostat]] block"
            fi
            targets+=("$file")
            index=$((index + 1))
        done
    fi

    run install -o root -g root -m 0644 "$work/environment" "$CONFIG_DIR/metrics-manager.env"
    for index in "${!targets[@]}"; do
        run install -o root -g root -m 0644 "$work/turbostat-$index" "${targets[$index]}"
    done
    for key in "${RUNTIME_OPTIONS[@]}"; do
        [[ ! -v "runtime[$key]" ]] || printf '%s=%s\n' "$key" "${runtime[$key]}"
    done
)

configure_dropin() {
    local key=$1 destination=${destinations[$1]}
    case "${settings[$key]}" in
        true)
            if exists "$destination"; then
                printf 'Keeping %s\n' "$destination"
            else
                run install -d -o root -g root -m 0755 "$(dirname -- "$destination")"
                if exists "$destination.disabled"; then
                    run mv -- "$destination.disabled" "$destination"
                else
                    run install -o root -g root -m 0644 "${examples[$key]}" "$destination"
                fi
            fi
            ;;
        false)
            if exists "$destination"; then
                run mv -- "$destination" "$destination.disabled"
            fi
            ;;
    esac
}

main() {
    if [[ "${1:-}" == --help || "${1:-}" == -h ]]; then
        printf 'Usage: %s [options.conf]\nDefault: %s/metrics-options.conf\n' "$0" "$NATIVE_DIR"
        printf 'Options: ENABLE_*=true|false|auto, TURBOSTAT_INTERVAL=seconds,\n'
        printf '         TURBOSTAT_BIN=/absolute/path, METRICS_MANAGER_HOSTNAME=name (empty resets).\n'
        printf 'Omitted settings are unchanged. Values are unquoted; shell expansion is not supported.\n'
        return
    fi
    (( $# <= 1 )) || fail "Usage: $0 [options.conf]"
    read_options "${1:-$NATIVE_DIR/metrics-options.conf}"
    prepare_paths
    preflight

    local key
    for key in "${OPTIONS[@]}"; do
        printf 'ENABLE_%s=%s\n' "$key" "${settings[$key]}"
        if [[ "$key" != RAPL ]]; then
            configure_dropin "$key"
        fi
    done
    configure_runtime
    case "${settings[RAPL]}" in
        true) run systemctl enable --now metrics-manager-rapl.service ;;
        false) run systemctl disable --now metrics-manager-rapl.service ;;
    esac

    # A plain restart would also start a loaded RAPL unit just disabled above.
    run systemctl try-restart 'metrics-manager-*.service'
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    trap 'printf "configure-metrics.sh: Failed at line %s: %s\n" "$LINENO" "$BASH_COMMAND" >&2' ERR
    main "$@"
fi
