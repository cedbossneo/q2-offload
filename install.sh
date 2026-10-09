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
#   ./install.sh check           check that every installed service answers
#
# Options:
#   --printer <ip>               printer IP address (asked otherwise)
#   --components <list>          comma list among: mainsail,fluidd,spoolman,autopa,printguard
#                                (default: all)
#   --build-firmware             build the MCU firmware here instead of downloading it
#   --yes                        answer yes to plain yes/no questions (flashing always asks)
#   --ci                         CI mode: host software only, no systemd/nginx/docker/printer
#
# Internal: "update --unattended --as-user <user>" is run as root by q2-offload.service
# when Moonraker has updated the q2-offload repo (see host/moonraker.conf).
set -Eeuo pipefail

Q2_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export Q2_ROOT

# Unattended root run: everything that follows works on the target user's home
UNATTENDED=0; AS_USER=""
for ((i = 1; i <= $#; i++)); do
    case "${!i}" in
        --unattended) UNATTENDED=1 ;;
        --as-user) j=$((i + 1)); AS_USER="${!j:-}" ;;
    esac
done
if [ "$UNATTENDED" = 1 ] && [ "$(id -u)" = 0 ]; then
    [ -n "$AS_USER" ] || { echo "ERROR: --unattended as root needs --as-user" >&2; exit 2; }
    HOME="$(getent passwd "$AS_USER" | cut -d: -f6)"
    [ -n "$HOME" ] || { echo "ERROR: no user ${AS_USER}" >&2; exit 2; }
    USER="$AS_USER"
    export HOME USER
fi
. "${Q2_ROOT}/scripts/lib.sh"
. "${Q2_ROOT}/scripts/host.sh"
. "${Q2_ROOT}/scripts/remote.sh"
. "${Q2_ROOT}/scripts/verify.sh"
. "${Q2_ROOT}/scripts/calibrate.sh"

ALL_COMPONENTS=mainsail,fluidd,spoolman,autopa,printguard
SETTINGS="${STATE_DIR}/settings.env"
FLUIDD_PORT=80
MAINSAIL_PORT=81

usage() { sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

command="install"
case "${1:-}" in
    install|update|host|printer|flash|status|check|_update-check|_update-user) command="$1"; shift ;;
    -h|--help) usage ;;
esac
while [ $# -gt 0 ]; do
    case "$1" in
        --printer) PRINTER_IP="${2:?}"; shift 2 ;;
        --components) COMPONENTS="${2:?}"; shift 2 ;;
        --build-firmware) BUILD_FIRMWARE=1; shift ;;
        --yes|-y) ASSUME_YES=1; shift ;;
        --ci) Q2_CI=1; shift ;;
        --unattended) shift ;;
        --as-user) shift 2 ;;
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
    [ "$(id -u)" = 0 ] && return 0  # unattended root phase: the user phase already saved them
    mkdir -p "$STATE_DIR"
    cat > "$SETTINGS" <<EOF
PRINTER_IP=${PRINTER_IP}
HOST_IP=${HOST_IP}
COMPONENTS=${COMPONENTS}
EOF
}

# Component menu, shown on an interactive install unless --components was given. Starts
# from the previous selection (settings.env) or from everything.
COMPONENT_HELP=(
    "mainsail|Mainsail web interface (port ${MAINSAIL_PORT})"
    "fluidd|Fluidd web interface (port ${FLUIDD_PORT})"
    "spoolman|Spoolman spool inventory, filled by the Box NFC tags (Docker, port 7912)"
    "autopa|autopa: pressure advance calibration with the printer camera"
    "printguard|PrintGuard: print failure detection on the camera (Docker, about 1 CPU core)"
)

choose_components() {
    local sel=",${COMPONENTS-$ALL_COMPONENTS}," i entry name reply n
    while true; do
        printf '\n%sComponents to install%s (Klipper, Moonraker and Happy Hare are always installed)\n' "${C_INFO}" "${C_OFF}"
        i=1
        for entry in "${COMPONENT_HELP[@]}"; do
            name="${entry%%|*}"
            printf '  %d) [%s] %s\n' "$i" "$([[ "$sel" == *",${name},"* ]] && echo x || echo ' ')" "${entry#*|}"
            i=$((i + 1))
        done
        read -r -p "Numbers to toggle (e.g. 2 5), Enter to continue: " reply
        [ -z "$reply" ] && break
        for n in $reply; do
            [[ "$n" =~ ^[0-9]+$ ]] && [ "$n" -ge 1 ] && [ "$n" -le "${#COMPONENT_HELP[@]}" ] \
                || { warn "ignored '${n}'"; continue; }
            name="${COMPONENT_HELP[$((n - 1))]%%|*}"
            if [[ "$sel" == *",${name},"* ]]; then sel="${sel/,${name},/,}"; else sel="${sel}${name},"; fi
        done
    done
    # Keep the canonical order
    COMPONENTS=""
    for name in ${ALL_COMPONENTS//,/ }; do
        [[ "$sel" == *",${name},"* ]] && COMPONENTS="${COMPONENTS:+${COMPONENTS},}${name}"
    done
}

preflight() {
    if [ "$UNATTENDED" != 1 ]; then
        [ "$(id -u)" != 0 ] || die "run as your normal user (sudo is used where needed), not as root"
        in_ci || sudo -v || die "sudo is required"
    fi
    command -v apt-get >/dev/null || die "only Debian/Ubuntu hosts are supported"
    if [ "$command" = install ] && [ -z "$cli_components" ] && [ "${ASSUME_YES:-0}" != 1 ] \
        && [ -t 0 ] && ! in_ci; then
        choose_components
    fi
    COMPONENTS="${COMPONENTS-$ALL_COMPONENTS}"
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
    info "Waiting for Klipper to connect to the three MCUs (up to 2 minutes)"
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
    printer_prepare
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
    host_ui_defaults
    printer_helixscreen
    if klipper_ready; then
        calibrate_load_cell_tare || true
        calibrate_offer
    fi
    local healthy=0
    verify_install || healthy=1
    final_notes "$healthy"
}

do_update() {
    preflight
    banner
    printing && die "a print is running: update after it ends"
    host_install_all
    host_firmware
    if [ "$(printer_firmware_id)" != "$(firmware_id)" ]; then
        info "MCU firmware changes ($(printer_firmware_id) -> $(firmware_id)): Klipper and MCUs must match"
        printer_prepare
        printer_convert
        proot proxies-start
    fi
    host_start
    wait_ready || true
    verify_install
}

# Unattended update (q2-offload.service), root part. Option chosen for this project:
# when the MCU firmware would change, nothing is updated and the user is told to run
# "./install.sh update" in a terminal (flashing needs someone at the printer).
do_update_unattended() {
    [ "$(id -u)" = 0 ] || die "--unattended runs as root (q2-offload.service)"
    exec 9> /run/q2-offload-update.lock
    flock -n 9 || die "an update is already running"
    echo "===== $(date -Is) q2-offload update"
    run_user() {
        runuser -u "$AS_USER" -- env HOME="$HOME" USER="$AS_USER" PATH=/usr/local/bin:/usr/bin:/bin \
            "${Q2_ROOT}/install.sh" "$@" --unattended
    }
    local rc=0
    run_user _update-check || rc=$?
    case "$rc" in
        0) ;;
        10|11) return 0 ;;  # flash needed / print running: already reported
        *) notify "update check failed (logs/q2-offload-update.log)"; return 1 ;;
    esac
    notify "updating Klipper, Happy Hare and the web clients, Klipper will restart"
    run_user _update-user || { notify "update FAILED (logs/q2-offload-update.log)"; return 1; }
    # Root phase: system packages, nginx, containers, units, restarts
    preflight
    moonraker_sysdeps
    host_nginx
    host_spoolman
    host_printguard
    host_services
    systemctl restart klipper
    if [ -e "${STATE_DIR}/moonraker-changed" ]; then
        rm -f "${STATE_DIR}/moonraker-changed"
        systemctl restart moonraker
        sleep 5
    fi
    wait_ready || true
    notify "update done (firmware $(firmware_id))"
}

# User part 1: nothing is changed unless the update can complete without flashing
do_update_check() {
    preflight
    if printing; then
        notify "a print is running: update not applied, use Update again after the print"
        return 11
    fi
    local cur
    cur="$(printer_firmware_id)"
    if [ "$cur" != "$(firmware_id)" ]; then
        notify "this update changes the MCU firmware (${cur:-unknown} -> $(firmware_id)): nothing was changed. Run ./install.sh update in a terminal on the host to update and flash."
        return 10
    fi
}

# User part 2: everything under the user's home
do_update_user() {
    preflight
    host_klipper
    host_moonraker_update
    host_extensions
    host_config
    host_happy_hare
    host_autopa
    host_web_clients
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
    if [ "${1:-0}" = 0 ]; then
        printf '\n%sDone.%s\n' "${C_OK}" "${C_OFF}"
    else
        printf '\n%sDone, but some checks failed (see above).%s\n' "${C_WARN}" "${C_OFF}"
    fi
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
    update) if [ "$UNATTENDED" = 1 ] && [ "$(id -u)" = 0 ]; then do_update_unattended; else do_update; fi ;;
    _update-check) do_update_check ;;
    _update-user) do_update_user ;;
    host) preflight; banner; host_install_all; in_ci || host_start ;;
    printer) preflight; printer_prepare; printer_proxies; printer_helixscreen ;;
    flash) preflight; printing && die "a print is running"; host_firmware; printer_prepare; printer_convert; proot proxies-start; host_start ;;
    status) do_status ;;
    check) [ -f "$SETTINGS" ] || die "not installed yet"; verify_install ;;
esac
