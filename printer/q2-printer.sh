#!/usr/bin/env bash
# Runs ON the Qidi Q2 printer board (stock Qidi OS, user mks), copied there by install.sh.
# Every subcommand is idempotent. Run as root (install.sh uses: ssh -t ... sudo bash ...).
#
#   q2-printer.sh backup
#   q2-printer.sh detect
#   q2-printer.sh proxy-install <klipper-host-ip>
#   q2-printer.sh stock-stop | stock-start
#   q2-printer.sh proxies-start | proxies-stop
#   q2-printer.sh katapult-status <main|thr|box>
#   q2-printer.sh deploy-katapult <main|thr|box> <deployer.bin>
#   q2-printer.sh flash <main|thr|box> <firmware-dir>
#   q2-printer.sh convert <firmware-id> [deploy]   (deploy Katapult if needed, flash all three)
#   q2-printer.sh setup <klipper-host-ip>          (proxy-install + stock-stop + proxies-start + sudoers)
#   q2-printer.sh sudoers                          (passwordless sudo for this script only)
#   q2-printer.sh status
#   q2-printer.sh helixscreen-restart
set -Eeuo pipefail

USER_HOME="${Q2_PRINTER_HOME:-/home/mks}"
WORK="${USER_HOME}/q2-offload"
FLASHTOOL="${WORK}/flashtool.py"
STOCK_SERVICES="klipper klipper-mcu moonraker makerbase-client"
THR_DEVICE=/dev/ttyS4
THR_BAUD=500000

# Katapult application offsets: the firmware must be linked for exactly these.
declare -A OFFSET=([main]=0x8008000 [thr]=0x8002000 [box]=0x8004000)
declare -A MCU_TYPE=([main]=stm32f407xx [thr]=stm32f103xe [box]=stm32f401xc)
declare -A PORT=([main]=7001 [thr]=7002 [mmu]=7003)

info() { printf '==> %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" = 0 ] || die "run as root (sudo)"
mkdir -p "$WORK"

# Stock Qidi OS is Debian 11 with stale (or no) package lists, and bullseye is being moved
# to archive.debian.org. Refresh the lists; if a package is still missing, switch the
# sources to the archive (old list kept as sources.list.q2-offload.bak) and retry.
apt_install() {
    apt-get update -qq >/dev/null 2>&1 || true
    apt-get install -y -qq "$@" >/dev/null 2>&1 && return 0
    info "Debian mirror lacks $*; switching apt to archive.debian.org"
    [ -f /etc/apt/sources.list.q2-offload.bak ] || cp /etc/apt/sources.list /etc/apt/sources.list.q2-offload.bak
    cat > /etc/apt/sources.list <<'SRC'
deb http://archive.debian.org/debian bullseye main contrib
deb http://archive.debian.org/debian bullseye-updates main contrib
deb http://archive.debian.org/debian bullseye-backports main contrib
deb http://archive.debian.org/debian-security bullseye-security main contrib
SRC
    echo 'Acquire::Check-Valid-Until "false";' > /etc/apt/apt.conf.d/99-q2-offload-archive
    apt-get update -qq >/dev/null || die "apt-get update failed (no internet on the printer?)"
    apt-get install -y -qq "$@" >/dev/null || die "cannot install $*"
}

python_bin() {
    # Klipper's venv on the stock image has pyserial; fall back to python3 + python3-serial
    if [ -x "${USER_HOME}/klippy-env/bin/python" ]; then
        echo "${USER_HOME}/klippy-env/bin/python"
    else
        python3 -c 'import serial' 2>/dev/null || apt_install python3-serial
        echo python3
    fi
}

# One device or nothing; fails on ambiguity (two boxes, leftovers...)
one_device() {
    local matches=()
    shopt -s nullglob
    # shellcheck disable=SC2206  # $1 is a glob pattern, expanded on purpose
    matches=($1)
    shopt -u nullglob
    [ "${#matches[@]}" -le 1 ] || die "several devices match $1: ${matches[*]}"
    [ "${#matches[@]}" -eq 1 ] && echo "${matches[0]}"
    return 0
}

klipper_device() {
    case "$1" in
        main) one_device "/dev/serial/by-id/usb-Klipper_${MCU_TYPE[main]}_*-if00" ;;
        box)  one_device "/dev/serial/by-id/usb-Klipper_${MCU_TYPE[box]}_*-if00" ;;
        thr)  echo "$THR_DEVICE" ;;
    esac
}

katapult_device() {
    case "$1" in
        main|box) one_device "/dev/serial/by-id/usb-katapult_${MCU_TYPE[$1]}_*-if00" ;;
        thr) echo "$THR_DEVICE" ;;
    esac
}

flashtool() {
    [ -f "$FLASHTOOL" ] || die "missing $FLASHTOOL (install.sh copies it)"
    "$(python_bin)" "$FLASHTOOL" "$@"
}

cmd_backup() {
    local out
    out="${WORK}/backup-$(date +%Y%m%d-%H%M%S).tgz"
    systemctl list-unit-files --type=service --state=enabled --no-legend > "${WORK}/enabled-services.txt"
    tar czf "$out" -C "$USER_HOME" --ignore-failed-read printer_data/config \
        q2-offload/enabled-services.txt 2>/dev/null || true
    [ "$(tar tzf "$out" 2>/dev/null | wc -l)" -gt 1 ] || die "backup ${out} is empty, stopping"
    chown -R "$(stat -c %U "$USER_HOME")": "$WORK"
    info "backup: $out"
}

cmd_detect() {
    local d
    for m in main thr box; do
        d="$(klipper_device "$m")"
        printf '%-5s klipper : %s\n' "$m" "${d:-<none>}"
        d="$(katapult_device "$m")"
        [ "$m" = thr ] || printf '%-5s katapult: %s\n' "$m" "${d:-<none>}"
    done
    ls -l /dev/serial/by-id/ 2>/dev/null || true
}

cmd_proxy_install() {
    local host="${1:?klipper host ip}" main box
    command -v socat >/dev/null || { info "installing socat"; apt_install socat; }
    main="$(klipper_device main)"; box="$(klipper_device box)"
    [ -n "$main" ] || die "mainboard not found as usb-Klipper_${MCU_TYPE[main]} (flash it first)"
    [ -n "$box" ] || die "Qidi Box not found as usb-Klipper_${MCU_TYPE[box]} (flash it first)"
    mkdir -p /etc/q2-serial-proxy
    printf 'DEVICE=%s\nPORT=%s\nALLOW=%s/32\nSERIAL_OPTS=\n' "$main" "${PORT[main]}" "$host" > /etc/q2-serial-proxy/main.env
    printf 'DEVICE=%s\nPORT=%s\nALLOW=%s/32\nSERIAL_OPTS=,b%s\n' "$THR_DEVICE" "${PORT[thr]}" "$host" "$THR_BAUD" > /etc/q2-serial-proxy/thr.env
    printf 'DEVICE=%s\nPORT=%s\nALLOW=%s/32\nSERIAL_OPTS=\n' "$box" "${PORT[mmu]}" "$host" > /etc/q2-serial-proxy/mmu.env
    install -m 644 "${WORK}/q2-serial-proxy@.service" /etc/systemd/system/
    systemctl daemon-reload
    info "proxies configured for host ${host}"
}

cmd_stock_stop() {
    for s in $STOCK_SERVICES; do
        systemctl list-unit-files "${s}.service" --no-legend | grep -q . || continue
        systemctl disable --now "$s" >/dev/null 2>&1 || true
        info "stopped and disabled ${s}"
    done
}

cmd_stock_start() {
    cmd_proxies_stop
    for s in $STOCK_SERVICES; do
        systemctl list-unit-files "${s}.service" --no-legend | grep -q . || continue
        systemctl enable --now "$s" >/dev/null 2>&1 || true
        info "enabled ${s}"
    done
}

cmd_proxies_start() {
    systemctl enable q2-serial-proxy@main q2-serial-proxy@thr q2-serial-proxy@mmu
    # restart, not --now: a running proxy would keep an old ALLOW range
    systemctl restart q2-serial-proxy@main q2-serial-proxy@thr q2-serial-proxy@mmu
    info "proxies running"
}

cmd_proxies_stop() {
    systemctl disable --now q2-serial-proxy@main q2-serial-proxy@thr q2-serial-proxy@mmu >/dev/null 2>&1 || true
}

# Print Katapult status and check the application offset and MCU type.
cmd_katapult_status() {
    local m="${1:?main|thr|box}" dev out
    dev="$(katapult_device "$m")"
    [ -n "$dev" ] || die "${m}: no Katapult device (is the MCU in its bootloader?)"
    if [ "$m" = thr ]; then
        out="$(flashtool -d "$dev" -b "$THR_BAUD" -s 2>&1 | tr -d '\0')" || { echo "$out" >&2; die "${m}: flashtool status failed"; }
    else
        out="$(flashtool -d "$dev" -s 2>&1 | tr -d '\0')" || { echo "$out" >&2; die "${m}: flashtool status failed"; }
    fi
    echo "$out"
    echo "$out" | grep -Eqi "Application Start: 0x0*${OFFSET[$m]#0x}([^0-9a-f]|$)" \
        || die "${m}: Katapult application offset is not ${OFFSET[$m]}, refusing to flash"
    echo "$out" | grep -qi "MCU type: ${MCU_TYPE[$m]}" \
        || die "${m}: Katapult reports another MCU type than ${MCU_TYPE[$m]}"
    touch "$(katapult_marker "$m")"
    info "${m}: Katapult OK (${OFFSET[$m]}, ${MCU_TYPE[$m]})"
}

# Nothing may talk to the MCUs while flashing: stock Klipper, the stock UI or our proxies.
release_devices() {
    local s
    cmd_proxies_stop
    for s in $STOCK_SERVICES; do systemctl stop "$s" 2>/dev/null || true; done
}

refuse_if_busy() {
    local dev="$1" holders
    [ -e "$dev" ] || return 0
    holders="$(fuser "$dev" 2>/dev/null || true)"
    [ -z "$holders" ] || die "${dev} is still in use by pid(s)${holders}; stop them first"
}

wait_katapult() {
    local m="$1"
    for _ in $(seq 1 30); do
        [ -n "$(katapult_device "$m")" ] && return 0
        sleep 0.5
    done
    die "${m}: Katapult did not show up"
}

# Reboot a running Klipper MCU into Katapult and wait for the bootloader.
enter_katapult() {
    local m="$1" dev
    dev="$(katapult_device "$m")"
    if [ "$m" != thr ] && [ -n "$dev" ]; then return 0; fi
    dev="$(klipper_device "$m")"
    [ -n "$dev" ] || die "${m}: neither Klipper nor Katapult device found"
    refuse_if_busy "$dev"
    info "${m}: requesting the bootloader on ${dev}"
    if [ "$m" = thr ]; then
        # A UART has no USB descriptor to wait for: give Katapult a moment to start
        flashtool -d "$dev" -b "$THR_BAUD" -r
        sleep 1
        return 0
    fi
    flashtool -d "$dev" -r
    wait_katapult "$m"
}

cmd_flash() {
    local m="${1:?main|thr|box}" fwdir="${2:?firmware dir}" dev bin
    bin="${fwdir}/${m}/klipper.bin"
    [ -s "$bin" ] || die "missing firmware $bin"
    [ -s "${fwdir}/${m}/klipper.dict" ] || die "missing ${fwdir}/${m}/klipper.dict"
    grep -Eq "\"MCU\": *\"${MCU_TYPE[$m]}\"" "${fwdir}/${m}/klipper.dict" \
        || die "${bin} is not built for ${MCU_TYPE[$m]}, refusing to flash"
    release_devices
    enter_katapult "$m"
    cmd_katapult_status "$m"
    dev="$(katapult_device "$m")"
    info "${m}: flashing $(basename "$bin")"
    if [ "$m" = thr ]; then flashtool -d "$dev" -b "$THR_BAUD" -f "$bin"; else flashtool -d "$dev" -f "$bin"; fi
    info "${m}: flashed"
}

# First conversion from stock: Qidi's own update scripts flash a Katapult deployer while
# the stock firmware still runs (they read its dictionary to find the reset command).
# Marker written once Katapult is confirmed on an MCU. After a Klipper flash a USB MCU no
# longer shows up as Katapult, and its USB name cannot tell our Klipper from Qidi's stock
# one, so without the marker a resumed conversion would run Qidi's script on our firmware.
katapult_marker() { echo "${WORK}/katapult-$1"; }

has_katapult() {
    local m="$1"
    [ -e "$(katapult_marker "$m")" ] && return 0
    if [ "$m" = thr ]; then
        flashtool -d "$THR_DEVICE" -b "$THR_BAUD" -s >/dev/null 2>&1
    else
        [ -n "$(katapult_device "$m")" ]
    fi
}

cmd_deploy_katapult() {
    local m="${1:?main|thr|box}" bin="${2:?deployer.bin}" box
    [ -s "$bin" ] || die "missing deployer $bin"
    if has_katapult "$m"; then
        info "${m}: Katapult already installed, skipping the deployer"
        return 0
    fi
    # Qidi's scripts read the dictionary of the running stock firmware: stock Klipper must
    # not hold the port, and the scripts expect the mks home directory
    release_devices
    cd "$USER_HOME"
    case "$m" in
        main) HOME="$USER_HOME" bash "${USER_HOME}/mcu_update.sh" "$bin" ;;
        thr)  HOME="$USER_HOME" bash "${USER_HOME}/mcu_update_THR.sh" "$bin" ;;
        box)
            box="$(one_device '/dev/serial/by-id/usb-Klipper_QIDI_BOX_V2*-if00')"
            [ -n "$box" ] || box="$(klipper_device box)"
            [ -n "$box" ] || die "Qidi Box not found (usb-Klipper_QIDI_BOX_V2* or usb-Klipper_stm32f401xc*)"
            HOME="$USER_HOME" bash "${USER_HOME}/mcu_update_BOX_to_v2.sh" "$bin" "$box"
            ;;
    esac
    if [ "$m" = thr ]; then sleep 2; else wait_katapult "$m"; fi
    cmd_katapult_status "$m"
}

# Whole firmware phase in one root session (one sudo password prompt)
cmd_convert() {
    local id="${1:?firmware id}" deploy="${2:-}" m file
    if [ "$deploy" = deploy ]; then
        for m in main thr box; do
            file=mcu; [ "$m" = thr ] && file=thr; [ "$m" = box ] && file=mmu
            info "Katapult -> ${m}"
            cmd_deploy_katapult "$m" "${WORK}/deployer/${file}-deployer.bin"
        done
    fi
    for m in main thr box; do
        cmd_flash "$m" "${WORK}/firmware"
    done
    echo "$id" > "${WORK}/firmware-id"
    chown "$(stat -c %U "$USER_HOME")": "${WORK}/firmware-id"
    info "all MCUs on firmware ${id}"
}

# Let the printer user run this script (and only this one) as root without a password, so
# the host can drive it non-interactively. mks already has full sudo with the well-known
# stock password, so this grants nothing new.
cmd_sudoers() {
    local u tmp
    u="$(stat -c %U "$USER_HOME")"
    tmp="$(mktemp)"
    printf '# q2-offload: host-driven printer maintenance
%s ALL=(root) NOPASSWD: /bin/bash %s/q2-printer.sh *, /usr/bin/bash %s/q2-printer.sh *
' \
        "$u" "$WORK" "$WORK" > "$tmp"
    visudo -cqf "$tmp" || die "invalid sudoers rule"
    install -m 440 "$tmp" /etc/sudoers.d/q2-offload
    rm -f "$tmp"
    info "sudo rule for ${u}: q2-printer.sh only"
}

cmd_setup() {
    cmd_proxy_install "${1:?klipper host ip}"
    cmd_stock_stop
    cmd_proxies_start
    cmd_sudoers
}

cmd_status() {
    cmd_detect
    systemctl --no-pager --no-legend list-units 'q2-serial-proxy@*' || true
    for s in $STOCK_SERVICES; do
        printf '%-18s %s\n' "$s" "$(systemctl is-enabled "$s" 2>/dev/null || echo absent)"
    done
}

sub="${1:-}"; shift || true
case "$sub" in
    backup) cmd_backup ;;
    detect) cmd_detect ;;
    proxy-install) cmd_proxy_install "$@" ;;
    stock-stop) cmd_stock_stop ;;
    stock-start) cmd_stock_start ;;
    proxies-start) cmd_proxies_start ;;
    proxies-stop) cmd_proxies_stop ;;
    katapult-status) cmd_katapult_status "$@" ;;
    deploy-katapult) cmd_deploy_katapult "$@" ;;
    flash) cmd_flash "$@" ;;
    convert) cmd_convert "$@" ;;
    setup) cmd_setup "$@" ;;
    sudoers) cmd_sudoers ;;
    status) cmd_status ;;
    helixscreen-restart) systemctl restart helixscreen ;;
    *) sed -n '2,15p' "$0"; exit 2 ;;
esac
