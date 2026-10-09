#!/usr/bin/env bash
# Simulated flash of a stock printer and of an already converted one, with fake serial
# devices and a fake flashtool.py (tests/flash-sim/flashtool.py). Runs as root in a
# throwaway Debian container: it creates /dev/serial/by-id entries and a user "mks".
# Usage: tests/flash-sim/run.sh <repo> <firmware-dir>
set -euo pipefail
REPO="${1:?repo}"; FW="${2:?firmware dir}"
command -v fuser >/dev/null || { apt-get update -qq >/dev/null; apt-get install -y -qq --no-install-recommends python3 psmisc sudo >/dev/null; }
useradd -m mks; W=/home/mks/q2-offload; mkdir -p $W/firmware $W/deployer /dev/serial/by-id
cp "$REPO/printer/q2-printer.sh" $W/; cp "$REPO/tests/flash-sim/flashtool.py" $W/flashtool.py
for m in main thr box; do mkdir -p $W/firmware/$m; cp "$FW/q2-$m.bin" $W/firmware/$m/klipper.bin; cp "$FW/q2-$m.dict" $W/firmware/$m/klipper.dict; done
for f in mcu thr mmu; do echo x > $W/deployer/$f-deployer.bin; done
# stock scripts: turn a stock device into katapult
printf 'mv /dev/serial/by-id/usb-Klipper_stm32f407xx_X-if00 /dev/serial/by-id/usb-katapult_stm32f407xx_X-if00\n' > /home/mks/mcu_update.sh
printf 'rm -f /tmp/thr-stock\n' > /home/mks/mcu_update_THR.sh
printf 'mv "$2" /dev/serial/by-id/usb-katapult_stm32f401xc_Y-if00\n' > /home/mks/mcu_update_BOX_to_v2.sh
rm -f /dev/ttyS4; touch /dev/ttyS4
echo "== scenario 1: first conversion (stock), deploy + flash"
touch /dev/serial/by-id/usb-Klipper_stm32f407xx_X-if00 /dev/serial/by-id/usb-Klipper_QIDI_BOX_V2_Y-if00 /tmp/thr-stock
bash $W/q2-printer.sh convert TESTID deploy
ls /dev/serial/by-id; [ "$(cat $W/firmware-id)" = TESTID ]
echo "== scenario 2: update (already Klipper + Katapult), re-run deploy is skipped"
out="$(bash $W/q2-printer.sh convert TESTID2 deploy)"; echo "$out"
[ "$(echo "$out" | grep -c "skipping the deployer")" = 3 ] || { echo "FAIL: deployer re-run on a converted MCU"; exit 1; }
echo "== scenario 3: swapped image is refused"
cp $W/firmware/box/klipper.dict $W/firmware/main/klipper.dict
if bash $W/q2-printer.sh flash main $W/firmware; then echo "FAIL: flashed a box image on the mainboard"; exit 1; fi
echo "refused as expected"
echo "== sudoers rule"
bash $W/q2-printer.sh sudoers
cat /etc/sudoers.d/q2-offload
su mks -c "sudo -n /bin/bash $W/q2-printer.sh detect" >/dev/null || { echo "FAIL: passwordless rule does not match"; exit 1; }
if su mks -c "sudo -n /bin/true" 2>/dev/null; then echo "FAIL: rule is too broad"; exit 1; fi
echo "== flashtool calls"; cat /tmp/flashtool.log
echo "flash simulation OK"
