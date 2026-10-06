#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# set_power_profile.sh - Set an intel_lpmd power profile and enforce it with a
# hard RAPL power cap (CPU + iGPU), either from a named platform profile or from
# explicit PkgWatt/SysWatt targets.
#
# This script merges the former set_power_profile.sh (named profiles) and
# set_platform_power.sh (low-level RAPL/MSR programming) into a single tool.
#
# Two ways to drive it:
#
#   1. Named profile (--profile), expressed as a PkgWatt (CPU package) budget.
#      PkgWatt is chosen as the profile parameter because the package power
#      limit can be enforced on every platform (via RAPL MSR 0x610), whereas the
#      SysWatt (psys / whole-platform) domain is not implemented on all silicon.
#
#          Profile               PkgWatt        Default burst ratio
#          -------               -------        -------------------
#          LowPower               10 W          1.25
#          BalancedLow            15 W          1.25
#          BalancedHigh           20 W          1.18
#          Performance            25 W          1.19
#          MaxPerformance         platform max  1.18  (cTDP Level 2, read at
#                                                      runtime from the MSRs)
#          Custom                  (none)       (uses the explicit --pkgWatt/--sysWatt
#                                                /--burstRatio/--pl1Tau flags instead)
#
#      psys (SysWatt) support:
#        * The package (PkgWatt) target is always enforced.
#        * On silicon that also exposes a platform (psys) RAPL power domain, the
#          whole-platform (SysWatt) limit is set to the same PkgWatt budget by
#          default, or to an explicit --sysWatt value when one is supplied.
#        * If psys is NOT supported, only the package cap is applied and any
#          --sysWatt value is ignored.
#
#   2. Explicit targets (--pkgWatt / --sysWatt) for fine-grained control:
#
#          --pkgWatt W    package (PkgWatt) PL1 target: 0.125 W .. cTDP Level 2
#                         (default: Nominal TDP, e.g. 25 W)
#          --sysWatt W    psys/platform (SysWatt) cap (default: same as pkgWatt)
#
# Usage:
#   sudo ./set_power_profile.sh --profile <name> [--sysWatt W] [--burstRatio R]
#                                                [--pl1Tau S] [--dry-run]
#   sudo ./set_power_profile.sh [--pkgWatt W] [--sysWatt W] [--burstRatio R]
#                               [--pl1Tau S] [--dry-run]
#   ./set_power_profile.sh --list
#
# Tuned for Intel Panther Lake (Core Ultra, family 6 model 204). The Config-TDP
# levels (Nominal / Level 1 / Level 2) are read from the CPU's RAPL MSRs at
# runtime; the requested target is clamped to [0.125 W, Level 2] and snapped to
# the RAPL power-unit granularity (0.125 W here), where Level 2 is the silicon's
# maximum configurable TDP (e.g. 65 W on Panther Lake). EPP/EPB are interpolated
# from a 5 W-spaced tuning table. If the MSRs are unavailable it falls back to
# the Panther Lake defaults (Nominal 25 W, Level 1 15 W, Level 2 65 W).
#
# What it does:
#   * CPUs : generates a single-state intel_lpmd config with EPP/EPB interpolated
#            for the target wattage and then biased toward performance by the
#            PL2/PL1 ratio, installs it, restarts the daemon and puts it in AUTO
#            so the state is applied to all CPUs.
#   * GPU  : the RAPL "package" domain includes the integrated GPU (uncore), so
#            the package cap below bounds CPU + iGPU power together.
#   * NPU  : capped too if a modern NPU exposes a RAPL/powercap domain; legacy
#            GNA accelerators have no power domain and are left untouched.
#   * Cap  : sets RAPL PL1 (long term) = watts and PL2 (short term) = watts *
#            ratio on the package (and psys, if writable), then enables
#            enforcement. The default ratio 1.25 gives Intel's typical turbo
#            headroom (PL2 = 1.25 x PL1); set ratio 1.0 for a strict cap where
#            PL1 = PL2, or higher to let brief bursts reach the cTDP Level 2
#            ceiling while sustained stays at PL1.
#            Package/psys limits are written via the RAPL MSRs (0x610/0x65C)
#            because the powercap sysfs interface clamps to the firmware max
#            (e.g. a 25W cTDP); this needs the 'msr' module + msr-tools (wrmsr).
#
# Note: the RAPL cap is applied at runtime and does not persist across reboot.

set -euo pipefail

# ---- Configuration ---------------------------------------------------------
# Directory the installed intel_lpmd daemon reads its config from. Override with
# LPMD_CONF_DIR=/etc/intel_lpmd if your build uses that prefix.
LPMD_CONF_DIR="${LPMD_CONF_DIR:-/usr/local/etc/intel_lpmd}"
LPMD_CONF_FILE="$LPMD_CONF_DIR/intel_lpmd_config.xml"
LPMD_CONTROL="${LPMD_CONTROL:-intel_lpmd_control}"

# ---- Profile table (name -> PkgWatt, default burst ratio) -----------------
# Ordered lowest-to-highest package budget. Profiles are expressed as PkgWatt
# (CPU package) targets because the package cap is enforceable on every platform;
# the default burst ratio for each profile can be overridden with --burstRatio.
# The special value "max" for MaxPerformance is resolved at runtime to the
# silicon's cTDP Level 2 (the maximum wattage the platform supports), read from
# the RAPL MSRs.
PROFILE_NAMES=(LowPower BalancedLow BalancedHigh Performance MaxPerformance)
PROFILE_WATTS=(10 15 20 25 max)
PROFILE_RATIOS=(1.25 1.25 1.18 1.19 1.18)

# ---- Argument handling -----------------------------------------------------
usage() {
	cat <<EOF
Usage: $0 --profile <name> [--sysWatt W] [--burstRatio R] [--pl1Tau S] [--dry-run]
       $0 [--pkgWatt W] [--sysWatt W] [--burstRatio R] [--pl1Tau S] [--dry-run]
       $0 --list
       $0 --help

Set an intel_lpmd power profile and enforce it with a hard RAPL power cap
(CPU + iGPU), either from a named platform profile or from explicit
PkgWatt/SysWatt targets. The Config-TDP levels are read from the CPU's RAPL MSRs
at runtime.

Profile mode:
  --profile NAME  One of the named profiles (case-insensitive), each a PkgWatt
                  (CPU package) budget — enforceable on every platform:
                    LowPower        10 W    (default burst ratio 1.25)
                    BalancedLow     15 W    (default burst ratio 1.25)
                    BalancedHigh    20 W    (default burst ratio 1.18)
                    Performance     25 W    (default burst ratio 1.19)
                    MaxPerformance  max     (platform cTDP Level 2; default burst ratio 1.18)
                    Custom                  (no preset; use the explicit-target
                                             flags below to set any values)
                  A profile may be combined with --sysWatt to override the
                  whole-platform (SysWatt) cap on psys-capable silicon; without
                  it the SysWatt cap tracks the profile PkgWatt.

Explicit-target mode:
  --pkgWatt W     Package (PkgWatt) PL1 sustained target in watts. Default:
                  Nominal TDP (the CPU's rated sustained power, e.g. 25 W).
                  Clamped to [0.125, cTDP Level 2] and snapped to the RAPL
                  power-unit granularity (0.125 W). Level 2 = max configurable
                  TDP (e.g. 65 W on Panther Lake).
  --sysWatt W     psys/platform (turbostat SysWatt) cap in watts, applied only
                  on platforms that expose the psys domain (ignored otherwise).
                  Valid with a --profile or with --pkgWatt. Default: same as the
                  PkgWatt target. Uses --burstRatio for its PL2. Set higher than
                  PkgWatt (or to the max) to let the package limit dominate.

Common options:
  --burstRatio R  burst ratio (>= 1.0). PL2 = pkgWatt * R, clamped to cTDP
                  Level 2. A higher ratio also biases EPP/EPB toward performance.
                  In profile mode, overrides the profile's default ratio; in
                  explicit-target mode the default is 1.25.
  --pl1Tau S      PL1 time window (tau) in seconds (default 28, Intel's typical
                  PL1 window). Programmed via the MSR Y/Z fields and the powercap
                  constraint_0_time_window_us.
  --dry-run       Resolve and print the plan (and the effective explicit-target
                  command line) without applying anything.
  --list          List the available profiles and exit.
  -h, --help      Show this help and exit.

Environment:
  LPMD_CONF_DIR   intel_lpmd config directory (default /usr/local/etc/intel_lpmd).
  LPMD_CONTROL    intel_lpmd control command (default intel_lpmd_control).

Examples:
  sudo $0 --profile Performance
  sudo $0 --profile MaxPerformance --burstRatio 1.4
  $0 --profile Performance --dry-run
  sudo $0 --profile Performance --sysWatt 35       # profile PkgWatt + explicit SysWatt cap
  sudo $0 --profile Custom --pkgWatt 30 --sysWatt 40 --burstRatio 1.3
  sudo $0 --pkgWatt 30                             # PkgWatt 30 W (ratio 1.25, tau 28 s)
  sudo $0 --pkgWatt 30 --burstRatio 1.0            # strict cap: PL1 = PL2 = 30 W
  sudo $0 --pkgWatt 30 --sysWatt 65 --burstRatio 1.25 --pl1Tau 28

Note: needs root (re-runs itself with sudo) and the 'msr' module + msr-tools.
The RAPL cap is applied at runtime and does not persist across reboot.
EOF
}

list_profiles() {
	echo "Available power profiles:"
	local i w wdisp
	for i in "${!PROFILE_NAMES[@]}"; do
		w="${PROFILE_WATTS[$i]}"
		if [[ "$w" == "max" ]]; then
			wdisp="platform max"
		else
			wdisp="${w}W"
		fi
		printf "  %-20s %-14s (PkgWatt)   default burst ratio %s\n" \
			"${PROFILE_NAMES[$i]}" "$wdisp" "${PROFILE_RATIOS[$i]}"
	done
	printf "  %-20s %s\n" "Custom" "no preset; pass --pkgWatt/--sysWatt/--burstRatio/--pl1Tau explicitly"
}

# profile_index <name>: echo the array index for a case-insensitive profile
# name, or return non-zero if the name is unknown.
profile_index() {
	local want i
	want="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
	for i in "${!PROFILE_NAMES[@]}"; do
		if [[ "$(printf '%s' "${PROFILE_NAMES[$i]}" | tr '[:upper:]' '[:lower:]')" == "$want" ]]; then
			echo "$i"
			return 0
		fi
	done
	return 1
}

# Defaults (Intel out-of-box): pkgWatt = Nominal TDP (resolved after the MSR
# read below), burstRatio 1.25, pl1Tau 28 s, sysWatt = pkgWatt.
PROFILE=""
WATTS=""
RATIO="1.25"
RATIO_SET=0
TAU_S="28"
PSYS_REQ=""
DRY_RUN=0

# Preserve the original command line before the parse loop consumes it with
# 'shift'. The sudo self-elevation below re-execs the script and must forward
# these; using "$@" after parsing would pass an empty argument list, silently
# dropping --profile/--pkgWatt/etc. and falling back to the Nominal TDP default.
ORIG_ARGS=("$@")

while [[ $# -gt 0 ]]; do
	case "$1" in
		-h|--help) usage; exit 0 ;;
		--list) list_profiles; exit 0 ;;
		--dry-run) DRY_RUN=1; shift ;;
		--profile|--pkgWatt|--sysWatt|--burstRatio|--pl1Tau)
			if [[ $# -lt 2 ]]; then
				echo "Error: $1 requires a value" >&2
				exit 1
			fi
			case "$1" in
				--profile)    PROFILE="$2" ;;
				--pkgWatt)    WATTS="$2" ;;
				--sysWatt)    PSYS_REQ="$2" ;;
				--burstRatio) RATIO="$2"; RATIO_SET=1 ;;
				--pl1Tau)     TAU_S="$2" ;;
			esac
			shift 2 ;;
		--profile=*)    PROFILE="${1#*=}";    shift ;;
		--pkgWatt=*)    WATTS="${1#*=}";      shift ;;
		--sysWatt=*)    PSYS_REQ="${1#*=}";   shift ;;
		--burstRatio=*) RATIO="${1#*=}"; RATIO_SET=1; shift ;;
		--pl1Tau=*)     TAU_S="${1#*=}";      shift ;;
		*) echo "Error: unknown option '$1'" >&2; usage >&2; exit 1 ;;
	esac
done

# ---- Resolve a named profile (if given) ------------------------------------
# A named preset sets the package (PkgWatt) target, so it cannot be combined
# with an explicit --pkgWatt. The PkgWatt budget and (unless overridden) the
# default burst ratio come from the profile table. On psys-capable silicon the
# whole-platform (SysWatt) limit tracks the same PkgWatt budget unless an
# explicit --sysWatt is supplied, in which case that value is used as the
# SysWatt cap. The special profile 'Custom' is the exception: it carries no
# preset and simply passes the explicit
# --pkgWatt/--sysWatt/--burstRatio/--pl1Tau flags straight through.
PROFILE_MODE=0
PROFILE_PKG_W=""
PROFILE_LC="$(printf '%s' "$PROFILE" | tr '[:upper:]' '[:lower:]')"
if [[ -n "$PROFILE" && "$PROFILE_LC" != "custom" ]]; then
	PROFILE_MODE=1
	if [[ -n "$WATTS" ]]; then
		echo "Error: --profile $PROFILE cannot be combined with --pkgWatt (the profile sets PkgWatt; use '--profile Custom' for an explicit package target)." >&2
		exit 1
	fi
	if ! PROFILE_IDX="$(profile_index "$PROFILE")"; then
		echo "Error: unknown profile '$PROFILE'." >&2
		list_profiles >&2
		exit 1
	fi
	PROFILE_PKG_W="${PROFILE_WATTS[$PROFILE_IDX]}"
	# Use the profile's default burst ratio unless the user supplied one.
	if [[ "$RATIO_SET" -eq 0 ]]; then
		RATIO="${PROFILE_RATIOS[$PROFILE_IDX]}"
	fi
fi

# 'Custom' is a pass-through: it is not a preset, so behave exactly like
# explicit-target mode and honour any --pkgWatt/--sysWatt/--burstRatio/--pl1Tau
# the user supplied (falling back to the same defaults as those flags).
if [[ "$PROFILE_LC" == "custom" ]]; then
	echo "Profile          : Custom (explicit targets)"
fi

# Validate the supplied values.
if [[ -n "$WATTS" ]] && ! [[ "$WATTS" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
	echo "Error: '--pkgWatt' must be a positive number (got '$WATTS')" >&2
	exit 1
fi
if ! [[ "$RATIO" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
	echo "Error: '--burstRatio' must be a positive number (got '$RATIO')" >&2
	exit 1
fi
if [[ -n "$TAU_S" ]] && ! [[ "$TAU_S" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
	echo "Error: '--pl1Tau' must be a positive number of seconds (got '$TAU_S')" >&2
	exit 1
fi
if [[ -n "$PSYS_REQ" ]] && ! [[ "$PSYS_REQ" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
	echo "Error: '--sysWatt' must be a positive number (got '$PSYS_REQ')" >&2
	exit 1
fi

# ---- Root handling ---------------------------------------------------------
# MSR probing and programming need root. A dry run stays read-only and does not
# require elevation.
if [[ "$DRY_RUN" -eq 0 && $EUID -ne 0 ]]; then
	echo "This script needs root; re-running with sudo..." >&2
	exec sudo -E LPMD_CONF_DIR="$LPMD_CONF_DIR" LPMD_CONTROL="$LPMD_CONTROL" "$0" "${ORIG_ARGS[@]}"
fi

# ---- Detect Config-TDP levels from the CPU (Nominal / Level1 / Level2) ------
# Read the platform's actual cTDP thermal-spec-power values from the RAPL MSRs
# instead of hardcoding them, so the envelope tracks the silicon:
#   Nominal : MSR_PKG_POWER_INFO   (0x614) Thermal Spec Power [14:0]
#   Level 1 : MSR_CONFIG_TDP_LEVEL1 (0x649) PKG_TDP [14:0]
#   Level 2 : MSR_CONFIG_TDP_LEVEL2 (0x64A) PKG_TDP [14:0]  (= max configurable TDP)
# Requires the 'msr' module + msr-tools; falls back to Panther Lake defaults
# (Nominal 25W, Level1 15W, Level2 65W) when the MSRs are unavailable.
HAVE_MSR=0
PU_BITS=0
TU_BITS=0
if command -v rdmsr >/dev/null 2>&1 && command -v wrmsr >/dev/null 2>&1; then
	modprobe msr 2>/dev/null || true
	if pu_raw=$(rdmsr -0 0x606 2>/dev/null); then
		HAVE_MSR=1
		# MSR_RAPL_POWER_UNIT (0x606) bits 3:0 = power unit exponent; watt = 1/2^bits.
		PU_BITS=$(( 0x$pu_raw & 0xF ))
		# bits 19:16 = time unit exponent; second = 1/2^bits.
		TU_BITS=$(( (0x$pu_raw >> 16) & 0xF ))
	fi
fi

# msr_tdp_w <reg>: print the PKG_TDP / thermal-spec field [14:0] of <reg> in
# whole watts, or nothing if the MSR can't be read.
msr_tdp_w() {
	local reg="$1" v
	[[ "$HAVE_MSR" -eq 1 ]] || return 0
	v=$(rdmsr -0 "$reg" 2>/dev/null) || return 0
	awk -v r=$(( 0x$v & 0x7FFF )) -v b="$PU_BITS" 'BEGIN{ printf "%d", r/(2^b) + 0.5 }'
}

NOMINAL_TDP=25
LEVEL1_TDP=15
MAX_TDP=65
if [[ "$HAVE_MSR" -eq 1 ]]; then
	v=$(msr_tdp_w 0x614); [[ -n "$v" && "$v" -gt 0 ]] && NOMINAL_TDP="$v"
	v=$(msr_tdp_w 0x649); [[ -n "$v" && "$v" -gt 0 ]] && LEVEL1_TDP="$v"
	v=$(msr_tdp_w 0x64A); [[ -n "$v" && "$v" -gt 0 ]] && MAX_TDP="$v"
fi
echo "Config-TDP levels: Nominal=${NOMINAL_TDP}W  Level1=${LEVEL1_TDP}W  Level2(max)=${MAX_TDP}W"

# ---- Profile mode: set the PkgWatt target and derive any SysWatt cap --------
# When a named profile was selected, the profile value is the PkgWatt (package)
# target, which is enforced on every platform. On psys-capable silicon the
# whole-platform (SysWatt) limit tracks the same PkgWatt budget:
#   * psys supported   -> cap PkgWatt AND cap SysWatt at the PkgWatt budget.
#   * psys unsupported -> cap PkgWatt only (SysWatt cannot be capped here).
if [[ "$PROFILE_MODE" -eq 1 ]]; then
	# Resolve the MaxPerformance "max" sentinel to the platform maximum, i.e.
	# the cTDP Level 2 wattage read from the MSRs above (or the documented
	# fallback when the MSRs are unavailable).
	if [[ "$PROFILE_PKG_W" == "max" ]]; then
		PROFILE_PKG_W="$MAX_TDP"
	fi

	# psys_supported: true when the kernel RAPL driver registered a "psys"
	# powercap domain, or MSR_PLATFORM_POWER_LIMIT (0x65C) reads non-zero.
	psys_supported() {
		local d v
		for d in /sys/class/powercap/intel-rapl:* ; do
			[[ -r "$d/name" ]] || continue
			if [[ "$(cat "$d/name" 2>/dev/null)" == "psys" ]]; then
				return 0
			fi
		done
		if [[ "$HAVE_MSR" -eq 1 ]]; then
			if v=$(rdmsr -0 0x65C 2>/dev/null); then
				[[ "$(( 0x$v ))" -ne 0 ]] && return 0
			fi
		fi
		return 1
	}

	SYS_SUPPORTED=0
	SYS_METHOD="unsupported"
	if psys_supported; then
		SYS_SUPPORTED=1
		SYS_METHOD="psys RAPL domain / MSR 0x65C"
	elif [[ "$HAVE_MSR" -eq 0 ]]; then
		SYS_METHOD="undetermined (msr-tools/msr module unavailable)"
	fi

	# PkgWatt = the profile target (always enforced). On psys-capable silicon
	# the whole-platform (SysWatt) limit tracks the same PkgWatt budget unless
	# the user passed an explicit --sysWatt, which is then honoured as the
	# SysWatt cap (PSYS_REQ is left unset otherwise so it defaults to PkgWatt).
	WATTS="$PROFILE_PKG_W"

	echo "Profile          : $PROFILE"
	echo "PkgWatt target   : ${WATTS}W"
	echo "Burst ratio      : ${RATIO}"
	if [[ "$SYS_SUPPORTED" -eq 1 ]]; then
		if [[ -n "$PSYS_REQ" ]]; then
			echo "SysWatt support  : yes ($SYS_METHOD) -> SysWatt cap ${PSYS_REQ}W (from --sysWatt)"
		else
			echo "SysWatt support  : yes ($SYS_METHOD) -> SysWatt tracks PkgWatt (${WATTS}W)"
		fi
	else
		if [[ -n "$PSYS_REQ" ]]; then
			echo "SysWatt support  : no ($SYS_METHOD) -> --sysWatt ${PSYS_REQ}W ignored (no psys domain); capping PkgWatt only at ${WATTS}W"
		else
			echo "SysWatt support  : no ($SYS_METHOD) -> capping PkgWatt only at ${WATTS}W"
		fi
	fi
fi

# Default target = Nominal TDP (the CPU's rated sustained power) when neither a
# <pkgWatt> argument nor a profile supplied one.
if [[ -z "$WATTS" ]]; then
	WATTS="$NOMINAL_TDP"
	echo "No target given; defaulting PL1 to Nominal TDP ${WATTS}W."
fi

# ---- Clamp to [0.125, Level2] and snap to RAPL power-unit granularity -------
# Support any target from one RAPL power unit (0.125 W here) up to Level 2, the
# max configurable TDP read above. STEP is the hardware resolution (1/2^PU_BITS
# W, or 0.125 W if the MSRs are unavailable); the request is snapped to it.
STEP=$(awk -v b="$PU_BITS" 'BEGIN{ printf "%g", (b>0)? 1/(2^b) : 0.125 }')
REQ="$WATTS"
WATTS=$(awk -v w="$WATTS" -v mx="$MAX_TDP" -v s="$STEP" 'BEGIN{
	if(w<s)w=s; if(w>mx)w=mx;
	printf "%g", int(w/s + 0.5) * s
}')
if awk "BEGIN{exit !($REQ != $WATTS)}"; then
	echo "Note: request ${REQ}W adjusted to ${WATTS}W (valid range ${STEP}-${MAX_TDP} W)." >&2
fi

# ---- Derive PL1/PL2 from the target and the PL2/PL1 ratio -------------------
# PL1 (sustained) = snapped target; PL2 (burst) = PL1 * ratio, clamped to the
# cTDP Level 2 ceiling. The ratio is floored at 1.0 (burst cannot be below
# sustained); RATIO_EFF is what is actually achieved after the ceiling clamp.
PL1_W="$WATTS"
if awk "BEGIN{exit !($RATIO < 1)}"; then
	echo "Note: PL2/PL1 ratio ${RATIO} raised to 1.00 (burst cannot be below sustained)." >&2
	RATIO=1.0
fi
PL2_W=$(awk -v p="$PL1_W" -v r="$RATIO" -v mx="$MAX_TDP" -v s="$STEP" 'BEGIN{ v=p*r; if(v>mx)v=mx; printf "%g", int(v/s + 0.5) * s }')
RATIO_EFF=$(awk -v a="$PL2_W" -v b="$PL1_W" 'BEGIN{ printf "%.2f", a/b }')
if awk "BEGIN{exit !(($PL1_W * $RATIO) > $MAX_TDP)}"; then
	echo "Note: PL2 capped at ${MAX_TDP}W (cTDP Level 2); effective ratio ${RATIO_EFF}." >&2
fi

# ---- Derive the psys/platform (SysWatt) target -----------------------------
# Defaults to the package target so behaviour is unchanged unless a separate
# [psys_watts] was supplied. Same clamping/snapping as the package; PL2 uses the
# same burst ratio. This lets PkgWatt and SysWatt be capped independently.
if [[ -z "$PSYS_REQ" ]]; then
	PSYS_W="$PL1_W"
else
	PSYS_W=$(awk -v w="$PSYS_REQ" -v mx="$MAX_TDP" -v s="$STEP" 'BEGIN{ if(w<s)w=s; if(w>mx)w=mx; printf "%g", int(w/s + 0.5) * s }')
fi
PSYS_PL2_W=$(awk -v p="$PSYS_W" -v r="$RATIO" -v mx="$MAX_TDP" -v s="$STEP" 'BEGIN{ v=p*r; if(v>mx)v=mx; printf "%g", int(v/s + 0.5) * s }')
if [[ -n "$PSYS_REQ" ]] && awk "BEGIN{exit !($PSYS_REQ > $MAX_TDP)}"; then
	echo "Note: psys/SysWatt request ${PSYS_REQ}W clamped to ${PSYS_W}W (cTDP Level 2)." >&2
fi

# ---- Encode the PL1 time window (tau) if requested -------------------------
# When a PL1 tau is given, prepare it for both interfaces:
#   MSR  : PKG/PLATFORM_POWER_LIMIT bits [23:17] = Y[21:17] + Z[23:22], where
#          tau = 2^Y * (1 + Z/4) * time_unit and time_unit = 1/2^TU_BITS s.
#   sysfs: constraint_0_time_window_us in microseconds.
# Omitted => TAU_SET=0 and the existing (firmware/daemon) window is preserved.
TAU_SET=0
TAU_FIELD=0
TAU_US=0
TAU_Y=0
TAU_Z=0
TAU_EFF=""
if [[ -n "$TAU_S" ]]; then
	TAU_SET=1
	TAU_US=$(awk -v t="$TAU_S" 'BEGIN{ printf "%d", t*1000000 }')
	if [[ "$HAVE_MSR" -eq 1 ]]; then
		read -r TAU_Y TAU_Z <<EOF
$(awk -v t="$TAU_S" -v tu="$TU_BITS" 'BEGIN{
	unit = 1.0/(2^tu);
	ratio = t/unit; if (ratio < 1) ratio = 1;
	y = int(log(ratio)/log(2)); if (y < 0) y = 0; if (y > 31) y = 31;
	z = int(((ratio/(2^y)) - 1) * 4 + 0.5); if (z < 0) z = 0; if (z > 3) z = 3;
	print y, z;
}')
EOF
		TAU_FIELD=$(( (TAU_Z << 5) | TAU_Y ))
		TAU_EFF=$(awk -v y="$TAU_Y" -v z="$TAU_Z" -v tu="$TU_BITS" 'BEGIN{ printf "%.4g", (2^y)*(1+z/4)/(2^tu) }')
		echo "PL1 time window: requested ${TAU_S}s -> encoded ~${TAU_EFF}s (Y=${TAU_Y} Z=${TAU_Z})"
	else
		echo "PL1 time window: ${TAU_S}s (${TAU_US}us) via powercap sysfs (no MSR)"
	fi
fi

# ---- Panther Lake tuning table (sampled every 5 W, interpolated) -----------
# Tuned for Intel Core Ultra / Panther Lake (F6_M204). Columns per sample:
#   EPP         : 0 = max performance .. 255 = max power save
#   EPB         : 0 = performance      .. 15  = power save
#   ITMTState   : 1 = enable turbo/preferred-core bias, 0 = disable, -1 = leave
#   ActiveCPUs  : cpu set the daemon confines work to ('all' = no restriction)
# Low samples fold work onto the low-index (efficient) cores and bias hard
# toward efficiency; from 25 W up all cores are freed and the bias ramps to
# performance. For an arbitrary target the continuous EPP/EPB are linearly
# interpolated between the two bracketing 5 W samples, while the discrete
# ITMTState/ActiveCPUs take the nearest sample's value. Below the first sample
# (5 W) or above the last, the endpoint sample is used.
read -r EPP EPB ITMT ACTIVE_CPUS <<EOF
$(awk -v w="$WATTS" 'BEGIN{
	n=split("5 10 15 20 25 30 35 40 45 50 55 60 65", W, " ");
	split("255 224 192 160 128 112 96 80 64 48 32 16 0", E, " ");
	split("15 12 10 8 6 5 4 3 2 1 1 0 0", B, " ");
	split("0 0 0 0 -1 -1 -1 1 1 1 1 1 1", T, " ");
	split("0-1 0-3 0-5 0-7 all all all all all all all all all", C, " ");
	x=w; if(x<W[1])x=W[1]; if(x>W[n])x=W[n];
	lo=1; for (i=1;i<=n;i++) if (W[i]<=x) lo=i;
	hi=lo; if (lo<n && W[lo]!=x) hi=lo+1;
	f=(hi==lo)?0:(x-W[lo])/(W[hi]-W[lo]);
	epp=E[lo]+f*(E[hi]-E[lo]);
	epb=B[lo]+f*(B[hi]-B[lo]);
	near=(f<0.5)?lo:hi;
	printf "%d %d %d %s", int(epp+0.5), int(epb+0.5), T[near], C[near];
}')
EOF

# ---- Bias EPP/EPB by the PL2/PL1 ratio -------------------------------------
# The table gives base EPP/EPB for the PL1 wattage. A larger burst ratio means
# more short-term headroom, so shift the hints toward performance (lower values)
# by dividing them by the effective ratio: at ratio 1.0 the table values are
# used unchanged; higher ratios scale them down toward 0 (max performance).
# Results are clamped to their valid ranges (EPP 0-255, EPB 0-15).
EPP=$(awk -v e="$EPP" -v r="$RATIO_EFF" 'BEGIN{ v=int(e/r + 0.5); if(v<0)v=0; if(v>255)v=255; print v }')
EPB=$(awk -v b="$EPB" -v r="$RATIO_EFF" 'BEGIN{ v=int(b/r + 0.5); if(v<0)v=0; if(v>15)v=15; print v }')

NCPU=$(nproc)

echo "Target: PL1=${PL1_W}W PL2=${PL2_W}W (ratio ${RATIO_EFF})  ->  EPP=$EPP EPB=$EPB ITMT=$ITMT ActiveCPUs=$ACTIVE_CPUS"
if [[ "$PSYS_W" != "$PL1_W" ]]; then
	echo "psys (SysWatt) target: PL1=${PSYS_W}W PL2=${PSYS_PL2_W}W"
fi

# ---- Dry run: print the resolved plan + effective command line and stop -----
if [[ "$DRY_RUN" -eq 1 ]]; then
	echo
	echo "Dry run - no changes applied."
	echo "Effective command line (resolved explicit-target equivalent):"
	echo "  sudo $0 --pkgWatt ${WATTS} --sysWatt ${PSYS_W} --burstRatio ${RATIO} --pl1Tau ${TAU_S}"
	exit 0
fi

# ---- Generate and install the intel_lpmd config ----------------------------
mkdir -p "$LPMD_CONF_DIR"
tmp_cfg="$(mktemp)"
cat > "$tmp_cfg" <<EOF
<?xml version="1.0"?>
<!-- Auto-generated by set_power_profile.sh for ~${WATTS}W. Pinned single state. -->
<Configuration>
	<lp_mode_cpus></lp_mode_cpus>
	<lp_mode_epp>-1</lp_mode_epp>
	<Mode>0</Mode>
	<PerformanceDef>0</PerformanceDef>
	<BalancedDef>0</BalancedDef>
	<PowersaverDef>0</PowersaverDef>
	<HfiLpmEnable>0</HfiLpmEnable>
	<HfiSuvEnable>0</HfiSuvEnable>
	<util_entry_threshold></util_entry_threshold>
	<util_exit_threshold></util_exit_threshold>
	<EntryDelayMS>0</EntryDelayMS>
	<ExitDelayMS>0</ExitDelayMS>
	<EntryHystMS>0</EntryHystMS>
	<ExitHystMS>0</ExitHystMS>
	<IgnoreITMT>0</IgnoreITMT>
	<States>
		<CPUFamily> * </CPUFamily>
		<CPUModel> * </CPUModel>
		<CPUConfig> * </CPUConfig>
		<State>
			<ID> 1 </ID>
			<Name> POWER_${WATTS}W </Name>
			<EntrySystemLoadThres></EntrySystemLoadThres>
			<EnterCPULoadThres></EnterCPULoadThres>
			<EPP> $EPP </EPP>
			<EPB> $EPB </EPB>
			<ITMTState> $ITMT </ITMTState>
			<IRQMigrate> -1 </IRQMigrate>
			<ActiveCPUs> $ACTIVE_CPUS </ActiveCPUs>
			<MinPollInterval> 1000 </MinPollInterval>
			<PollIntervalIncrement> 500 </PollIntervalIncrement>
			<MaxPollInterval> 2000 </MaxPollInterval>
		</State>
	</States>
</Configuration>
EOF

install -m 644 "$tmp_cfg" "$LPMD_CONF_FILE"

# The daemon (match_config_file) prefers a model-specific config over the
# generic one, in this order of precedence:
#   intel_lpmd_config_F<family>_M<model>_T<tdp>.xml   (highest)
#   intel_lpmd_config_F<family>_M<model>.xml
#   intel_lpmd_config.xml                             (generic, written above)
# On platforms that ship a model-specific file (e.g. Panther Lake = F6_M204),
# the generic file we just wrote is ignored. So overwrite any matching
# model/TDP-specific files too (keeping a one-time .orig backup) to guarantee
# our profile is the one the daemon loads.
CPU_FAMILY=$(awk -F: '{k=$1; gsub(/[ \t]/, "", k); if (k=="cpufamily") {v=$2; gsub(/ /,"",v); print v; exit}}' /proc/cpuinfo)
CPU_MODEL=$(awk -F: '{k=$1; gsub(/[ \t]/, "", k); if (k=="model") {v=$2; gsub(/ /,"",v); print v; exit}}' /proc/cpuinfo)
if [[ -n "$CPU_FAMILY" && -n "$CPU_MODEL" ]]; then
	shopt -s nullglob
	for f in "$LPMD_CONF_DIR/intel_lpmd_config_F${CPU_FAMILY}_M${CPU_MODEL}.xml" \
		 "$LPMD_CONF_DIR/intel_lpmd_config_F${CPU_FAMILY}_M${CPU_MODEL}_T"*.xml; do
		[[ -e "$f" ]] || continue
		[[ -e "$f.orig" ]] || cp -a "$f" "$f.orig"
		install -m 644 "$tmp_cfg" "$f"
		echo "Overrode model-specific config $f (original saved as $f.orig)"
	done
	shopt -u nullglob
fi
rm -f "$tmp_cfg"

# ---- Restart daemon and put it in AUTO so the state is applied -------------
if systemctl list-unit-files intel_lpmd.service >/dev/null 2>&1; then
	# Reload systemd's view of unit files first. Rewriting the intel_lpmd
	# config on disk makes systemd flag the unit as changed and emit
	# "unit file ... changed on disk. Run 'systemctl daemon-reload'"; doing the
	# reload here suppresses that warning before we touch the service.
	systemctl daemon-reload 2>/dev/null || true
	# Clear any prior failed/rate-limited state so frequent re-runs don't trip
	# systemd's start limiter ("start-limit-hit" / "Start request repeated too
	# quickly"), which would otherwise leave the service failed.
	systemctl reset-failed intel_lpmd.service 2>/dev/null || true
	if ! systemctl restart intel_lpmd.service; then
		echo "Warning: 'systemctl restart intel_lpmd' failed; run 'systemctl reset-failed intel_lpmd' and retry." >&2
	fi
	sleep 2
	"$LPMD_CONTROL" AUTO >/dev/null 2>&1 || true
	sleep 1
else
	echo "Warning: intel_lpmd.service not found; config installed but daemon not restarted." >&2
fi

# ---- Apply hard RAPL cap on package (CPU+iGPU), psys and any NPU domain -----
# PL1 (long term) = PL2 (short term) = target wattage, so bursts stay within the
# same budget as sustained load.
#
# NOTE: the powercap *sysfs* interface clamps package/psys writes to the
# firmware-advertised max (constraint_0_max_power_uw, e.g. a 25W cTDP), so it
# cannot raise the package above that ceiling. We therefore program PL1/PL2
# straight into the RAPL MSRs for package/psys (MSR 0x610 / 0x65C), which the
# PCU honours up to the silicon limit. sysfs is still used for the MMIO package
# mirror and for NPU/VPU domains that have no equivalent MSR.
pl1_uw=$(awk "BEGIN{printf \"%d\", $PL1_W*1000000}")
pl2_uw=$(awk "BEGIN{printf \"%d\", $PL2_W*1000000}")
psys_pl1_uw=$(awk "BEGIN{printf \"%d\", $PSYS_W*1000000}")
psys_pl2_uw=$(awk "BEGIN{printf \"%d\", $PSYS_PL2_W*1000000}")

# --- MSR-based PL1/PL2 programming (bypasses the sysfs max clamp) -----------
# HAVE_MSR/PU_BITS were detected above; derive PL1/PL2 in RAPL power units for
# the package and (separately) the psys/platform domain.
MSR_UNITS=0
MSR_UNITS2=0
PSYS_MSR_UNITS=0
PSYS_MSR_UNITS2=0
if [[ "$HAVE_MSR" -eq 1 ]]; then
	MSR_UNITS=$(awk "BEGIN{printf \"%d\", $PL1_W * (2 ^ $PU_BITS) + 0.5}")
	MSR_UNITS2=$(awk "BEGIN{printf \"%d\", $PL2_W * (2 ^ $PU_BITS) + 0.5}")
	PSYS_MSR_UNITS=$(awk "BEGIN{printf \"%d\", $PSYS_W * (2 ^ $PU_BITS) + 0.5}")
	PSYS_MSR_UNITS2=$(awk "BEGIN{printf \"%d\", $PSYS_PL2_W * (2 ^ $PU_BITS) + 0.5}")
fi

# set_msr_pl <msr> <name>: set PL1 (bits14:0) and PL2 (bits46:32) to the target
# PL1/PL2 watts, enable both limits (bits 15 & 47), and set the PL1 time window
# (bits 23:17) when a tau was requested (otherwise preserve it); clamp bits are
# preserved. Refuses if
# the register is locked (bit 63). Writes then verifies, retrying a few times
# because a just-restarted intel_lpmd daemon can transiently reassert a lower
# package limit right after AUTO. If the firmware still clamps below the target
# (e.g. cTDP-Nominal 25W ceiling) it reports the effective value and how to lift
# it. Returns non-zero only on a hard failure (missing MSR / lock).
set_msr_pl() {
	local reg="$1" nm="$2" u="$3" u2="$4" capw="${5:-0}" o n a p1 p2 w1 w2 reqw
	[[ "$HAVE_MSR" -eq 1 && "$u" -gt 0 ]] || return 1
	o=$(rdmsr -0 "$reg" 2>/dev/null) || return 1
	if (( (0x$o >> 63) & 1 )); then
		echo "  $nm ($reg): MSR locked (bit63) - cannot override via MSR" >&2
		return 1
	fi
	n=$(( (0x$o & ~0x7FFF & ~((0x7FFF)<<32)) | u | (u2<<32) | (1<<15) | (1<<47) ))
	# Optionally overwrite the PL1 time-window field (bits 23:17) with tau.
	if [[ "$TAU_SET" -eq 1 ]]; then
		n=$(( (n & ~((0x7F)<<17)) | (TAU_FIELD<<17) ))
	fi
	n=$(printf '%016x' "$n")
	p1=0
	for _ in 1 2 3; do
		wrmsr -a "$reg" "0x$n" 2>/dev/null || return 1
		sleep 0.3
		a=$(rdmsr -0 "$reg" 2>/dev/null) || return 1
		p1=$(( 0x$a & 0x7FFF ))
		if [[ "$p1" -ge "$u" ]]; then break; fi
	done
	p2=$(( (0x$a >> 32) & 0x7FFF ))
	w1=$(awk "BEGIN{print $p1/(2^$PU_BITS)}")
	w2=$(awk "BEGIN{print $p2/(2^$PU_BITS)}")
	reqw=$(awk "BEGIN{print $u/(2^$PU_BITS)}")
	if [[ "$p1" -lt "$u" ]]; then
		echo "  $nm ($reg): requested ${reqw}W but firmware clamped PL1 to ${w1}W"
		echo "    -> set Config TDP Level 2 in BIOS to raise the package above ${w1}W"
	elif awk "BEGIN{exit !($capw > 0 && $w1 > $capw)}"; then
		echo "  capped $nm ($reg via MSR) -> PL1 ${w1}W  PL2 ${w2}W (register only; firmware enforces ~${capw}W sustained)"
	else
		echo "  capped $nm ($reg via MSR) -> PL1 ${w1}W  PL2 ${w2}W"
	fi
	return 0
}

apply_cap() {
	local dom="$1" nm="$2" a_pl1="$3" a_pl2="$4" applied=0
	for con in "$dom"/constraint_0_power_limit_uw "$dom"/constraint_1_power_limit_uw; do
		[[ -w "$con" ]] || continue
		# constraint_0 = long_term (PL1), constraint_1 = short_term (PL2)
		local val
		case "$con" in
			*constraint_1_power_limit_uw) val="$a_pl2" ;;
			*) val="$a_pl1" ;;
		esac
		# Clamp to the domain's max if one is advertised
		local maxf="${con%_power_limit_uw}_max_power_uw"
		if [[ -r "$maxf" ]]; then
			local mx; mx=$(cat "$maxf" 2>/dev/null || echo 0)
			if [[ "$mx" -gt 0 && "$val" -gt "$mx" ]]; then val="$mx"; fi
		fi
		if echo "$val" > "$con" 2>/dev/null; then applied=1; fi
	done
	# Set the PL1 time window (tau) if requested and writable.
	if [[ "$TAU_SET" -eq 1 && -w "$dom/constraint_0_time_window_us" ]]; then
		echo "$TAU_US" > "$dom/constraint_0_time_window_us" 2>/dev/null || true
	fi
	if [[ -w "$dom/enabled" ]]; then echo 1 > "$dom/enabled" 2>/dev/null || true; fi
	if [[ "$applied" -eq 1 ]]; then
		echo "  capped $nm -> PL1 $(cat "$dom"/constraint_0_power_limit_uw 2>/dev/null) uw, PL2 $(cat "$dom"/constraint_1_power_limit_uw 2>/dev/null) uw (enabled=$(cat "$dom"/enabled 2>/dev/null))"
	else
		echo "  $nm: not writable (skipped)"
	fi
}

# --- Config-TDP level selection --------------------------------------------
# The sustained package limit is bounded by the active cTDP level's thermal
# spec. For targets above the Nominal ceiling, select cTDP Level 2 (the max
# configurable TDP) so the higher PL1/PL2 can be honoured; at or below Nominal
# keep Nominal for the correct guaranteed frequency. The thresholds use the
# per-silicon values read above (Nominal/Level2), not hardcoded numbers. NOTE:
# on some silicon only a *BIOS* Config-TDP Level 2 fully raises the sustained
# firmware limit - the runtime switch here is best-effort and requires the cTDP
# control MSR to be unlocked.
if [[ "$HAVE_MSR" -eq 1 ]]; then
	ctdp=$(rdmsr -0 0x64B 2>/dev/null || echo 0)
	if (( (0x$ctdp >> 31) & 1 )); then
		echo "  cTDP control locked (fixed at level $((0x$ctdp & 0x3)); needs reboot/BIOS to change)"
	else
		if awk "BEGIN{exit !($WATTS > $NOMINAL_TDP)}"; then lvl=2; lbl="Level2/${MAX_TDP}W"; else lvl=0; lbl="Nominal/${NOMINAL_TDP}W"; fi
		if wrmsr -a 0x64B "$lvl" 2>/dev/null; then
			echo "  cTDP level -> $lvl ($lbl)"
		fi
	fi
fi

echo "Applying RAPL caps:"
# Advertised firmware ceiling for the package (used to annotate the MSR line when
# the register accepts more than the hardware will actually enforce).
PKG_MAX_W=0
for dom in /sys/class/powercap/intel-rapl:*; do
	[[ -r "$dom/name" ]] || continue
	[[ "$(cat "$dom/name")" == package-* ]] || continue
	mx=$(cat "$dom/constraint_0_max_power_uw" 2>/dev/null || echo 0)
	[[ "$mx" -gt 0 ]] && PKG_MAX_W=$(awk -v u="$mx" 'BEGIN{printf "%g", u/1000000}')
	break
done
for dom in /sys/class/powercap/intel-rapl:* /sys/class/powercap/intel-rapl-mmio:*; do
	[[ -r "$dom/name" ]] || continue
	nm=$(cat "$dom/name")
	case "$dom:$nm" in
		# Real (MSR) package domain: program PL via MSR 0x610, sysfs as fallback.
		*intel-rapl:*:package-*) set_msr_pl 0x610 "$nm" "$MSR_UNITS" "$MSR_UNITS2" "$PKG_MAX_W" || apply_cap "$dom" "$nm" "$pl1_uw" "$pl2_uw" ;;
		# psys / platform power limit lives in MSR 0x65C (its own SysWatt target).
		*:psys) set_msr_pl 0x65C "$nm" "$PSYS_MSR_UNITS" "$PSYS_MSR_UNITS2" || apply_cap "$dom" "$nm" "$psys_pl1_uw" "$psys_pl2_uw" ;;
		# MMIO package mirror has no MSR; use sysfs (bounded by its own max).
		*intel-rapl-mmio:*:package-*) apply_cap "$dom" "$nm" "$pl1_uw" "$pl2_uw" ;;
		# NPU/VPU accelerators: sysfs only.
		*:*npu*|*:*NPU*|*:*vpu*|*:*VPU*) apply_cap "$dom" "$nm" "$pl1_uw" "$pl2_uw" ;;
	esac
done

# ---- Verify the effective (enforced) package PL1 ---------------------------
# The MSR can accept a PL1 above the firmware/MMIO ceiling, but the PCU enforces
# the lower MMIO/cTDP limit for sustained power. Compute the actually-enforced
# value = min over the package domains of min(PL1, advertised max).
eff_uw=""
for dom in /sys/class/powercap/intel-rapl:* /sys/class/powercap/intel-rapl-mmio:*; do
	[[ -r "$dom/name" ]] || continue
	[[ "$(cat "$dom/name")" == package-* ]] || continue
	v=$(cat "$dom/constraint_0_power_limit_uw" 2>/dev/null || echo "")
	[[ -n "$v" ]] || continue
	mx=$(cat "$dom/constraint_0_max_power_uw" 2>/dev/null || echo 0)
	if [[ "$mx" -gt 0 && "$v" -gt "$mx" ]]; then v="$mx"; fi
	if [[ -z "$eff_uw" || "$v" -lt "$eff_uw" ]]; then eff_uw="$v"; fi
done
EFF_PL1_W="$PL1_W"
if [[ -n "$eff_uw" ]]; then
	EFF_PL1_W=$(awk -v u="$eff_uw" 'BEGIN{ printf "%g", u/1000000 }')
fi
pl1_disp="${EFF_PL1_W}W"
if awk "BEGIN{exit !($EFF_PL1_W < $PL1_W)}"; then
	pl1_disp="${EFF_PL1_W}W (requested ${PL1_W}W, clamped by firmware/cTDP ceiling)"
	echo "Note: package PL1 ${PL1_W}W exceeds the firmware ceiling; sustained power is enforced at ${EFF_PL1_W}W (raise it via BIOS Config-TDP Level 2)." >&2
fi
# Effective burst ratio reflects the ENFORCED PL1 (which may be clamped below the
# requested value while PL2 stays higher), so it can differ from the requested
# ratio shown on the Target line above.
EFF_RATIO=$(awk -v a="$PL2_W" -v b="$EFF_PL1_W" 'BEGIN{ if(b>0){printf "%.2f", a/b} else {printf "%s", "-"} }')

# ---- Report ----------------------------------------------------------------
echo "=== Result ==="
if command -v "$LPMD_CONTROL" >/dev/null 2>&1; then
	echo "  intel_lpmd state : $("$LPMD_CONTROL" STATUS 2>/dev/null || echo '?')"
fi
epp=$(for c in /sys/devices/system/cpu/cpu[0-9]*; do cat "$c/cpufreq/energy_performance_preference" 2>/dev/null; done | sort -u | paste -sd,)
epb=$(for c in /sys/devices/system/cpu/cpu[0-9]*; do cat "$c/power/energy_perf_bias" 2>/dev/null; done | sort -u | paste -sd,)
echo "  CPU tuning       : EPP=$epp EPB=$epb ITMT=$ITMT cpuset=$(cat /sys/fs/cgroup/system.slice/cpuset.cpus.effective 2>/dev/null) (${NCPU} CPUs)"
if [[ "$TAU_SET" -eq 1 ]]; then tau_note=", tau=${TAU_EFF:-$TAU_S}s"; else tau_note=""; fi
echo "  Package (PkgWatt): PL1=${pl1_disp}, PL2=${PL2_W}W (effective ratio ${EFF_RATIO})${tau_note}"
echo "  psys (SysWatt)   : PL1=${PSYS_W}W, PL2=${PSYS_PL2_W}W"
echo "Done. (runtime only; does not persist across reboot)"
