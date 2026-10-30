# BogFather Titan Anim Pack — manifest

Rig: Tripo UE5-named armature (80 bones, unchanged). 24 fps. Native 1 m (scale ×80 in UE). FBX: -Y forward, Z up, no leaf bones, all actions baked, textures embedded.

| Action | Frames | Source | Quality | Notes |
|---|---|---|---|---|
| Armature|walk | 1–57 | tripo | solid | original Tripo clip (24 fps, 1 m native) |
| Titan_Armature|walk | 6–359 | derived | usable | uniform ×6.3 stretch (earlier pass); prefer Titan_Walk/Idle below |
| Armature|run | 1–31 | tripo | solid | original Tripo clip (24 fps, 1 m native) |
| Titan_Armature|run | 6–195 | derived | usable | uniform ×6.3 stretch (earlier pass); prefer Titan_Walk/Idle below |
| Armature|standing_relax | 1–423 | tripo | solid | original Tripo clip (24 fps, 1 m native) |
| Titan_Armature|standing_relax | 6–2665 | derived | usable | uniform ×6.3 stretch (earlier pass); prefer Titan_Walk/Idle below |
| Armature|angry_02 | 1–53 | tripo | solid | original Tripo clip (24 fps, 1 m native) |
| Titan_Armature|angry_02 | 6–334 | derived | usable | uniform ×6.3 stretch (earlier pass); prefer Titan_Walk/Idle below |
| Titan_Walk | 1–354 | derived (tripo walk) | usable | ×6.3 primary, starts f1, loop closed; plant sharpen still TODO |
| Titan_Idle | 1–1267 | derived (standing_relax) | solid | ×3 (idle breathing already slow), loop closed |
| Titan_RunHeavy | 1–136 | derived (tripo run) | usable | ×4.5 (lumbering run), loop closed; add lean/plant later |
| Titan_WalkStart | 1–200 | authored (idle→walk) | usable | long inertia ease-in; blends into Titan_Walk |
| Titan_WalkStop | 1–210 | authored (walk→idle) | usable | overshoot + settle, hard to stop |
| Titan_Turn_L | 1–241 | authored (walk legs + root yaw) | usable | 90° in-place root yaw, head/torso lead; feet slide a bit |
| Titan_Turn_R | 1–241 | authored (walk legs + root yaw) | usable | 90° in-place root yaw, head/torso lead; feet slide a bit |
| Titan_Strafe_L | 1–361 | authored (walk w/ hip yaw) | stub | lower body walks sideways, torso counter-yawed; needs real crossover steps |
| Titan_Strafe_R | 1–361 | authored (walk w/ hip yaw) | stub | lower body walks sideways, torso counter-yawed; needs real crossover steps |
| Titan_Backstep | 1–181 | authored (walk reversed) | usable | walk sampled backwards, back lean |
| Titan_Roar | 1–310 | authored (angry_02 base) | usable | crouch wind-up → chest out, arms wide, head back |
| Titan_Stomp | 1–210 | authored | usable | slow raise (80f) → 8f slam = impact frame 88 (UE notify) |
| Titan_Swipe_Ground | 1–250 | authored | usable | R-arm low sweep, contact f110–118 |
| Titan_Swipe_Air | 1–240 | authored | usable | overhead R swipe, contact f110–118 |
| Titan_Grab_Ground | 1–300 | authored | stub-usable | bend + R-hand grab f145 (attach notify), ends holding at chest; hand only reaches ~knee height — deepen bend |
| Titan_Throw | 1–260 | authored | usable | starts holding (chain after Grab), release f118 |
| Titan_Loom_Defeat | 1–420 | authored | usable | 180° turn → loom over downed foe, hold breathing |
| Titan_Hit_React | 1–130 | authored | usable | fast 4f jolt (impact must read fast), slow recovery |
| Titan_Fall_Defeated | 1–260 | authored | stub-usable | topples backward via root pitch, ground impact f172 + bounce; may clip ground — tune in UE |

Impact frames for UE AnimNotifies: Stomp f88, Swipe_Ground f110, Swipe_Air f110, Grab f145, Throw release f118, Hit_React f5, Fall ground f172.
Known TODO: foot-plant sharpening on Titan_Walk/RunHeavy, real crossover steps for strafes, secondary (moss/vines) timing not separable on this rig.