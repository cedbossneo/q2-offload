# shellcheck shell=bash
# Printer-board side of install.sh, driven over SSH. Source after lib.sh and host.sh.

PRINTER_USER="${PRINTER_USER:-mks}"
PRINTER_WORK="/home/${PRINTER_USER}/q2-offload"
SSH_OPTS=(-o ConnectTimeout=10 -o ServerAliveInterval=15)
# Unattended update: never wait for a password
[ "${UNATTENDED:-0}" = 1 ] && SSH_OPTS+=(-o BatchMode=yes)

pssh() { ssh "${SSH_OPTS[@]}" "${PRINTER_USER}@${PRINTER_IP}" "$@"; }
# Root commands. After "setup", a sudoers rule allows exactly this command without a
# password; before that, -tt lets sudo ask for it (stock Qidi image: "makerbase").
proot() { ssh -tt "${SSH_OPTS[@]}" "${PRINTER_USER}@${PRINTER_IP}" sudo /bin/bash "${PRINTER_WORK}/q2-printer.sh" "$@"; }

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
        # One directory per MCU with klipper.bin + klipper.dict: flashtool then also checks
        # that the image was built for the MCU it is writing to
        local m stage
        stage="$(mktemp -d)"
        for m in main thr box; do
            mkdir -p "${stage}/${m}"
            cp "${FIRMWARE_DIR}/q2-${m}.bin" "${stage}/${m}/klipper.bin"
            cp "${FIRMWARE_DIR}/q2-${m}.dict" "${stage}/${m}/klipper.dict"
        done
        (cd "$stage" && sha256sum ./*/klipper.bin ./*/klipper.dict > SHA256SUMS)
        pssh "rm -rf ${PRINTER_WORK}/firmware && mkdir -p ${PRINTER_WORK}/firmware"
        scp -q -r "${SSH_OPTS[@]}" "$stage"/* "${PRINTER_USER}@${PRINTER_IP}:${PRINTER_WORK}/firmware/"
        rm -rf "$stage"
        pssh "cd ${PRINTER_WORK}/firmware && sha256sum -c --quiet SHA256SUMS" \
            || die "firmware copy on the printer is corrupted"
    fi
}

# SSH key, current scripts on the printer, then the sudo rule for q2-printer.sh: the
# printer's sudo password is asked once here, every later step runs without it.
printer_prepare() {
    printer_ssh_key
    printer_push
    if ! pssh "sudo -n /bin/bash ${PRINTER_WORK}/q2-printer.sh status" >/dev/null 2>&1; then
        info "Allowing ${PRINTER_USER} to run q2-printer.sh as root (printer sudo password, asked once)"
        proot sudoers
    fi
}

# First conversion only: fetch and verify the pinned Katapult deployers, copy them over.
printer_fetch_deployers() {
    local tmp
    tmp="$(mktemp -d)"
    curl -fsSL "$DEPLOYER_URL" -o "${tmp}/deployer.tgz"
    echo "${DEPLOYER_SHA256}  ${tmp}/deployer.tgz" | sha256sum -c --quiet || die "deployer archive checksum mismatch"
    tar xzf "${tmp}/deployer.tgz" -C "$tmp"
    echo "${DEPLOYER_MCU_SHA256}  ${tmp}/mcu-deployer.bin" | sha256sum -c --quiet || die "mcu-deployer checksum mismatch"
    echo "${DEPLOYER_THR_SHA256}  ${tmp}/thr-deployer.bin" | sha256sum -c --quiet || die "thr-deployer checksum mismatch"
    echo "${DEPLOYER_MMU_SHA256}  ${tmp}/mmu-deployer.bin" | sha256sum -c --quiet || die "mmu-deployer checksum mismatch"
    scp -q "${SSH_OPTS[@]}" "$tmp"/*-deployer.bin "${PRINTER_USER}@${PRINTER_IP}:${PRINTER_WORK}/deployer/"
    rm -rf "$tmp"
}

# Firmware phase: optional Katapult deploy (first conversion), then Klipper on all three
# MCUs, in a single root session on the printer (one sudo password prompt).
printer_convert() {
    local deploy="${1:-}"
    if [ "$deploy" = deploy ]; then
        cat <<EOF

${C_WARN}First conversion: Katapult bootloader on the three MCUs${C_OFF}
Qidi's own update scripts flash a Katapult "deployer" (n3oney/qidi-q2-klipper) while the
stock firmware still runs. Afterwards Katapult replaces Qidi's bootloader: Qidi's firmware
can still be flashed back through Katapult (docs/recovery.md), but recovering from a power
cut during THIS step needs an ST-Link.
  - keep the printer powered and connected the whole time
  - one MCU at a time; each one is checked before the next
EOF
        confirm_phrase "INSTALL KATAPULT"
    fi
    cat <<EOF

${C_WARN}Flashing Klipper ($(firmware_id)) on mainboard, toolhead and Qidi Box${C_OFF}
Each MCU is put into Katapult and its application offset is checked before writing.
EOF
    # Never skipped, not even with --yes
    confirm_phrase "FLASH"
    if [ -n "$(systemctl list-unit-files klipper.service --no-legend 2>/dev/null)" ]; then
        sudo systemctl stop klipper q2-serial-bridge@main:7001 q2-serial-bridge@thr:7002 q2-serial-bridge@mmu:7003 2>/dev/null || true
    fi
    # shellcheck disable=SC2086  # $deploy is empty or one word
    proot convert "$(firmware_id)" $deploy || die "firmware phase failed; see docs/recovery.md"
    ok "all MCUs on firmware $(firmware_id)"
}

printer_firmware_id() { pssh "cat ${PRINTER_WORK}/firmware-id 2>/dev/null" || true; }

printer_proxies() {
    proot setup "$HOST_IP"
}

# Point HelixScreen (the touchscreen UI) at the host's Moonraker, installing it if needed.
printer_helixscreen() {
    local settings="/home/${PRINTER_USER}/helixscreen/config/settings.json"
    if ! pssh "test -f ${settings}"; then
        confirm "Install HelixScreen on the printer touchscreen (stock Qidi UI needs a local Klipper)?" y || return 0
        info "Installing HelixScreen on the printer: download and setup take a few minutes; its installer may ask for the printer sudo password"
        pssh -t "curl -sSL https://releases.helixscreen.org/install.sh | sh" \
            || { warn "HelixScreen install failed; run it later on the printer"; return 0; }
        pssh "test -f ${settings}" || {
            warn "HelixScreen: in its first-run wizard, set Moonraker to ${HOST_IP}:7125"; return 0; }
    fi
    pssh "python3 - ${settings} ${HOST_IP}" <<'EOF' || { warn "could not update ${settings}: set Moonraker to ${HOST_IP}:7125 in HelixScreen"; return 0; }
import json, sys
path, host = sys.argv[1], sys.argv[2]
data = json.load(open(path))
printers = data.get('printers') or {}
for p in (printers.values() if printers else [data]):
    p['moonraker_host'] = host
    p['moonraker_port'] = 7125
json.dump(data, open(path, 'w'), indent=2)
EOF
    proot helixscreen-restart || true
    ok "HelixScreen -> Moonraker ${HOST_IP}:7125"
}

