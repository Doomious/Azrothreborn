# World regions

The world map `/Game/azrothreborn` (16.1 × 10.6 km) is split into the 11 Titan Walks regions so several people can
build at once on separate PCs. The world is World Partition with one file per actor, so as long as each person only
changes actors in their own region, nobody edits the same file and branches merge cleanly.

Region outlines are the zone polygons from `SourceArt/WorldMap/Tools/generate_world_maps.py` (the same ones that
produced `SourceArt/WorldMap/Output/Zones.png`). Titans and biome notes are in the Titan Walks spec
(`AzrothReborn_Titan_Walks_GitHub_Upload.zip` at the repo root).

| # | Region key | Titan | Actors | Centre (km) | Owner |
|---|---|---|---|---|---|
| 01 | `01_StormreachIsles` | Thal'Kor, the Stormwalker | 208 | 2.4, 2.1 | |
| 02 | `02_FrostpeakRange` | Vaelthir, the Glacier King | 1026 | 8.0, 1.2 | |
| 03 | `03_AshenWastes` | Vorr'Khal, the Spirestrider (provisional; pillarlands revision pending) | 715 | 13.6, 1.7 | |
| 04 | `04_SunscorchDesert` | Sah'Ruun, the Dune Sovereign | 733 | 13.6, 4.4 | |
| 05 | `05_EmberwoodForest` | Oru'Moss, the Elderwood Titan | 1986 | 4.2, 2.3 | |
| 06 | `06_StonevaleHighlands` | Khar'Voss, the Pillarbreaker | 973 | 2.6, 5.4 | |
| 07 | `07_EmberCoast` | Ael'Marin, the Tidebound | 496 | 3.2, 8.4 | |
| 08 | `08_MosswardenSwamps` | Mor'Vael, the Bogfather | 1231 | 7.5, 8.2 | |
| 09 | `09_HollowBlightLands` | Nhal'Veth, the Drowned Hollow (provisional; dark-swamp revision pending) | 724 | 11.7, 8.2 | |
| 10 | `10_VerdantIsles` | Elarion, the Verdant Guardian | 438 | 13.9, 8.2 | |
| 11 | `11_StarfallCraterRainforest` | Azh'Roth, the Firstborn | 2036 | 8.4, 4.5 | |

Fill in the Owner column when someone claims a region.

## What each region has

- **Editor data layer** `/Game/Maps/Regions/DL_<key>`: every actor in the region is in it. Editor data layers only
  control what loads in the editor; the game is unaffected.
- **Location volume** `Region_<key>` (outliner folder `Regions`): select it and press **Load** in its Details panel
  to load just that area.
- **Content folder** `Content/Regions/<key>/`: put new meshes, materials, blueprints, etc. for the region here.
- **Ownership table** `Docs/Regions/actor_owners.tsv`: every actor file in the map and which region (or `Shared`)
  owns it. `Docs/Regions/regions.json` has each region's outline and bounds in world centimetres.

An actor belongs to the region its bounds centre sits in. 150 actors are **Shared** because they span the whole world:
sky, sun, fog, clouds, ocean plane, sky sphere, the leftover landscape patch, HLODs, the minimap, the player start, the
data-layer list and the 11 region volumes.

## Working on a region

1. Clone the repo, `git lfs pull`, and add the third-party packs listed in the main README.
2. Open `/Game/azrothreborn`. In **Window > Data Layers Outliner**, untick *Loaded in editor* on every `DL_` layer
   except yours, then select your `Region_<key>` volume and press **Load** in its Details panel.
3. Right-click your data layer > **Make Current** so actors you place are added to it automatically.
4. Work on a branch named `region/<key>`, e.g. `git switch -c region/08_MosswardenSwamps`.
5. Install the commit check once: `Tools/region_check.sh 8 --install`. It stops a commit that touches another
   region's actors or shared files. Run `Tools/region_check.sh 8` any time to list what you have changed.
6. Push your branch and merge it into `main`. Pull `main` often so you see neighbouring regions' work.

## Rules

- Don't edit, move or delete actors that belong to another region; ask that region's owner. This includes actors
  that poke across your border.
- Don't change Shared actors, `Content/azrothreborn.umap` or `Content/Maps/Regions/` without telling everyone.
  In particular, only one agreed person rebuilds HLODs or the minimap, because that rewrites every HLOD actor.
- Keep new actors inside your region's outline. New actors aren't in the ownership table until someone re-runs the
  `manifest` stage below on `main`; until then the check lists them as `NEW ACTOR`.
- Shared assets outside `Content/Regions/<key>/` (packs, `Content/StarfallCrater`, `Content/Blockout`) are flagged
  `SHARED ASSET`; changing them affects every region, so coordinate first.

## Rebuilding the split

`SourceArt/WorldMap/Tools/regions_build.py` creates all of this. Run it inside the editor:

```
py "<project>/SourceArt/WorldMap/Tools/regions_build.py" manifest
```

Stages: `layers` (create and register the data layers), `assign` (put actors into their region's layer), `volumes`
(place the region volumes) and `manifest` (rewrite `regions.json` and `actor_owners.tsv`). Every stage can be re-run
safely. `assign` only touches actors that are not yet in their layer, but it does modify those actor files, so run it
on `main` when nobody else has unmerged map work.
