import os, sys
# Fake of printer/q2_stock_reset.py: the stock MCU reboots into Qidi's bootloader
BOOT = {'02.01': 'usb-x_DRIVER_BOOT_X', 'f407': 'usb-x_DRIVER_BOOT_X', 'VCP': 'usb-STM_Virtual_ComPort_Y',
        'QIDI_BOX': 'usb-MKS_COLOR_BOOT_Y', 'f401': 'usb-MKS_COLOR_BOOT_Y'}
device = sys.argv[1]
for key, name in BOOT.items():
    if key in device:
        os.rename(device, '/dev/serial/by-id/' + name)
        break
