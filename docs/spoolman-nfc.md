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

New spools are created with 1000 g: correct the weight in Spoolman for part-used spools.
Filaments created from tags are named after their material; rename them in Spoolman.

`MMU_NFC_SCAN GATE=n` turns the spool a full revolution to look for a tag the preload
did not see.
