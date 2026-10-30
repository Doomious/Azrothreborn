# AzrothReborn

Unreal Engine project (World Partition) — world map blockout and the Starfall Crater region.

## Getting started

1. Install [Git LFS](https://git-lfs.com) and run `git lfs install` once.
2. Clone: `git clone https://github.com/Doomious/Azrothreborn.git`
3. Add the third-party asset packs below to `Content/` (see next section).
4. Open `AzrothReborn.uproject`.

## Third-party asset packs (not in this repo)

These Fab/Marketplace packs are licensed per user and can't be redistributed, so they are
git-ignored. Add each one to the project from your own Fab library, keeping the folder name:

| Folder under `Content/` |
|---|
| `Clouds_Tunnel_Loop` |
| `Megaplant_Library` |
| `PN_GrassLibrary` |
| `PN_Fern` |
| `PN_GroundFoliage` |
| `JustBStudios` |
| `FC_Coastal_Landscape` |
| `Fab` |
| `Arapaima_Gigas` |
| `MuddyGroundPack` |
| `Medieval_Campfire` |

Levels that use these assets will show missing references until the packs are installed.

## Layout

- `Content/Maps`, `Content/Blockout`, `Content/StarfallCrater` — project content
- `Content/__ExternalActors__`, `__ExternalObjects__` — World Partition one-file-per-actor data
- `SourceArt/` — heightmaps, splat/density maps, renders, and the Python tools in `SourceArt/WorldMap/Tools` that generate them

## Working together

`.uasset`/`.umap` files are binary and can't be merged. They're marked lockable in Git LFS —
run `git lfs lock <file>` before editing a map or asset and `git lfs unlock <file>` after pushing.

## Maps

- `/Game/Maps/StarfallCrater_WP` — main map (World Partition). Props, foliage chunks, ruins, town plots and FX stream in
  within 256 m of the player; terrain, water, sky and lighting are always loaded. Open regions from the World Partition window.
- `/Game/Maps/StarfallCrater` — older non-streaming version, kept as a fallback.

## Crater build pipeline

1. `SourceArt/WorldMap/Tools/build_crater_v2.py <v2 dir> Saved/Crater` — generates terrain, water, splats, town/village
   plots and placement data (needs numpy, scipy, Pillow, matplotlib).
2. `flip_obj_y.py <v2>/Terrain <v2>/Water` (required — the OBJ importer mirrors Y), then `pack_crater_masks.py <v2>`.
3. In the editor console: `py "<project>/SourceArt/WorldMap/Tools/crater_build.py" <stages...>` — see the stage list at the
   bottom of the script. Full streaming-map build: `wpmap`, then
   `terrain water rocks ruins foliage outposts emitters fx swim towns night fogmist cull stream save`.

Fog of war and ground mist are tuned in `/Game/StarfallCrater/FX/MPC_FogOfWar` (fog of war only runs during play).
