#!/bin/bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# set_thermal_profile.sh - Generate, apply and verify a thermald thermal profile.
#
# Builds a /etc/thermald/thermal-conf.xml with a staged escalation on the CPU
# package sensor (x86_pkg_temp):
#     Fan (active)  <  Processor (passive)  <  intel_powerclamp (passive)
# then makes thermald the sole thermal authority (--ignore-default-control,
# no --adaptive) via a systemd drop-in override, and verifies the result.
#
# Profiles (Fan / Processor / powerclamp trip points, in Celsius):
#     cool            55 / 70 / 80
#     warm            60 / 75 / 85   (default)
#     hot             70 / 90 / 95
#     thermal-max     95 / 100 / 104 (pushes to Tjmax headroom; runs hot)
#     custom          --fan/--proc/--clamp (supply your own)
#
# Usage:
#     sudo ./set_thermal_profile.sh --profile PROFILE [options]
#
# Options:
#     -p, --profile <name>    Profile to apply: cool|warm|hot|thermal-max|custom
#                             (default: warm). Must be given with this flag;
#                             a bare positional word is not accepted.
#     --fan   <C>             Fan (active) trip, Celsius        (custom only)
#     --proc  <C>             Processor (passive) trip, Celsius (custom only)
#     --clamp <C>             powerclamp (passive) trip, Celsius(custom only)
#     --charge                Add the CHRG (battery charge) cooling device to
#                             the top trip, if present on this platform.
#     -o, --output <file>     Write the XML here instead of installing it.
#                             Implies no daemon changes.
#     --disable               Stop thermald and disable it at boot (reverts to
#                             kernel default thermal control). Ignores profile
#                             options; leaves config/override files untouched.
#     -n, --dry-run           Print what would happen; write nothing, change
#                             nothing. Emits the generated XML to stdout.
#     -h, --help              Show this help.
#
# Examples:
#     sudo ./set_thermal_profile.sh --profile warm
#     sudo ./set_thermal_profile.sh -p cool --charge
#     sudo ./set_thermal_profile.sh --profile custom --fan 50 --proc 65 --clamp 78
#     ./set_thermal_profile.sh --profile hot --dry-run
#     sudo ./set_thermal_profile.sh --profile thermal-max   # runs near Tjmax
#     sudo ./set_thermal_profile.sh --disable
#
set -euo pipefail

# ---- constants ------------------------------------------------------------
THERMALD_BIN="/usr/sbin/thermald"
CONF_FILE="/etc/thermald/thermal-conf.xml"
OVERRIDE_DIR="/etc/systemd/system/thermald.service.d"
OVERRIDE_FILE="${OVERRIDE_DIR}/override.conf"
COOLING_GLOB="/sys/class/thermal/cooling_device*"
PKG_SENSOR="x86_pkg_temp"
ZONE_NAME="CPU_Zone"
RAPL_CONSTRAINT_FILE="/sys/class/powercap/intel-rapl/intel-rapl:0/constraint_0_power_limit_uw"

# The command line thermald must run with for our config to be authoritative.
# --adaptive is deliberately omitted: on DPTF/GDDV platforms it makes the
# firmware adaptive tables override thermal-conf.xml.
# NOTE: --disable-active-power only skips thermald's *secondary* RAPL MMIO
# shadow device (rapl_controller_mmio); it does NOT stop thermald from
# unconditionally creating its primary "rapl_controller" device on
# /sys/.../intel-rapl:0/, which force-writes constraint_0_power_limit_uw to
# the platform's PPCC/ACPI max power the moment thermald starts (thd_cdev_rapl.cpp
# update()->read_ppcc_power_limits()), regardless of any CLI flag. The only way
# to stop that write from clobbering a custom cap is to give thermald our own
# limit via a <PPCC> block in thermal-conf.xml (see --rapl-cap), so it resets
# to OUR value instead of the platform default.
EXEC_START="${THERMALD_BIN} --systemd --dbus-enable --ignore-default-control"

# ---- output helpers -------------------------------------------------------
c_red=$'\e[31m'; c_grn=$'\e[32m'; c_ylw=$'\e[33m'; c_dim=$'\e[2m'; c_rst=$'\e[0m'
info() { printf '%s[*]%s %s\n' "$c_grn" "$c_rst" "$*"; }
warn() { printf '%s[!]%s %s\n' "$c_ylw" "$c_rst" "$*" >&2; }
err()  { printf '%s[x]%s %s\n' "$c_red" "$c_rst" "$*" >&2; }
die()  { err "$@"; exit 1; }

# ---- defaults / arg parsing ----------------------------------------------
PROFILE="warm"
FAN_C=""; PROC_C=""; CLAMP_C=""
WANT_CHARGE=0
DRY_RUN=0
OUTPUT_OVERRIDE=""
DISABLE=0

usage() { sed -n '2,/^set -euo/{/^set -euo/!p}' "$0" | sed 's/^# \{0,1\}//'; }

# Profile must be given via --profile/-p; a bare positional word is rejected.
valid_profile() { [[ "$1" =~ ^(cool|warm|hot|thermal-max|custom)$ ]]; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --profile|-p)
            PROFILE="${2:-}"
            valid_profile "$PROFILE" || die "Invalid --profile '$PROFILE' (cool|warm|hot|thermal-max|custom)"
            shift 2 ;;
        --fan)      FAN_C="${2:-}";   shift 2 ;;
        --proc)     PROC_C="${2:-}";  shift 2 ;;
        --clamp)    CLAMP_C="${2:-}"; shift 2 ;;
        --charge)   WANT_CHARGE=1; shift ;;
        -o|--output) OUTPUT_OVERRIDE="${2:-}"; shift 2 ;;
        -n|--dry-run) DRY_RUN=1; shift ;;
        --disable)  DISABLE=1; shift ;;
        -h|--help)  usage; exit 0 ;;
        *) die "Unknown argument: $1  (see --help)" ;;
    esac
done

# ---- --disable: stop and disable the daemon, then exit --------------------
if (( DISABLE )); then
    if (( DRY_RUN )); then
        warn "DRY-RUN: would stop thermald and disable it from starting at boot."
        echo "${c_dim}--- would run ---${c_rst}"
        printf '    %s\n' "systemctl stop thermald" "systemctl disable thermald"
        echo "${c_dim}(config file and override.conf are left untouched)${c_rst}"
        exit 0
    fi
    [[ $EUID -eq 0 ]] || die "Disabling thermald requires root. Re-run with sudo (or add --dry-run)."
    info "Stopping thermald..."
    systemctl stop thermald 2>/dev/null || true
    info "Disabling thermald at boot..."
    systemctl disable thermald 2>/dev/null || true
    if systemctl is-active --quiet thermald; then
        warn "thermald is still active; check: systemctl status thermald"
    else
        info "thermald stopped and disabled. Kernel default thermal control now applies."
        info "Re-enable later with: sudo systemctl enable --now thermald"
    fi
    exit 0
fi

# ---- resolve profile trip points -----------------------------------------
case "$PROFILE" in
    cool)        def_fan=55; def_proc=70;  def_clamp=80 ;;
    warm)        def_fan=60; def_proc=75;  def_clamp=85 ;;
    hot)         def_fan=70; def_proc=90;  def_clamp=95 ;;
    thermal-max) def_fan=95; def_proc=100; def_clamp=104 ;;
    custom)      def_fan="";  def_proc="";  def_clamp="" ;;
    *) die "Unknown profile: $PROFILE" ;;
esac

# For non-custom profiles, --fan/--proc/--clamp override individual values.
FAN_C="${FAN_C:-$def_fan}"
PROC_C="${PROC_C:-$def_proc}"
CLAMP_C="${CLAMP_C:-$def_clamp}"

if [[ "$PROFILE" == "custom" ]]; then
    [[ -n "$FAN_C" && -n "$PROC_C" && -n "$CLAMP_C" ]] \
        || die "custom profile requires --fan, --proc and --clamp"
fi

# ---- validate the trip points ---------------------------------------------
is_int() { [[ "$1" =~ ^[0-9]+$ ]]; }
for v in "$FAN_C" "$PROC_C" "$CLAMP_C"; do
    is_int "$v" || die "Trip points must be positive integers (Celsius); got '$v'"
done

# Ordering is what makes the escalation correct: fan first, clamp last.
(( FAN_C < PROC_C )) || die "Fan trip ($FAN_C) must be < Processor trip ($PROC_C)"
(( PROC_C < CLAMP_C )) || die "Processor trip ($PROC_C) must be < powerclamp trip ($CLAMP_C)"

# Sanity vs silicon Tjmax (~110C) and a plausible floor.
(( CLAMP_C < 105 )) || die "powerclamp trip ($CLAMP_C) too close to Tjmax; use < 105"
(( FAN_C >= 30 )) || warn "Fan trip ($FAN_C C) is near/below idle temp; CPU may stay throttled."

# ---- detect cooling devices present on this platform ----------------------
declare -A HAVE=()
if compgen -G "$COOLING_GLOB" >/dev/null; then
    for d in $COOLING_GLOB; do
        t="$(cat "$d/type" 2>/dev/null || true)"
        [[ -n "$t" ]] && HAVE["$t"]=$(( ${HAVE["$t"]:-0} + 1 ))
    done
else
    warn "No cooling devices found under ${COOLING_GLOB%\*} - is this the target host?"
fi

have_dev() { [[ -n "${HAVE[$1]:-}" ]]; }

info "Cooling devices detected on this platform:"
if (( ${#HAVE[@]} )); then
    for t in "${!HAVE[@]}"; do printf '      %-18s x%d\n' "$t" "${HAVE[$t]}"; done | sort
else
    printf '      (none)\n'
fi

# Decide which devices we can actually wire into the config.
USE_FAN=0;  have_dev Fan              && USE_FAN=1
USE_PROC=0; have_dev Processor        && USE_PROC=1
USE_CLAMP=0;have_dev intel_powerclamp && USE_CLAMP=1
USE_CHRG=0
if (( WANT_CHARGE )); then
    if have_dev CHRG; then USE_CHRG=1; else warn "--charge requested but no CHRG device present; skipping."; fi
fi

(( USE_FAN ))   || warn "No 'Fan' cooling device; STEP 1 (active) will be omitted."
(( USE_PROC ))  || warn "No 'Processor' cooling device; STEP 2 (passive) will be omitted."
(( USE_CLAMP )) || warn "No 'intel_powerclamp' device; STEP 3 (passive) will be omitted."
(( USE_FAN + USE_PROC + USE_CLAMP )) || die "None of the expected cooling devices are present; refusing to write an empty zone."

# ---- read the currently-applied RAPL cap (e.g. from set_power_profile.sh) --
# Embedding it as thermald's own PPCC max means thermald's startup reset lands
# on this value instead of the platform's ACPI/DPTF default.
RAPL_CAP_UW=""
if [[ -r "$RAPL_CONSTRAINT_FILE" ]]; then
    RAPL_CAP_UW="$(cat "$RAPL_CONSTRAINT_FILE" 2>/dev/null || true)"
    is_int "${RAPL_CAP_UW:-}" || RAPL_CAP_UW=""
fi
if [[ -n "$RAPL_CAP_UW" ]]; then
    info "Current RAPL PL1 cap: $(( RAPL_CAP_UW / 1000000 ))W (from ${RAPL_CONSTRAINT_FILE}); embedding as PPCC max."
else
    warn "Could not read ${RAPL_CONSTRAINT_FILE}; no PPCC block will be embedded."
fi

# ---- generate the XML ------------------------------------------------------
gen_xml() {
    printf '%s\n' '<?xml version="1.0"?>'
    printf '%s\n' '<ThermalConfiguration>'
    printf '%s\n' '    <Platform>'
    printf '        <Name>Strict %sC (%s)</Name>\n' "$CLAMP_C" "$PROFILE"
    printf '%s\n' '        <!-- Wildcard: applies on any machine. Replace * with the exact DMI'
    printf '%s\n' '             product name (cat /sys/class/dmi/id/product_name) to pin it. -->'
    printf '%s\n' '        <ProductName>*</ProductName>'
    printf '%s\n' '        <Preference>QUIET</Preference>'
    printf '%s\n' ''
    if [[ -n "$RAPL_CAP_UW" ]]; then
        local max_mw min_mw
        max_mw=$(( RAPL_CAP_UW / 1000 ))
        min_mw=$(awk -v v="$max_mw" 'BEGIN{ m=v*0.3; printf "%d", (m<2000)?2000:m }')
        printf '%s\n' '        <!-- thermald always force-writes its RAPL cooling device to this PPCC'
        printf '%s\n' '             limit at startup (see thd_cdev_rapl.cpp update()); giving it the cap'
        printf '%s\n' '             already applied (e.g. by set_power_profile.sh) means that reset lands'
        printf '%s\n' '             on our value, not the platform default. -->'
        printf '%s\n' '        <PPCC>'
        printf '%s\n' '            <PowerLimitIndex>0</PowerLimitIndex>'
        printf '            <PowerLimitMaximum>%d</PowerLimitMaximum>\n' "$max_mw"
        printf '            <PowerLimitMinimum>%d</PowerLimitMinimum>\n' "$min_mw"
        printf '%s\n' '            <TimeWindowMinimum>20</TimeWindowMinimum>'
        printf '%s\n' '            <TimeWindowMaximum>60</TimeWindowMaximum>'
        printf '%s\n' '            <StepSize>1000</StepSize>'
        printf '%s\n' '        </PPCC>'
        printf '%s\n' ''
    fi
    printf '%s\n' '        <ThermalSensors>'
    printf '%s\n' '            <ThermalSensor>'
    printf '                <Type>%s</Type>\n' "$PKG_SENSOR"
    printf '%s\n' '                <AsyncCapable>1</AsyncCapable>'
    printf '%s\n' '            </ThermalSensor>'
    printf '%s\n' '        </ThermalSensors>'
    printf '%s\n' ''
    printf '%s\n' '        <ThermalZones>'
    printf '%s\n' '            <ThermalZone>'
    printf '                <Type>%s</Type>\n' "$ZONE_NAME"
    printf '%s\n' '                <TripPoints>'

    if (( USE_FAN )); then
        printf '\n                    <!-- STEP 1: fans on early (%sC), no performance cost -->\n' "$FAN_C"
        gen_trip active "$FAN_C" "Fan:100:5"
    fi
    if (( USE_PROC )); then
        printf '\n                    <!-- STEP 2: cap CPU frequency (%sC) -->\n' "$PROC_C"
        gen_trip passive "$PROC_C" "Processor:150:2"
    fi
    if (( USE_CLAMP )); then
        printf '\n                    <!-- STEP 3: hard limit (%sC), inject idle cycles -->\n' "$CLAMP_C"
        if (( USE_CHRG )); then
            gen_trip passive "$CLAMP_C" "intel_powerclamp:200:1" "CHRG:50:5"
        else
            gen_trip passive "$CLAMP_C" "intel_powerclamp:200:1"
        fi
    fi

    printf '%s\n' '                </TripPoints>'
    printf '%s\n' '            </ThermalZone>'
    printf '%s\n' '        </ThermalZones>'
    printf '%s\n' '    </Platform>'
    printf '%s\n' '</ThermalConfiguration>'
}

# gen_trip <type> <celsius> <dev:influence:sampling>...
gen_trip() {
    local ttype="$1" celsius="$2"; shift 2
    printf '                    <TripPoint>\n'
    printf '                        <SensorType>%s</SensorType>\n' "$PKG_SENSOR"
    printf '                        <Temperature>%d</Temperature>\n' $(( celsius * 1000 ))
    printf '                        <type>%s</type>\n' "$ttype"
    printf '                        <ControlType>SEQUENTIAL</ControlType>\n'
    local spec dev infl samp
    for spec in "$@"; do
        IFS=':' read -r dev infl samp <<<"$spec"
        printf '                        <CoolingDevice>\n'
        printf '                            <type>%s</type>\n' "$dev"
        printf '                            <influence>%s</influence>\n' "$infl"
        printf '                            <SamplingPeriod>%s</SamplingPeriod>\n' "$samp"
        printf '                        </CoolingDevice>\n'
    done
    printf '                    </TripPoint>\n'
}

XML_CONTENT="$(gen_xml)"

info "Profile '${PROFILE}' -> Fan:${FAN_C}C  Processor:${PROC_C}C  powerclamp:${CLAMP_C}C$( ((USE_CHRG)) && printf '  +CHRG' )"

# ---- dry-run: show summary and exit ----------------------------------------
if (( DRY_RUN )); then
    warn "DRY-RUN: no files written, no services touched."
    echo "${c_dim}--- summary ---${c_rst}"
    printf '    %-16s %s\n' "Profile:"     "$PROFILE"
    printf '    %-16s %sC (active)\n'       "Fan trip:"        "$FAN_C"
    printf '    %-16s %sC (passive)\n'      "Processor trip:"  "$PROC_C"
    printf '    %-16s %sC (passive)\n'      "powerclamp trip:" "$CLAMP_C"
    printf '    %-16s %s\n'                 "CHRG device:"     "$( ((USE_CHRG)) && echo 'yes' || echo 'no' )"
    printf '    %-16s %s\n'                 "RAPL cap:"        "$( [[ -n "$RAPL_CAP_UW" ]] && echo "$(( RAPL_CAP_UW / 1000000 ))W (via PPCC, read from sysfs)" || echo 'none' )"
    printf '    %-16s %s\n'                 "Config target:"   "${OUTPUT_OVERRIDE:-$CONF_FILE}"
    printf '    %-16s %s\n'                 "Override:"        "$OVERRIDE_FILE"
    printf '    %-16s %s\n'                 "ExecStart:"       "$EXEC_START"
    echo "${c_dim}--- would then: write config; ensure override; daemon-reload; restart thermald; verify parse ---${c_rst}"
    echo "${c_dim}(re-run without --dry-run to apply, or with -o FILE to write the XML)${c_rst}"
    exit 0
fi

# ---- output-only mode: write XML, no daemon changes ------------------------
if [[ -n "$OUTPUT_OVERRIDE" ]]; then
    printf '%s\n' "$XML_CONTENT" > "$OUTPUT_OVERRIDE"
    info "Wrote XML to ${OUTPUT_OVERRIDE} (no daemon changes)."
    exit 0
fi

# ---- from here on we mutate the system: require root -----------------------
[[ $EUID -eq 0 ]] || die "Applying to ${CONF_FILE} requires root. Re-run with sudo (or use --dry-run / -o)."
[[ -x "$THERMALD_BIN" ]] || die "thermald not found at ${THERMALD_BIN}."

# ---- validate the generated XML with thermald before installing -----------
tmp_xml="$(mktemp /tmp/thermal-conf.XXXXXX.xml)"
trap 'rm -f "$tmp_xml"' EXIT
printf '%s\n' "$XML_CONTENT" > "$tmp_xml"

# A running daemon holds thermald's lock file, so a --no-daemon validation run
# would exit with "already running" instead of parsing. Stop it first; we
# restart (with the new config) at the end regardless of outcome.
was_active=0
if systemctl is-active --quiet thermald; then
    was_active=1
    info "Stopping running thermald for a clean validation..."
    systemctl stop thermald
fi
# If we abort before the normal restart, bring the daemon back up so the host
# is never left thermally unmanaged.
restore_daemon() {
    if (( was_active )); then
        systemctl start thermald 2>/dev/null || true
    fi
}

info "Validating generated config with thermald (test mode)..."
verify_log="$(mktemp /tmp/thermald-verify.XXXXXX.log)"
timeout 8 "$THERMALD_BIN" --no-daemon --test-mode --loglevel=info \
    --config-file "$tmp_xml" >"$verify_log" 2>&1 || true

if grep -q "$ZONE_NAME" "$verify_log" && grep -qi "Product Name matched" "$verify_log"; then
    trips_seen="$(grep -c 'temp/power' "$verify_log" || true)"
    info "Validation OK: zone '${ZONE_NAME}' loaded, ${trips_seen} trip point(s) parsed, platform matched."
else
    err "thermald did not accept the generated config. Log excerpt:"
    grep -iE 'error|invalid|fail|Zone|Trip|matched' "$verify_log" | grep -viE 'powercap|RAPL|sysfs' | head -20 >&2 || true
    rm -f "$verify_log"
    restore_daemon
    die "Aborting without changing the system."
fi
rm -f "$verify_log"

# ---- install the config (back up any existing) -----------------------------
if [[ -f "$CONF_FILE" ]]; then
    backup="${CONF_FILE}.bak"
    cp -f "$CONF_FILE" "$backup"
    info "Backed up existing config -> ${backup}"
else
    mkdir -p "$(dirname "$CONF_FILE")"
fi
install -m 0644 "$tmp_xml" "$CONF_FILE"
info "Installed config -> ${CONF_FILE}"

# ---- ensure the systemd override (ignore-default-control, no --adaptive) ---
need_reload=0
desired_override="$(cat <<EOF
[Service]
# Managed by set_thermal_profile.sh
# Reset the packaged ExecStart, then re-declare it with --ignore-default-control
# and WITHOUT --adaptive, so the trip points in ${CONF_FILE} are the sole
# thermal authority (firmware DPTF/GDDV adaptive tables would otherwise win).
ExecStart=
ExecStart=${EXEC_START}
EOF
)"

mkdir -p "$OVERRIDE_DIR"
if [[ ! -f "$OVERRIDE_FILE" ]]; then
    printf '%s\n' "$desired_override" > "$OVERRIDE_FILE"
    info "Created override -> ${OVERRIDE_FILE}"
    need_reload=1
elif [[ "$(cat "$OVERRIDE_FILE")" != "$desired_override" ]]; then
    cp -f "$OVERRIDE_FILE" "${OVERRIDE_FILE}.bak"
    printf '%s\n' "$desired_override" > "$OVERRIDE_FILE"
    info "Updated override -> ${OVERRIDE_FILE} (previous saved as ${OVERRIDE_FILE}.bak)"
    need_reload=1
else
    info "Override already correct -> ${OVERRIDE_FILE}"
fi

# ---- reload + restart ------------------------------------------------------
if (( need_reload )); then
    systemctl daemon-reload
    info "systemd daemon-reloaded."
fi
systemctl restart thermald
sleep 2

# ---- verify the running daemon --------------------------------------------
if ! systemctl is-active --quiet thermald; then
    err "thermald is not active after restart. Recent status:"
    systemctl status thermald --no-pager -n 15 >&2 || true
    die "Restore with: cp ${CONF_FILE}.bak ${CONF_FILE} && systemctl restart thermald"
fi

running_cmd="$(systemctl show thermald -p ExecStart --no-pager | tr ';' '\n' | grep -o 'argv\[\]=.*' | sed 's/argv\[\]=//')"
info "thermald is active."
info "Effective ExecStart:${running_cmd:+ $running_cmd}"

if grep -q -- '--ignore-default-control' <<<"$running_cmd" && ! grep -q -- '--adaptive' <<<"$running_cmd"; then
    info "Daemon is the sole thermal authority (ignore-default-control set, adaptive off). ✔"
else
    warn "Daemon flags are not as expected; check ${OVERRIDE_FILE}."
fi

# The installed file is byte-identical to the one we validated above (before the
# daemon restart), so re-parsing is unnecessary - and a --no-daemon run now would
# just hit the running daemon's lock file. Confirm on-disk instead.
if cmp -s "$tmp_xml" "$CONF_FILE"; then
    info "Live config: zone '${ZONE_NAME}' installed with trips ${FAN_C}/${PROC_C}/${CLAMP_C}C (validated pre-restart)."
else
    warn "Installed config differs from the validated one; inspect ${CONF_FILE}."
fi

echo
info "Done. Current package temp: $(( $(cat /sys/class/thermal/thermal_zone4/temp 2>/dev/null || echo 0) / 1000 ))C"
