# BogFather animated import
Source: tripo_convert_a2f73b5e...fbx (Tripo, UE-rigged, 809 fcurves/action). Scene fps 30 assumed.
| Original | Frames | Titan copy | Frames |
|---|---|---|---|
| Armature|angry_02 | 1-53 | Titan_Armature|angry_02 | 6.3-333.9 |
| Armature|run | 1-31 | Titan_Armature|run | 6.3-195.3 |
| Armature|standing_relax | 1-423 | Titan_Armature|standing_relax | 6.3-2664.9 |
| Armature|walk | 1-57 | Titan_Armature|walk | 6.3-359.1 |
Method: copied each Action, multiplied all keyframe + handle times by 6.3 (sqrt(80/2)). Originals untouched, fake-user on all. Scene fps NOT changed.
TODO refine: sharpen foot plants (contacts fast), keep secondaries (moss/vines) near normal speed; shift start to frame 1.
Texture packed to Principled Base Color. Empty Scale_Note_80m: native ~1 m -> x80.
