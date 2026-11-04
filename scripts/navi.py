#!/usr/bin/env python3
"""Mainsail sidebar links (.theme/navi.json): the Box page and the selected q2-offload components.

Usage: navi.py <components> <host-ip> <web-port> [box|nobox]

Links are relative: they open on the address and port the browser used for Mainsail (a LAN
name, a VPN address...), not on HOST_IP, which is the host's address on the printer link.
<host-ip> and <web-port> are accepted for compatibility and unused.
"""
import json
import sys

# Material Design Icons paths (pictogrammers.com, Apache-2.0)
ICON_CHART = ("M4 19V20H22V22H2V2H4V17C7 17 10 15 12.1 11.4C15.1 6.4 18.4 4 22 4V6"
              "C19.2 6 16.5 8.1 13.9 12.5C11.3 16.6 7.7 19 4 19Z")
ICON_EYE = ("M12,9A3,3 0 0,0 9,12A3,3 0 0,0 12,15A3,3 0 0,0 15,12A3,3 0 0,0 12,9M12,17A5,5 0 0,1 7,12"
            "A5,5 0 0,1 12,7A5,5 0 0,1 17,12A5,5 0 0,1 12,17M12,4.5C7,4.5 2.73,7.61 1,12C2.73,16.39 7,19.5 12,19.5"
            "C17,19.5 21.27,16.39 23,12C21.27,7.61 17,4.5 12,4.5Z")
ICON_WATER = ("M12,20A6,6 0 0,1 6,14C6,10 12,3.25 12,3.25C12,3.25 18,10 18,14A6,6 0 0,1 12,20Z")
ICON_SPOOL = ("M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2"
              "M12,4A8,8 0 0,1 20,12A8,8 0 0,1 12,20A8,8 0 0,1 4,12A8,8 0 0,1 12,4"
              "M12,9A3,3 0 0,0 9,12A3,3 0 0,0 12,15A3,3 0 0,0 15,12A3,3 0 0,0 12,9Z")


def main():
    components = set(sys.argv[1].split(','))
    box = (sys.argv[4] if len(sys.argv) > 4 else 'box') != 'nobox'
    # Every nginx server of the web clients serves these pages (q2-offload-common.conf);
    # /spoolman redirects to port 7912 on the host name the browser used
    links = []
    if box:
        links.append({"title": "Box drying", "href": "/box/", "icon": ICON_WATER})
    if 'autopa' in components:
        links.append({"title": "AutoPA", "href": "/autopa/", "icon": ICON_CHART})
    if 'detect' in components:
        links.append({"title": "Failure detection", "href": "/detect/", "icon": ICON_EYE})
    if 'spoolman' in components:
        links.append({"title": "Spoolman", "href": "/spoolman", "icon": ICON_SPOOL})
    for i, link in enumerate(links):
        link.update(target="_blank", position=85 + i)
    json.dump(links, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == '__main__':
    main()
