# BogFather Titan Anim Pack (v1)

- Main file: `BogFather_AnimPack_UE.fbx` — mesh + armature + 27 animations (textures embedded)
- Import into UE with **new skeleton**, mesh + animations, **scale x80** (native ~1 m)
- No AnimBP / character BP included — assets only, not wired
- Source: `BogFather_anim_pack.blend`, `blend/`, `src/` (Tripo originals), zip of all
- See `ANIM_PACK_MANIFEST.md` for clip list + AnimNotify suggestions

## Placement / World Context (for Claude)

**BogFather belongs in the Starfall Crater area.** He is meant to roam Starfall Crater (`SourceArt/Regions/StarfallCrater/`) - NOT the other world zones (Stormreach Isles, Frostpeak, Emberwood, Mosswarden, etc.).

When importing or wiring him later:
- Place spawns / roam volumes / patrol paths inside the Starfall Crater region only.
- Treat him as the crater's resident Titan (roaming boss/world threat), using the crater heightmap for nav and ground alignment.
- Don't auto-place him in other zones or the open world map.
