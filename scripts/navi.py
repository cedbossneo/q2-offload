#!/usr/bin/env python3
"""Mainsail sidebar links (.theme/navi.json) for the selected q2-offload components.

Usage: navi.py <components> <host-ip> <fluidd-port>
"""
import json
import sys

# Material Design Icons paths (pictogrammers.com, Apache-2.0)
ICON_CHART = ("M4 19V20H22V22H2V2H4V17C7 17 10 15 12.1 11.4C15.1 6.4 18.4 4 22 4V6"
              "C19.2 6 16.5 8.1 13.9 12.5C11.3 16.6 7.7 19 4 19Z")
ICON_SHIELD = ("M21,11C21,16.55 17.16,21.74 12,23C6.84,21.74 3,16.55 3,11V5L12,1L21,5V11"
               "M12,21C15.75,20 19,15.54 19,11.22V6.3L12,3.18L5,6.3V11.22C5,15.54 8.25,20 12,21"
               "M10,17L6,13L7.41,11.59L10,14.17L16.59,7.58L18,9")
ICON_SPOOL = ("M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2"
              "M12,4A8,8 0 0,1 20,12A8,8 0 0,1 12,20A8,8 0 0,1 4,12A8,8 0 0,1 12,4"
              "M12,9A3,3 0 0,0 9,12A3,3 0 0,0 12,15A3,3 0 0,0 15,12A3,3 0 0,0 12,9Z")


def main():
    components = set(sys.argv[1].split(','))
    host, fluidd_port = sys.argv[2], sys.argv[3]
    base = "http://%s" % host
    links = []
    if 'autopa' in components:
        # autopa is served under /autopa/ by the same nginx as the web clients
        port = "" if fluidd_port == "80" else ":%s" % fluidd_port
        links.append({"title": "AutoPA", "href": "%s%s/autopa/" % (base, port), "icon": ICON_CHART})
    if 'printguard' in components:
        links.append({"title": "PrintGuard", "href": "%s:8000/" % base, "icon": ICON_SHIELD})
    if 'spoolman' in components:
        links.append({"title": "Spoolman", "href": "%s:7912/" % base, "icon": ICON_SPOOL})
    for i, link in enumerate(links):
        link.update(target="_blank", position=85 + i)
    json.dump(links, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == '__main__':
    main()
