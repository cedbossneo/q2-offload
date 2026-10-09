import sys, os, argparse
ap=argparse.ArgumentParser(); ap.add_argument('-d'); ap.add_argument('-b'); ap.add_argument('-f'); ap.add_argument('-r',action='store_true'); ap.add_argument('-s',action='store_true')
a=ap.parse_args()
log=open('/tmp/flashtool.log','a'); log.write(' '.join(sys.argv[1:])+'\n')
types={'main':('stm32f407xx','0x8008000'),'box':('stm32f401xc','0x8004000'),'thr':('stm32f103xe','0x8002000')}
def which(d):
    if 'ttyS4' in d: return 'thr'
    return 'main' if 'f407' in d else 'box'
m=which(a.d)
if a.r:
    if m!='thr' and 'Klipper' in a.d:
        os.rename(a.d, a.d.replace('usb-Klipper','usb-katapult'))
    sys.exit(0)
if a.s:
    if 'Klipper' in a.d: print('Device is not Katapult'); sys.exit(1)
    if m=='thr' and os.path.exists('/tmp/thr-stock'): print('timeout'); sys.exit(1)
    t,o=types[m]
    print(f"Detected Bootloader: Katapult\nApplication Start: {o}\nMCU type: {t}"); sys.exit(0)
if a.f:
    print('Programming Complete')
    if m!='thr': os.rename(a.d, a.d.replace('usb-katapult','usb-Klipper'))
