#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

set -Eeuo pipefail

if [[ ${METRICS_MANAGER_PACKAGE_TEST:-} != 1 || ! -f /.dockerenv || $EUID != 0 ]]; then
    echo "Run only as root in a disposable Docker container with METRICS_MANAGER_PACKAGE_TEST=1" >&2
    exit 1
fi
if [[ -d /run/systemd/system ]] || dpkg-query -W -f='${Status}' metrics-manager 2>/dev/null | grep -q 'install ok installed'; then
    echo "Refusing a running systemd instance or an existing Metrics Manager installation" >&2
    exit 1
fi

package=${1:?Usage: package-install-test.sh PACKAGE.deb fresh|upgrade}
scenario=${2:?Usage: package-install-test.sh PACKAGE.deb fresh|upgrade}
case "$scenario" in fresh | upgrade) ;; *) echo "Unknown scenario: $scenario" >&2; exit 1 ;; esac
version=$(dpkg-deb -f "$package" Version)
work=$(mktemp -d)
telegraf_pid=
cleanup() {
    if [[ -n $telegraf_pid ]]; then
        kill "$telegraf_pid" 2>/dev/null || true
        wait "$telegraf_pid" || true
    fi
}
trap cleanup EXIT
trap 'echo "Package test failed at line $LINENO" >&2' ERR

# Suppress distro daemon startup inside the test container, not on a real host.
printf '#!/bin/sh\nexit 101\n' > /usr/sbin/policy-rc.d
chmod 0755 /usr/sbin/policy-rc.d
# Minimal Ubuntu images otherwise discard documentation during unpacking.
printf 'path-include=/usr/share/doc/metrics-manager/*\n' > /etc/dpkg/dpkg.cfg.d/zz-metrics-manager-test-docs
apt-get update

if [[ $scenario == upgrade ]]; then
    # This fixture tests dpkg conffile semantics, not an older release's runtime.
    dpkg-deb --raw-extract "$package" "$work/baseline"
    sed -i "s/^Version: .*/Version: ${version}~upgrade-test/" "$work/baseline/DEBIAN/control"
    while IFS= read -r config; do
        printf '\n' >> "$work/baseline$config"
    done < "$work/baseline/DEBIAN/conffiles"
    (
        cd "$work/baseline"
        find etc usr -type f -print0 | sort -z | xargs -0 md5sum > DEBIAN/md5sums
    )
    dpkg-deb --build "$work/baseline" "$work/baseline.deb"
    apt-get install --yes --no-install-recommends "$work/baseline.deb" curl
    mkdir "$work/kept"
    while IFS= read -r config; do
        printf '\n' >> "$config"
        cp "$config" "$work/kept/$(basename "$config")"
    done < "$work/baseline/DEBIAN/conffiles"
    printf '# Local operator drop-in\n' > /etc/metrics-manager/telegraf.d/local.conf
    printf '# Local privileged drop-in\n' > /etc/metrics-manager/powerstat.d/local.conf
    printf '#!/bin/sh\nprintf "operator_metric value=9i\\n"\n' > /etc/metrics-manager/custom-metrics.d/local.sh
    chmod 0755 /etc/metrics-manager/custom-metrics.d/local.sh
    sha256sum /etc/metrics-manager/{telegraf.d/local.conf,powerstat.d/local.conf,custom-metrics.d/local.sh} > "$work/local.sha256"
    apt-get install --yes --no-install-recommends -o Dpkg::Options::=--force-confold "$package"
    while IFS= read -r config; do
        cmp "$work/kept/$(basename "$config")" "$config"
        test -f "$config.dpkg-dist"
        cmp "$config.dpkg-dist" <(dpkg-deb --fsys-tarfile "$package" | tar -xOf - ".$config")
    done < "$work/baseline/DEBIAN/conffiles"
    sha256sum --check "$work/local.sha256"
else
    apt-get install --yes --no-install-recommends "$package" curl
fi

test "$(dpkg-query -W -f='${Version}' metrics-manager)" = "$version"
test "$(dpkg-query -W -f='${Status}' metrics-manager)" = "install ok installed"
test "$(getent passwd metrics-manager | cut -d: -f7)" = /usr/sbin/nologin
test "$(stat -c '%a %U %G' /etc/metrics-manager/custom-metrics.d)" = "755 root root"
test "$(stat -c '%a %U %G' /run/metrics-manager)" = "750 metrics-manager metrics-manager"
test "$(stat -c '%a %U %G' /run/metrics-manager/qmassa.fifo)" = "640 root metrics-manager"
test -p /run/metrics-manager/qmassa.fifo
test -f /usr/share/doc/metrics-manager/native-metric-migration.md
test -f /usr/share/doc/metrics-manager/terminal-dashboard.md
test "$(find /usr/lib/systemd/system -maxdepth 1 -name 'metrics-manager-*.service' | wc -l)" = 7
systemd-analyze verify /usr/lib/systemd/system/metrics-manager-*.service
for plugin in /usr/libexec/metrics-manager/mm-plugin-* /usr/bin/mm-tui; do
    test "$(stat -c '%a %U %G' "$plugin")" = "755 root root"
    test "$("$plugin" -version | awk '{print $NF}')" = "$version"
done
/usr/libexec/metrics-manager/qmassa --version
/usr/libexec/metrics-manager/telegraf --version

runuser -u metrics-manager -- env METRICS_MANAGER_HOSTNAME=package-validation \
    /usr/libexec/metrics-manager/telegraf \
    --config /etc/metrics-manager/telegraf.conf \
    --config-directory /etc/metrics-manager/telegraf.d > "$work/telegraf.log" 2>&1 &
telegraf_pid=$!
ready=false
for ((attempt = 0; attempt < 30; attempt++)); do
    if curl --noproxy '*' --fail --silent http://127.0.0.1:9273/metrics > "$work/metrics"; then
        ready=true
        break
    fi
    sleep 1
done
if [[ $ready != true ]]; then cat "$work/telegraf.log" >&2; exit 1; fi
curl --noproxy '*' --fail --silent --show-error \
    --data-binary 'package_probe,source=package-validation value=17' http://127.0.0.1:8186/write
exported=false
for ((attempt = 0; attempt < 15; attempt++)); do
    curl --noproxy '*' --fail --silent --show-error http://127.0.0.1:9273/metrics > "$work/metrics"
    if grep -Eq '^package_probe\{[^}]*source="package-validation"[^}]*\} 17 [0-9]+$' "$work/metrics"; then
        exported=true
        break
    fi
    sleep 1
done
if [[ $exported != true ]]; then cat "$work/telegraf.log" >&2; exit 1; fi
test "$(grep -c '^package_probe{' "$work/metrics")" = 1
runuser -u metrics-manager -- /usr/bin/mm-tui -once -width 160 > "$work/tui"
grep -Fq 'Memory' "$work/tui"
grep -Fq 'CPU' "$work/tui"

if [[ $scenario == fresh ]]; then
    printf '# Local operator drop-in\n' > /etc/metrics-manager/telegraf.d/local.conf
    printf '# Local privileged drop-in\n' > /etc/metrics-manager/powerstat.d/local.conf
    printf '#!/bin/sh\nprintf "operator_metric value=9i\\n"\n' > /etc/metrics-manager/custom-metrics.d/local.sh
    chmod 0755 /etc/metrics-manager/custom-metrics.d/local.sh
    sha256sum /etc/metrics-manager/{telegraf.d/local.conf,powerstat.d/local.conf,custom-metrics.d/local.sh} > "$work/local.sha256"
fi
cleanup
telegraf_pid=
apt-get remove --yes metrics-manager
test "$(dpkg-query -W -f='${Status}' metrics-manager)" = "deinstall ok config-files"
test -f /etc/metrics-manager/telegraf.conf
sha256sum --check "$work/local.sha256"
getent passwd metrics-manager >/dev/null
test ! -e /usr/bin/mm-tui
test ! -e /run/metrics-manager

apt-get purge --yes metrics-manager
test ! -e /etc/metrics-manager
test ! -e /run/metrics-manager
if getent passwd metrics-manager >/dev/null || getent group metrics-manager >/dev/null; then
    echo "Service account or group remained after purge" >&2
    exit 1
fi
echo "PASS $scenario: dependencies, configuration preservation, ownership, units, telemetry, TUI, remove and purge"
echo "Systemd boot/service lifecycle and hardware privileges require a separate VM or host test."
