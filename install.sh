#!/usr/bin/env bash
# q2-offload: run Klipper for a Qidi Q2 + Qidi Box on another Linux machine.
#
# Run on the Klipper HOST (Debian 12 / Ubuntu 22.04+, x86_64 or arm64), as your normal user:
#   ./install.sh                 guided install (host stack, printer conversion, flashing)
#   ./install.sh update          bring host software and MCU firmware to this repo's VERSIONS
#   ./install.sh host            (re)install only the host software
#   ./install.sh printer         (re)configure only the printer board (proxies, HelixScreen)
#   ./install.sh flash           reflash the MCUs (Katapult must already be installed)
#   ./install.sh status          show what is installed and running
#
# Options:
#   --printer <ip>               printer IP address (asked otherwise)
#   --components <list>          comma list among: mainsail,fluidd,spoolman,autopa,printguard
#                                (default: all)
#   --build-firmware             build the MCU firmware here instead of downloading it
#   --yes                        answer yes to plain yes/no questions (flashing always asks)
#   --ci                         CI mode: host software only, no systemd/nginx/docker/printer
set -Eeuo pipefail

Q2_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export Q2_ROOT
. "${Q2_ROOT}/scripts/lib.sh"
. "${Q2_ROOT}/scripts/host.sh"
. "${Q2_ROOT}/scripts/remote.sh"

ALL_COMPONENTS=mainsail,fluidd,spoolman,autopa,printguard
SETTINGS="${STATE_DIR}/settings.env"
FLUIDD_PORT=80
MAINSAIL_PORT=81

usage() { sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

command="install"
case "${1:-}" in
    install|update|host|printer|flash|status) command="$1"; shift ;;
    -h|--help) usage ;;
esac
while [ $# -gt 0 ]; do
    case "$1" in
        --printer) PRINTER_IP="${2:?}"; shift 2 ;;
        --components) COMPONENTS="${2:?}"; shift 2 ;;
        --build-firmware) BUILD_FIRMWARE=1; shift ;;
        --yes|-y) ASSUME_YES=1; shift ;;
        --ci) Q2_CI=1; shift ;;
        -h|--help) usage ;;
        *) warn "unknown option $1"; usage 2 ;;
    esac
done

# Saved answers from a previous run; options given on the command line win
cli_printer="${PRINTER_IP:-}"; cli_components="${COMPONENTS:-}"
# shellcheck disable=SC1090
[ -f "$SETTINGS" ] && . "$SETTINGS"
[ -n "$cli_printer" ] && PRINTER_IP="$cli_printer"
[ -n "$cli_components" ] && COMPONENTS="$cli_components"

Q2_ORIGIN="$(git -C "$Q2_ROOT" remote get-url origin 2>/dev/null || echo https://github.com/cedbossneo/q2-offload.git)"
Q2_GITHUB_REPO="$(echo "$Q2_ORIGIN" | sed -E 's#(git@github.com:|https://github.com/)##; s#\.git$##')"

save_settings() {
    mkdir -p "$STATE_DIR"
    cat > "$SETTINGS" <<EOF
PRINTER_IP=${PRINTER_IP}
HOST_IP=${HOST_IP}
COMPONENTS=${COMPONENTS}
EOF
}

preflight() {
    [ "$(id -u)" != 0 ] || die "run as your normal user (sudo is used where needed), not as root"
    command -v apt-get >/dev/null || die "only Debian/Ubuntu hosts are supported"
    in_ci || sudo -v || die "sudo is required"
    COMPONENTS="${COMPONENTS:-$ALL_COMPONENTS}"
    local c
    for c in ${COMPONENTS//,/ }; do
        [[ ",${ALL_COMPONENTS}," == *",${c},"* ]] || die "unknown component '${c}' (valid: ${ALL_COMPONENTS})"
    done
    if in_ci; then
        PRINTER_IP="${PRINTER_IP:-192.0.2.10}"; HOST_IP="${HOST_IP:-192.0.2.20}"
        return 0
    fi
    if [ -z "${PRINTER_IP:-}" ]; then
        [ -t 0 ] || die "pass --printer <ip>"
        read -r -p "Printer IP address: " PRINTER_IP
    fi
    [[ "$PRINTER_IP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "invalid printer IP '${PRINTER_IP}'"
    HOST_IP="$(ip -4 route get "$PRINTER_IP" 2>/dev/null | sed -n 's/.* src \([0-9.]*\).*/\1/p' || true)"
    [ -n "$HOST_IP" ] || die "no route to ${PRINTER_IP}"
    save_settings
}

banner() {
    cat <<EOF
${C_INFO}q2-offload${C_OFF} — Klipper ${KLIPPER_REF:0:9}, Happy Hare ${HAPPY_HARE_REF:0:9}, firmware $(firmware_id)
  printer ${PRINTER_IP}   host ${HOST_IP}   components ${COMPONENTS}
EOF
}

wait_ready() {
    local state
    for _ in $(seq 1 60); do
        state="$(curl -s localhost:7125/printer/info 2>/dev/null | sed -n 's/.*"state": *"\([a-z]*\)".*/\1/p')"
        [ "$state" = ready ] && { ok "Klipper is ready"; return 0; }
        sleep 2
    done
    warn "Klipper is not ready (state: ${state:-unknown}); check ${DATA}/logs/klippy.log"
    return 1
}

printing() {
    curl -s "localhost:7125/printer/objects/query?print_stats=state" 2>/dev/null \
        | grep -Eq '"state": *"(printing|paused)"'
}

do_install() {
    preflight
    banner
    cat <<EOF

This will:
  1. install Klipper, Moonraker, Happy Hare and the selected components on THIS machine
  2. convert the printer board into a serial proxy (its own Klipper/Moonraker stop)
  3. flash the mainboard, toolhead and Qidi Box MCUs
Read README.md (warnings) first. A backup of the printer config is made before step 2.
EOF
    confirm "Continue?" n || exit 0
    host_install_all
    host_firmware
    printer_ssh_key
    printer_push
    proot backup
    if [ -z "$(printer_firmware_id)" ] \
        && confirm "Is this the first conversion from Qidi's STOCK firmware?" y; then
        # Also safe on a partly converted printer: MCUs already running Katapult are skipped
        printer_fetch_deployers
        printer_convert deploy
    else
        printer_convert
    fi
    printer_proxies
    host_start
    wait_ready || true
    printer_helixscreen
    final_notes
}

do_update() {
    preflight
    banner
    printing && die "a print is running: update after it ends"
    host_install_all
    host_firmware
    if [ "$(printer_firmware_id)" != "$(firmware_id)" ]; then
        info "MCU firmware changes ($(printer_firmware_id) -> $(firmware_id)): Klipper and MCUs must match"
        printer_ssh_key
        printer_push
        printer_convert
        proot proxies-start
    fi
    host_start
    wait_ready || true
}

do_status() {
    [ -f "$SETTINGS" ] || die "not installed yet"
    banner
    echo "MCU firmware on the printer: $(printer_firmware_id || echo unknown)"
    systemctl --no-pager --no-legend list-units 'klipper*' 'moonraker*' 'q2-serial-bridge@*' 'nginx*' || true
    curl -s localhost:7125/printer/info | sed -n 's/.*"state": *"\([a-z]*\)".*/Klipper state: \1/p'
    pssh "sudo -n bash ${PRINTER_WORK}/q2-printer.sh status" 2>/dev/null || proot status
}

final_notes() {
    cat <<EOF

${C_OK}Done.${C_OFF}
EOF
    has fluidd && echo "  Fluidd      http://${HOST_IP}/"
    has mainsail && echo "  Mainsail    http://${HOST_IP}:${MAINSAIL_PORT}/"
    has autopa && echo "  autopa      http://${HOST_IP}/autopa/"
    has spoolman && echo "  Spoolman    http://${HOST_IP}:7912/"
    has printguard && echo "  PrintGuard  http://${HOST_IP}:8000/  (camera: http://${PRINTER_IP}/webcam/?action=stream, printer: http://${HOST_IP})"
    cat <<EOF

Next: calibrate this machine (load cell, PID, input shaper, Box gears): docs/calibration.md
Update later with: git pull && ./install.sh update
EOF
}

case "$command" in
    install) do_install ;;
    update) do_update ;;
    host) preflight; banner; host_install_all; in_ci || host_start ;;
    printer) preflight; printer_ssh_key; printer_push; printer_proxies; printer_helixscreen ;;
    flash) preflight; printing && die "a print is running"; host_firmware; printer_ssh_key; printer_push; printer_convert; proot proxies-start; host_start ;;
    status) do_status ;;
esac
