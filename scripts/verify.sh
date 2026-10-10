# shellcheck shell=bash
# End-of-install health check: every service the install set up must answer.
# Source after lib.sh, host.sh and remote.sh. verify_install returns 1 if anything failed.

VERIFY_FAILED=0

check() {
    local name="$1"; shift
    if "$@" >/dev/null 2>&1; then
        ok "$name"
    else
        printf '%sFAIL%s %s\n' "${C_ERR}" "${C_OFF}" "$name"
        VERIFY_FAILED=1
    fi
}

moonraker_json() { curl -sf -m 5 "localhost:7125$1"; }

klipper_ready() { moonraker_json /printer/info | grep -q '"state": *"ready"'; }
moonraker_sees_klipper() { moonraker_json /server/info | grep -q '"klippy_connected": *true'; }
moonraker_no_failed_components() { moonraker_json /server/info | grep -q '"failed_components": *\[\]'; }
load_cell_ready() { moonraker_json '/printer/objects/query?load_cell_probe=is_calibrated' | grep -q '"is_calibrated": *true'; }
happy_hare_enabled() { moonraker_json '/printer/objects/query?mmu=enabled' | grep -q '"enabled": *true'; }
spoolman_linked() { moonraker_json /server/spoolman/status | grep -q '"spoolman_connected": *true'; }
http_ok() { curl -sf -m 5 -o /dev/null "$1"; }
bridges_active() {
    systemctl is-active --quiet q2-serial-bridge@main:7001 q2-serial-bridge@thr:7002 q2-serial-bridge@mmu:7003
}
printer_proxies_active() {
    pssh "systemctl is-active --quiet q2-serial-proxy@main q2-serial-proxy@thr q2-serial-proxy@mmu"
}
printer_helixscreen_ok() {
    pssh "systemctl is-active --quiet helixscreen && grep -q '\"moonraker_host\": *\"${HOST_IP}\"' /home/${PRINTER_USER}/helixscreen/config/settings.json"
}

verify_install() {
    in_ci && return 0
    info "Checking the installation"
    VERIFY_FAILED=0
    check "serial bridges to the printer" bridges_active
    check "printer serial proxies" printer_proxies_active
    check "Klipper ready (mainboard, toolhead and Box connected)" klipper_ready
    check "Moonraker connected to Klipper" moonraker_sees_klipper
    check "Moonraker components loaded" moonraker_no_failed_components
    check "load cell ready for probing" load_cell_ready
    check "Happy Hare enabled" happy_hare_enabled
    has fluidd && check "Fluidd http://${HOST_IP}:${FLUIDD_PORT}/" http_ok "http://localhost:${FLUIDD_PORT}/"
    has mainsail && check "Mainsail http://${HOST_IP}:${MAINSAIL_PORT}/" http_ok "http://localhost:${MAINSAIL_PORT}/"
    local web_port="$FLUIDD_PORT"
    has fluidd || ! has mainsail || web_port="$MAINSAIL_PORT"
    { has fluidd || has mainsail; } && check "Moonraker API through nginx" http_ok "http://localhost:${web_port}/server/info"
    { has fluidd || has mainsail; } && check "Box drying page /box/" http_ok "http://localhost:${web_port}/box/"
    has autopa && check "autopa" http_ok "http://localhost:${web_port}/autopa/"
    if has spoolman; then
        check "Spoolman :7912" http_ok "http://localhost:7912/api/v1/info"
        check "Moonraker connected to Spoolman" spoolman_linked
    fi
    has printguard && check "PrintGuard :8000" http_ok "http://localhost:8000/"
    check "printer camera" http_ok "http://${PRINTER_IP}/webcam/?action=snapshot"
    check "HelixScreen running, pointed at ${HOST_IP}" printer_helixscreen_ok
    if [ "$VERIFY_FAILED" = 1 ]; then
        warn "some checks failed: see the FAIL lines above, ./install.sh status, ${DATA}/logs/ and docs/recovery.md"
        return 1
    fi
    ok "everything answers"
}
