# shellcheck shell=bash
# Printer-board side of install.sh, driven over SSH. Source after lib.sh and host.sh.

PRINTER_USER="${PRINTER_USER:-mks}"
PRINTER_WORK="/home/${PRINTER_USER}/q2-offload"
SSH_OPTS=(-o ConnectTimeout=10 -o ServerAliveInterval=15)

pssh() { ssh "${SSH_OPTS[@]}" "${PRINTER_USER}@${PRINTER_IP}" "$@"; }
# Root commands: -t so sudo can ask for the password (stock Qidi image: "makerbase")
proot() { ssh -t "${SSH_OPTS[@]}" "${PRINTER_USER}@${PRINTER_IP}" sudo bash "${PRINTER_WORK}/q2-printer.sh" "$@"; }

printer_ssh_key() {
    if ssh -o BatchMode=yes "${SSH_OPTS[@]}" "${PRINTER_USER}@${PRINTER_IP}" true 2>/dev/null; then
        return 0
    fi
    info "Setting up SSH key access to ${PRINTER_USER}@${PRINTER_IP} (stock password: makerbase)"
    [ -f "${HOME}/.ssh/id_ed25519" ] || ssh-keygen -q -t ed25519 -N '' -f "${HOME}/.ssh/id_ed25519"
    ssh-copy-id -i "${HOME}/.ssh/id_ed25519.pub" "${PRINTER_USER}@${PRINTER_IP}" >/dev/null
    ssh -o BatchMode=yes "${SSH_OPTS[@]}" "${PRINTER_USER}@${PRINTER_IP}" true \
        || die "SSH key login to the printer failed"
}

printer_push() {
    local tmp
    pssh "mkdir -p ${PRINTER_WORK}/firmware ${PRINTER_WORK}/deployer"
    tmp="$(mktemp -d)"
    curl -fsSL "https://raw.githubusercontent.com/Arksine/katapult/${KATAPULT_REF}/scripts/flashtool.py" -o "${tmp}/flashtool.py"
    scp -q "${SSH_OPTS[@]}" "${Q2_ROOT}/printer/q2-printer.sh" "${Q2_ROOT}/printer/q2-serial-proxy@.service" \
        "${tmp}/flashtool.py" "${PRINTER_USER}@${PRINTER_IP}:${PRINTER_WORK}/"
    rm -rf "$tmp"
    if [ -n "${FIRMWARE_DIR:-}" ]; then
        scp -q "${SSH_OPTS[@]}" "${FIRMWARE_DIR}"/q2-*.bin "${FIRMWARE_DIR}/SHA256SUMS" \
            "${PRINTER_USER}@${PRINTER_IP}:${PRINTER_WORK}/firmware/"
        pssh "cd ${PRINTER_WORK}/firmware && sha256sum -c --quiet --ignore-missing SHA256SUMS" \
            || die "firmware copy on the printer is corrupted"
    fi
}

# First conversion only: install Katapult on all three MCUs with the pinned deployers.
printer_deploy_katapult() {
    local tmp m
    tmp="$(mktemp -d)"
    curl -fsSL "$DEPLOYER_URL" -o "${tmp}/deployer.tgz"
    echo "${DEPLOYER_SHA256}  ${tmp}/deployer.tgz" | sha256sum -c --quiet || die "deployer archive checksum mismatch"
    tar xzf "${tmp}/deployer.tgz" -C "$tmp"
    echo "${DEPLOYER_MCU_SHA256}  ${tmp}/mcu-deployer.bin" | sha256sum -c --quiet || die "mcu-deployer checksum mismatch"
    echo "${DEPLOYER_THR_SHA256}  ${tmp}/thr-deployer.bin" | sha256sum -c --quiet || die "thr-deployer checksum mismatch"
    echo "${DEPLOYER_MMU_SHA256}  ${tmp}/mmu-deployer.bin" | sha256sum -c --quiet || die "mmu-deployer checksum mismatch"
    scp -q "${SSH_OPTS[@]}" "$tmp"/*-deployer.bin "${PRINTER_USER}@${PRINTER_IP}:${PRINTER_WORK}/deployer/"
    rm -rf "$tmp"

    cat <<EOF

${C_WARN}First conversion: Katapult bootloader on the three MCUs${C_OFF}
Qidi's own update scripts flash a Katapult "deployer" (n3oney/qidi-q2-klipper) while the
stock firmware still runs. Afterwards the stock Qidi bootloader is GONE: going back to
stock, or recovering from a power cut during this step, needs an ST-Link.
  - keep the printer powered and connected the whole time
  - one MCU at a time; each one is checked before the next
EOF
    confirm_phrase "INSTALL KATAPULT"
    for m in main thr box; do
        local file=mcu
        [ "$m" = thr ] && file=thr
        [ "$m" = box ] && file=mmu
        info "Katapult -> ${m}"
        proot deploy-katapult "$m" "${PRINTER_WORK}/deployer/${file}-deployer.bin" \
            || die "Katapult install failed on ${m}; stop here and see docs/recovery.md"
    done
}

printer_flash_all() {
    local m
    cat <<EOF

${C_WARN}Flashing Klipper ($(firmware_id)) on mainboard, toolhead and Qidi Box${C_OFF}
Each MCU is put into Katapult and its application offset is checked before writing.
EOF
    [ "${ASSUME_YES:-0}" = 1 ] || confirm_phrase "FLASH"
    if [ -n "$(systemctl list-unit-files klipper.service --no-legend 2>/dev/null)" ]; then
        sudo systemctl stop klipper q2-serial-bridge@main:7001 q2-serial-bridge@thr:7002 q2-serial-bridge@mmu:7003 2>/dev/null || true
    fi
    proot proxies-stop
    for m in main thr box; do
        proot flash "$m" "${PRINTER_WORK}/firmware/q2-${m}.bin" || die "flashing ${m} failed; see docs/recovery.md"
    done
    pssh "echo $(firmware_id) > ${PRINTER_WORK}/firmware-id"
    ok "all MCUs on firmware $(firmware_id)"
}

printer_firmware_id() { pssh "cat ${PRINTER_WORK}/firmware-id 2>/dev/null" || true; }

printer_proxies() {
    proot proxy-install "$HOST_IP"
    proot stock-stop
    proot proxies-start
}

# Point HelixScreen (the touchscreen UI) at the host's Moonraker, installing it if needed.
printer_helixscreen() {
    local settings="/home/${PRINTER_USER}/helixscreen/config/settings.json"
    if ! pssh "test -f ${settings}"; then
        confirm "Install HelixScreen on the printer touchscreen (stock Qidi UI needs a local Klipper)?" y || return 0
        pssh "curl -sSL https://releases.helixscreen.org/install.sh | sh" \
            || { warn "HelixScreen install failed; run it later on the printer"; return 0; }
        pssh "test -f ${settings}" || {
            warn "HelixScreen: in its first-run wizard, set Moonraker to ${HOST_IP}:7125"; return 0; }
    fi
    pssh "python3 - ${settings} ${HOST_IP}" <<'EOF'
import json, sys
path, host = sys.argv[1], sys.argv[2]
data = json.load(open(path))
printers = data.get('printers') or {}
for p in (printers.values() if printers else [data]):
    p['moonraker_host'] = host
    p['moonraker_port'] = 7125
json.dump(data, open(path, 'w'), indent=2)
EOF
    proot_cmd systemctl restart helixscreen || true
    ok "HelixScreen -> Moonraker ${HOST_IP}:7125"
}

proot_cmd() { ssh -t "${SSH_OPTS[@]}" "${PRINTER_USER}@${PRINTER_IP}" sudo "$@"; }
