# Spools: NFC tags and Spoolman

The Qidi Box has two RC522 NFC readers (gates 0–1 and 2–3). Happy Hare reads the tag when a
spool is loaded and, with Spoolman installed, finds or creates the matching spool.

1. Use **NTAG215** stickers. Do not lock them.
2. Write the filament with an OpenSpool app (for example OpenSpool or SpoolFlux on a phone):
   brand, material, colour, temperatures. Use exactly the same brand and material spelling
   every time, or Spoolman gets duplicate filaments.
3. Stick the tag on the spool flange, on the side facing the neighbouring gate.
4. Load the spool. The first scan creates the vendor, filament (one per colour) and spool in
   Spoolman and stores the tag UID on the spool. Later scans of that tag select the spool.

When the brand, material and colour match an entry of SpoolmanDB (the filament database
built into Spoolman; the closest colour wins, so an app's colour picker is fine), the
filament gets the manufacturer's name, temperatures, density and spool weight, and a filament
already imported from SpoolmanDB in Spoolman is reused. Otherwise the filament is named after
its material and uses the tag's temperatures; rename it in Spoolman.

New spools are created with 1000 g: correct the weight in Spoolman for part-used spools.

A new spool whose filament has no pressure advance yet gets a calibration offer: see
[calibration.md](calibration.md#5-pressure-advance-autopa).

`MMU_NFC_SCAN GATE=n` turns the spool a full revolution to look for a tag the preload
did not see.
