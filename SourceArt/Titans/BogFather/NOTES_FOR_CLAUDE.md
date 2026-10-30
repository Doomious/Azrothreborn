# Notes for Claude - BogFather

- Import: new skeleton, mesh + 27 anims, scale x80, no AnimBP (assets only).

## Placement / World Context (for Claude)

**BogFather belongs in the Starfall Crater area.** He is meant to roam Starfall Crater (`SourceArt/Regions/StarfallCrater/`) - NOT the other world zones (Stormreach Isles, Frostpeak, Emberwood, Mosswarden, etc.).

When importing or wiring him later:
- Place spawns / roam volumes / patrol paths inside the Starfall Crater region only.
- Treat him as the crater's resident Titan (roaming boss/world threat), using the crater heightmap for nav and ground alignment.
- Don't auto-place him in other zones or the open world map.
