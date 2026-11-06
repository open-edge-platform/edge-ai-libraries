#!/usr/bin/env bash
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

set -Eeuo pipefail

TEST_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=../configure-metrics.sh
source "$TEST_DIR/../configure-metrics.sh"

WORK=$(mktemp -d)
trap 'rm -rf -- "$WORK"' EXIT
CONFIG_DIR="$WORK/etc"
EXAMPLES_DIR="$WORK/examples"
LOG="$WORK/commands"
mkdir -p "$CONFIG_DIR" "$EXAMPLES_DIR" "$WORK/bin"
printf '#!/bin/sh\nexit 0\n' > "$WORK/bin/systemctl"
printf '#!/bin/sh\nif [ "$1" = -- ]; then shift; fi\nexec "$@"\n' > "$WORK/bin/sudo"
chmod +x "$WORK/bin/systemctl" "$WORK/bin/sudo"
export PATH="$WORK/bin:$PATH"

# Only filesystem operations in the temporary tree are executed.
run() {
    printf '%s\n' "$*" >> "$LOG"
    case "$1" in
        systemctl) ;;
        install)
            if [[ "$2" == -d ]]; then
                mkdir -p -- "${@: -1}"
            else
                command install -m 0644 -- "${@: -2:1}" "${@: -1}"
            fi
            ;;
        mv) command "$@" ;;
        *) fail "Unexpected test command: $*" ;;
    esac
}

assert_logged() {
    grep -Fxq -- "$*" "$LOG" || fail "Command not logged: $*"
}

expect_failure() {
    local options=$1 expected=$2 status
    : > "$LOG"
    # Match the executable's errexit behavior, including failures in subshells.
    set +e
    (set -e; main "$options") > "$WORK/stdout" 2> "$WORK/stderr"
    status=$?
    set -e
    (( status != 0 )) || fail "Expected failure for $options"
    grep -Fq -- "$expected" "$WORK/stderr" || fail "Missing error: $expected"
    [[ ! -s "$LOG" ]] || fail "Invalid configuration caused side effects"
}

# Local operator settings must not influence the test or touch host services.
printf 'ENABLE_RAPL=auto\n' > "$WORK/options"
main "$WORK/options" > "$WORK/stdout"
[[ $(wc -l < "$LOG") == 1 ]] || fail "auto changed configuration"
assert_logged "systemctl try-restart metrics-manager-*.service"

mkdir -p "$WORK/native"
cp "$NATIVE_DIR/configure-metrics.sh" "$WORK/native/configure-metrics.sh"
cp "$WORK/options" "$WORK/native/metrics-options.conf"
bash "$WORK/native/configure-metrics.sh" > "$WORK/stdout"
grep -Fxq 'ENABLE_RAPL=auto' "$WORK/stdout" || fail "Default options were not loaded"
bash "$NATIVE_DIR/configure-metrics.sh" --help > "$WORK/stdout"
grep -Fq 'Usage:' "$WORK/stdout" || fail "Help was not printed"

printf 'ENABLE_RAPL=true\n' > "$WORK/options"
: > "$LOG"
main "$WORK/options" > "$WORK/stdout"
assert_logged "systemctl enable --now metrics-manager-rapl.service"
[[ $(tail -n 1 "$LOG") == 'systemctl try-restart metrics-manager-*.service' ]] ||
    fail "Services were not reloaded last"

printf 'ENABLE_RAPL=false\n' > "$WORK/options"
: > "$LOG"
main "$WORK/options" > "$WORK/stdout"
assert_logged "systemctl disable --now metrics-manager-rapl.service"
assert_logged "systemctl try-restart metrics-manager-*.service"
[[ $(wc -l < "$LOG") == 2 ]] || fail "Unexpected service operation"

prepare_paths
for key in POWERSTAT_EXTRA TEMPERATURE INTERRUPTS NETWORK NETWORK_VIRTUAL STORAGE; do
    printf 'example %s\n' "$key" > "${examples[$key]}"
    printf 'ENABLE_%s=true\n' "$key" > "$WORK/options"
    main "$WORK/options" > "$WORK/stdout"
    cmp "${examples[$key]}" "${destinations[$key]}"
    printf 'local %s\n' "$key" > "${destinations[$key]}"
    main "$WORK/options" > "$WORK/stdout"
    [[ $(< "${destinations[$key]}") == "local $key" ]] || fail "Local configuration overwritten"
    printf 'ENABLE_%s=false\n' "$key" > "$WORK/options"
    main "$WORK/options" > "$WORK/stdout"
    [[ ! -e "${destinations[$key]}" && -f "${destinations[$key]}.disabled" ]] ||
        fail "Drop-in not disabled: $key"
    main "$WORK/options" > "$WORK/stdout"
    printf 'ENABLE_%s=true\n' "$key" > "$WORK/options"
    main "$WORK/options" > "$WORK/stdout"
    [[ $(< "${destinations[$key]}") == "local $key" ]] || fail "Local configuration not restored"
    [[ ! -e "${destinations[$key]}.disabled" ]] || fail "Disabled file not restored"
done

[[ "${destinations[NETWORK_VIRTUAL]}" == "$CONFIG_DIR/telegraf.d/network-virtual.conf" ]] ||
    fail "Wrong virtual network destination"
[[ "${examples[NETWORK_VIRTUAL]}" == "$EXAMPLES_DIR/telegraf-network-virtual.conf" ]] ||
    fail "Wrong virtual network example"
printf 'ENABLE_NETWORK=false\nENABLE_NETWORK_VIRTUAL=true\n' > "$WORK/options"
main "$WORK/options" > "$WORK/stdout"
[[ ! -e "${destinations[NETWORK]}" && -f "${destinations[NETWORK_VIRTUAL]}" ]] ||
    fail "Virtual NIC collection depends on traffic collection"
printf 'ENABLE_NETWORK=true\nENABLE_NETWORK_VIRTUAL=false\n' > "$WORK/options"
main "$WORK/options" > "$WORK/stdout"
[[ -f "${destinations[NETWORK]}" && ! -e "${destinations[NETWORK_VIRTUAL]}" ]] ||
    fail "Disabling virtual NIC collection changed traffic collection"
[[ $(< "${destinations[NETWORK]}") == "local NETWORK" ]] ||
    fail "Network interface selection was overwritten"

rm -- "${examples[NETWORK_VIRTUAL]}" "${destinations[NETWORK_VIRTUAL]}.disabled"
printf 'ENABLE_RAPL=true\nENABLE_NETWORK_VIRTUAL=true\n' > "$WORK/options"
expect_failure "$WORK/options" 'Missing example'
printf 'virtual example\n' > "${examples[NETWORK_VIRTUAL]}"
main "$WORK/options" > "$WORK/stdout"
printf 'backup\n' > "${destinations[NETWORK_VIRTUAL]}.disabled"
printf 'ENABLE_NETWORK_VIRTUAL=false\n' > "$WORK/options"
expect_failure "$WORK/options" 'resolve the conflict first'

# Turbostat can return 1 for help despite being installed and functional.
cat > "$WORK/bin/turbostat" <<'EOF'
#!/bin/sh
case "$1" in
    --help) echo 'Usage: turbostat [OPTIONS]' >&2; exit 1 ;;
    --version) echo 'turbostat version 2026.01.01' >&2 ;;
    *) exit 99 ;;
esac
EOF
chmod +x "$WORK/bin/turbostat"
check_turbostat "$WORK/bin/turbostat" > "$WORK/stdout" 2> "$WORK/stderr"
[[ ! -s "$WORK/stdout" && ! -s "$WORK/stderr" ]] || fail "Version probe was not quiet"

printf '#!/bin/sh\necho "WARNING: turbostat not found for kernel test" >&2\nexit 2\n' > "$WORK/bin/turbostat"
if (check_turbostat "$WORK/bin/turbostat") > "$WORK/stdout" 2> "$WORK/stderr"; then
    fail "Missing kernel tools were ignored"
fi
grep -Fq 'Cannot run' "$WORK/stderr" || fail "Missing actionable Turbostat error"
grep -Fq 'WARNING: turbostat not found for kernel test' "$WORK/stderr" ||
    fail "Original Turbostat diagnostic was lost"
if (check_turbostat "$WORK/bin/missing-turbostat") > "$WORK/stdout" 2> "$WORK/stderr"; then
    fail "Missing Turbostat executable was ignored"
fi
grep -Fq 'before enabling Turbostat' "$WORK/stderr" || fail "Missing executable diagnostic"

# Test Turbostat's drop-in mapping without requiring host MSR tools.
printf 'turbostat example\n' > "${examples[TURBOSTAT]}"
settings[TURBOSTAT]=true
configure_dropin TURBOSTAT
cmp "${examples[TURBOSTAT]}" "${destinations[TURBOSTAT]}"
settings[TURBOSTAT]=false
configure_dropin TURBOSTAT
[[ -f "${destinations[TURBOSTAT]}.disabled" ]] || fail "Turbostat not disabled"

printf 'ENABLE_RAPL=true\nENABLE_UNKNOWN=false\n' > "$WORK/options"
expect_failure "$WORK/options" 'Unknown option'
printf 'ENABLE_RAPL=true\nENABLE_RAPL=false\n' > "$WORK/options"
expect_failure "$WORK/options" 'Duplicate option'
printf 'ENABLE_RAPL=TRUE\n' > "$WORK/options"
expect_failure "$WORK/options" 'Expected ENABLE_OPTION=true|false|auto'
printf 'ENABLE_RAPL=$(touch %s/injected)\n' "$WORK" > "$WORK/options"
expect_failure "$WORK/options" 'Expected ENABLE_OPTION=true|false|auto'
[[ ! -e "$WORK/injected" ]] || fail "Options executed as shell code"
expect_failure "$WORK/missing" 'Cannot read options file'

printf 'backup\n' > "${destinations[NETWORK]}.disabled"
printf 'ENABLE_RAPL=true\nENABLE_NETWORK=false\n' > "$WORK/options"
expect_failure "$WORK/options" 'resolve the conflict first'

rm -- "${examples[TURBOSTAT]}" "${destinations[TURBOSTAT]}.disabled"
printf 'ENABLE_RAPL=true\nENABLE_TURBOSTAT=true\n' > "$WORK/options"
expect_failure "$WORK/options" 'Missing example'

printf '  # comment\r\n ENABLE_RAPL = auto # unchanged\r\nENABLE_NETWORK=auto' > "$WORK/options"
: > "$LOG"
main "$WORK/options" > "$WORK/stdout"
[[ $(wc -l < "$LOG") == 1 ]] || fail "Comments, CRLF or final unterminated line misparsed"

# Startup settings are validated before any privileged operation.
for value in 0 -1 1.5 05 auto ''; do
    printf 'TURBOSTAT_INTERVAL=%s\n' "$value" > "$WORK/options"
    expect_failure "$WORK/options" 'positive integer in seconds'
done
for value in turbostat '/path with spaces/turbostat' '$(uname -r)' ''; do
    printf 'TURBOSTAT_BIN=%s\n' "$value" > "$WORK/options"
    expect_failure "$WORK/options" 'absolute path'
done
printf 'METRICS_MANAGER_HOSTNAME=bad"name\n' > "$WORK/options"
expect_failure "$WORK/options" 'METRICS_MANAGER_HOSTNAME must contain'
printf 'TURBOSTAT_INTERVAL=2\nTURBOSTAT_INTERVAL=3\n' > "$WORK/options"
expect_failure "$WORK/options" 'Duplicate option TURBOSTAT_INTERVAL'
printf 'METRICS_MANAGER_HOSTNAME=lab-node-42\n' > "$WORK/options"
expect_failure "$WORK/options" 'Cannot read'

cp "$NATIVE_DIR/packaging/etc/metrics-manager.env" "$CONFIG_DIR/metrics-manager.env"
printf 'QMASSA_INTERVAL_MS=2500\nLOCAL_SETTING=keep-me\n' >> "$CONFIG_DIR/metrics-manager.env"
printf '#!/bin/sh\nprintf "%%s\\n" "$*" >> "%s"\n[ "$1" = --version ]\n' \
    "$WORK/turbostat-calls" > "$WORK/bin/turbostat"
chmod +x "$WORK/bin/turbostat"
cp "$NATIVE_DIR/packaging/etc/telegraf-turbostat.conf.example" "${examples[TURBOSTAT]}"
printf 'ENABLE_RAPL=true\nENABLE_TURBOSTAT=true\nTURBOSTAT_INTERVAL=2\nTURBOSTAT_BIN=%s\nMETRICS_MANAGER_HOSTNAME=lab-node-42\n' \
    "$WORK/bin/turbostat" > "$WORK/options"
: > "$LOG"
main "$WORK/options" > "$WORK/stdout"
grep -Fxq -- '--version' "$WORK/turbostat-calls" || fail "Custom Turbostat binary not checked"
for assignment in TURBOSTAT_INTERVAL=2 "TURBOSTAT_BIN=$WORK/bin/turbostat" METRICS_MANAGER_HOSTNAME=lab-node-42 \
    QMASSA_INTERVAL_MS=2500 LOCAL_SETTING=keep-me; do
    grep -Fxq "$assignment" "$CONFIG_DIR/metrics-manager.env" || fail "Lost setting: $assignment"
done
grep -Fq 'path = "${TURBOSTAT_BIN}"' "${destinations[TURBOSTAT]}" || fail "Binary not wired"
grep -Fq 'interval = "${TURBOSTAT_INTERVAL}s"' "${destinations[TURBOSTAT]}" || fail "Cadence not wired"
[[ $(tail -n 2 "$LOG" | head -n 1) == 'systemctl enable --now metrics-manager-rapl.service' ]] ||
    fail "RAPL started before startup settings were saved"

# Reapplying is idempotent and enabling without an override checks the persisted binary.
cp "$CONFIG_DIR/metrics-manager.env" "$WORK/saved-env"
cp "${destinations[TURBOSTAT]}" "$WORK/saved-turbostat"
main "$WORK/options" > "$WORK/stdout"
cmp "$WORK/saved-env" "$CONFIG_DIR/metrics-manager.env"
cmp "$WORK/saved-turbostat" "${destinations[TURBOSTAT]}"
: > "$WORK/turbostat-calls"
printf 'ENABLE_TURBOSTAT=true\n' > "$WORK/options"
main "$WORK/options" > "$WORK/stdout"
grep -Fxq -- '--version' "$WORK/turbostat-calls" || fail "Persisted binary not checked"
cmp "$WORK/saved-env" "$CONFIG_DIR/metrics-manager.env"

# Existing drop-ins gain only the selected fields, even while disabled.
cat > "${destinations[TURBOSTAT]}" <<'EOF'
# local settings
[[inputs.turbostat]]
  path = "/custom/turbostat"
  interval = "7s"
  use_sudo = false
  [inputs.turbostat.tags]
    interval = "keep-tag"
EOF
printf 'ENABLE_TURBOSTAT=false\nTURBOSTAT_INTERVAL=3\n' > "$WORK/options"
main "$WORK/options" > "$WORK/stdout"
grep -Fq 'path = "/custom/turbostat"' "${destinations[TURBOSTAT]}.disabled" ||
    fail "Unselected binary changed"
grep -Fq 'interval = "${TURBOSTAT_INTERVAL}s"' "${destinations[TURBOSTAT]}.disabled" ||
    fail "Disabled drop-in not migrated"
grep -Fq 'interval = "keep-tag"' "${destinations[TURBOSTAT]}.disabled" || fail "Nested tag changed"
grep -Fq 'use_sudo = false' "${destinations[TURBOSTAT]}.disabled" || fail "Local setting lost"
printf 'ENABLE_TURBOSTAT=true\nTURBOSTAT_BIN=%s\n' "$WORK/bin/turbostat" > "$WORK/options"
main "$WORK/options" > "$WORK/stdout"
grep -Fq 'path = "${TURBOSTAT_BIN}"' "${destinations[TURBOSTAT]}" || fail "Legacy binary not migrated"
grep -Fxq 'TURBOSTAT_INTERVAL=3' "$CONFIG_DIR/metrics-manager.env" || fail "Omitted interval changed"

# Empty hostname resets the default; unrelated settings and drop-ins stay intact.
cp "${destinations[TURBOSTAT]}" "$WORK/saved-turbostat"
printf ' METRICS_MANAGER_HOSTNAME = # kernel hostname\r\n' > "$WORK/options"
main "$WORK/options" > "$WORK/stdout"
grep -Fxq 'METRICS_MANAGER_HOSTNAME=' "$CONFIG_DIR/metrics-manager.env" || fail "Hostname not reset"
cmp "$WORK/saved-turbostat" "${destinations[TURBOSTAT]}"

# Upgrades can retain an environment file predating the Turbostat options.
printf 'METRICS_MANAGER_HOSTNAME=\nPROCESS_LIMIT=17\n' > "$CONFIG_DIR/metrics-manager.env"
printf 'TURBOSTAT_INTERVAL=9\nTURBOSTAT_BIN=%s\n' "$WORK/bin/turbostat" > "$WORK/options"
main "$WORK/options" > "$WORK/stdout"
grep -Fxq 'TURBOSTAT_INTERVAL=9' "$CONFIG_DIR/metrics-manager.env" || fail "New option not appended"
grep -Fxq 'PROCESS_LIMIT=17' "$CONFIG_DIR/metrics-manager.env" || fail "Existing option lost"
grep -Fxq 'Environment=TURBOSTAT_INTERVAL=5 TURBOSTAT_BIN=/usr/bin/turbostat' \
    "$NATIVE_DIR/packaging/systemd/metrics-manager-powerstat.service" || fail "Missing upgrade defaults"

printf 'TURBOSTAT_BIN=%s\n' "$WORK/bin/missing-turbostat" > "$WORK/options"
expect_failure "$WORK/options" 'before enabling Turbostat'
printf '#!/bin/sh\nexit 2\n' > "$WORK/bin/turbostat"
printf 'TURBOSTAT_BIN=%s\n' "$WORK/bin/turbostat" > "$WORK/options"
expect_failure "$WORK/options" 'Cannot run'
printf 'not a Turbostat config\n' > "${destinations[TURBOSTAT]}"
printf 'TURBOSTAT_INTERVAL=8\n' > "$WORK/options"
expect_failure "$WORK/options" 'expected an [[inputs.turbostat]] block'
grep -Fxq 'TURBOSTAT_INTERVAL=9' "$CONFIG_DIR/metrics-manager.env" || fail "Failed migration changed environment"

# Opt in with TELEGRAF_BIN to check the real plugin without MSR access or services.
if [[ -n "${TELEGRAF_BIN:-}" ]]; then
    [[ -x "$TELEGRAF_BIN" ]] || fail "TELEGRAF_BIN is not executable"
    cat > "$WORK/bin/turbostat" <<'EOF'
#!/bin/sh
if [ "$1" = --version ]; then exit 0; fi
printf '%s\n' "$*" > "$TURBOSTAT_TEST_ARGS"
printf 'CPU\tIPC\tSMI\n0\t2\t0\n'
exec sleep 30
EOF
    cp "$WORK/saved-turbostat" "${destinations[TURBOSTAT]}"
    printf 'TURBOSTAT_INTERVAL=2\nTURBOSTAT_BIN=%s\nMETRICS_MANAGER_HOSTNAME=lab-node-42\n' \
        "$WORK/bin/turbostat" > "$WORK/options"
    main "$WORK/options" > "$WORK/stdout"
    mkdir "$WORK/telegraf.d"
    cp "${destinations[TURBOSTAT]}" "$WORK/telegraf.d/turbostat.conf"
    (
        while IFS='=' read -r key value; do
            export "$key=$value"
        done < "$CONFIG_DIR/metrics-manager.env"
        export TURBOSTAT_TEST_ARGS="$WORK/turbostat-args"
        "$TELEGRAF_BIN" --config "$NATIVE_DIR/packaging/etc/telegraf-powerstat.conf" \
            --config-directory "$WORK/telegraf.d" --input-filter turbostat \
            --test --test-wait 1 > "$WORK/metrics" 2> "$WORK/telegraf-log" ||
            { cat "$WORK/telegraf-log" >&2; fail "Telegraf configuration test failed"; }
    )
    grep -Fxq -- '--quiet --interval 2 --show all' "$WORK/turbostat-args" ||
        fail "Telegraf did not pass the configured sampling cadence to the custom binary"
    grep -Eq '^> turbostat,.*host=lab-node-42[, ]' "$WORK/metrics" ||
        fail "Telegraf did not publish the configured host tag"
    grep -Eq ' ipc=2[, ]|,ipc=2[, ]' "$WORK/metrics" || fail "Missing Turbostat IPC sample"
fi

# Service errors must fail the executable and must not reach the final reload.
printf '#!/bin/sh\nexit 42\n' > "$WORK/bin/systemctl"
printf 'ENABLE_RAPL=true\n' > "$WORK/options"
if bash "$NATIVE_DIR/configure-metrics.sh" "$WORK/options" > "$WORK/stdout" 2> "$WORK/stderr"; then
    fail "Service failure was ignored"
else
    status=$?
    [[ "$status" == 42 ]] || fail "Service exit status lost: $status"
fi
grep -Fq 'Failed at line' "$WORK/stderr" || fail "Service error was not reported"

printf 'All configure-metrics tests passed.\n'
