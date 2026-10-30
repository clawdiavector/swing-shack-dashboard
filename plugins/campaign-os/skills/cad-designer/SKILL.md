---
name: cad-designer
description: >-
  3D designer for Campaign OS: build a true-scale 3D scene in metres (a Swing Shack simulator bay,
  a Stick fitting space, a golfer, a screen with the real logo, products at their real size) and
  render it from any camera (isometric, floor plan, elevation, perspective) in blueprint, plan or
  clay style. Use the render as a "building plan" post, or as the exact layout and perspective
  Krea paints a realistic or illustrated version on. Load when someone asks for a 3D render, a
  3D sketch, a floor plan, a blueprint or building-plan look, an isometric view, a layout of the
  bays or the shop, 3D illustrations of clubs, swings or movements, or wants to place a golfer,
  logo or product precisely in a space.
---

# 3D designer (CAD-lite)

Started 30 Oct 2026 from Christelle's idea: model the Swing Shack bays once in 3D, then "fill in
whatever and wherever we want": a building-plan look around a sketched bay, the golfer, the floor
and the screen with a Swing Shack logo design on the wall, 3D illustrations of clubs, swings and
movement.

It's a small Python renderer (`scripts/cad3d.py`, Pillow and numpy only, no Blender needed). Scenes
are built from real dimensions in metres, so everything is to scale by construction, and the same
scene renders from any camera in any style, deterministically, in about a second.

## Rules

- **The venue is real.** A bay or shop drawn as ours uses Swing Shack's or Stick's measured
  dimensions. Until they're measured, renders carry the line "Placeholder dimensions: TrackMan's
  recommended single bay" (4.6 m wide, 5.5 m deep, 3.1 m high, ball about 2.5 m from the screen;
  [TrackMan tech specs](https://trackman.com/golf/simulator/tech-specs)). Pass `--measured` only
  with real numbers.
- **Real-world scale everywhere.** People, clubs, balls and bags use the sizes in
  `campaign-os-carousel/real-sizes.json`. Anything real-looking made from a render passes the
  `reality-check` skill.
- **Real marks only.** Logos come from `data/brand-directory/<brand>/logos/`, never redrawn.
- **Brands stay separate:** a Swing Shack scene is Swing Shack only.

## Make a scene

```bash
python3 plugins/campaign-os/skills/cad-designer/scripts/swing_shack_bay.py --out out/ \
    [--width 4.6 --depth 5.5 --height 3.1 --ball-to-screen 2.5] [--measured]
```

writes `bay_blueprint_iso.png`, `bay_plan.png` and `bay_clay_persp.png` (1080x1350). For anything
else, build a scene in a few lines:

```python
import cad3d as c
from cad3d import V
s = c.Scene()
s.solids.append(c.box(0, 0, -0.05, 4.6, 5.5, 0, fill=(96, 150, 78), name="floor"))  # x across, y to the screen, z up
s.capsules += c.golfer((2.6, 3.0), "address")          # poses: address, top, impact, finish
s.decals.append(c.Decal(logo_image, [bottom_left, bottom_right, top_right, top_left]))
s.dims.append(c.Dim(V([0, 0, 0]), V([4.6, 0, 0]), V([0, -0.6, 0])))   # dimension line, labelled in metres
c.render(s, c.Camera("iso", yaw=-35, pitch=32), style="blueprint").save("bay.png")
```

| Camera | Use |
|---|---|
| `iso` | the "building plan" isometric; `yaw` turns it, `pitch` 35.26 is true isometric |
| `plan` | top-down floor plan |
| `front`, `side` | elevations |
| `persp` | a real camera: `eye`, `target`, `fov` (use the eye height of a person, about 1.6 m) |

| Style | Look |
|---|---|
| `blueprint` | white lines on navy, 50 cm grid, dimension lines |
| `plan` | dark lines on paper |
| `clay` | flat-lit solid faces, for layout and as a Krea reference |

## Make it a post

1. **Building-plan post:** render `blueprint` or `plan`, add the headline in the brand's type
   (Swing Shack: Montserrat Black Italic), one idea, one ask. The render itself is the design.
2. **Realistic or illustrated:** render `clay` from the camera you want, upload it to Krea and ask
   Nano Banana Pro to keep the exact layout, perspective and proportions while making it
   photographic or illustrated; add the generated golfer there. The 3D render fixes where things
   are and how big; Krea only paints. Then run `reality-check` and put the real logo and products
   on top (layering).
3. **Movement:** `swing_sequence.py` draws a whole swing as one picture: the seven positions as
   ghost arms and club around one solid golfer, with the hand path and the club-head path as arcs
   in the brand accent.

   ```bash
   python3 plugins/campaign-os/skills/cad-designer/scripts/swing_sequence.py --out out/ \
       --view faceon|dtl [--style blueprint|plan] [--brand swing-shack|stick]
   ```

   Keep any number on screen to a sourced fact; the picture says it's an illustration.

## The swing model: real anatomy

The golfer is built from published human measurements, all in `anatomy.json` with their sources:

- **Bones** are de Leva's (1996) segment lengths and **widths, girths and the head** are ANSUR II means
  (4,082 men), scaled to a 1.75 m golfer (`cad3d.STATURE`). Limbs taper like real ones: thighs to the
  knee, a calf belly, forearms to the wrist.
- **Joints only bend the way they can,** inside the AAOS ranges: elbows 0-150, knees 0-135 and over the
  toes, the wrist cocks only by radial and ulnar deviation (20 + 30), forearms roll up to 80 each way.
  Shoulder blades slide round the ribs so the trail arm can reach the grip.
- **The swing** has a tour player's 41.5 degree forward bend at address, a pelvis turn of 35-55 and a thorax
  turn of 85-110 at the top (X-factor 43-64), and a downswing that unwinds pelvis first, then thorax, then
  arm, then club (the kinematic sequence).
- **Muscles** (`cad3d.muscles`) run origin to insertion, keep their volume (a shortening muscle gets
  thicker) and are marked working only where an EMG study says so: the downswing from Bechler et al. 1995
  and Jobe, Perry & Pink 1989, impact from the 2012 EMG review. No source, no red muscle.

```bash
python3 plugins/campaign-os/skills/cad-designer/scripts/swing_muscles.py --out out/     --pose top|downswing|impact [--view faceon|dtl]
```

draws the golfer with the working muscles in red and the stretched ones in blue, naming the study on the
image. `swing_rig(ball, pose)` returns the joints, `golfer(ball, pose)` the body, `muscle_bands(ball, pose)`
the muscles for `Scene.bands`. Positions live in `POSES` (pelvis, thorax, arm, lift, hinge, roll, elbow,
tilt, side, shift, squat, heel, pro). Tests pin all of it (`test_cad_designer_anatomy_20261030.py`,
`test_cad_designer_swing_20261030.py`).

## Limits (be honest about them)

- **The golfer is a mannequin.** Proportions, joints, turn and muscles are real, but it reads as a
  figure, not a person. For finished
  posts the golfer comes from Krea, placed where the render puts him. It is a right-handed golfer
  only, and the swing is an illustration, not a measured swing.
- **The top is a three-quarter swing.** With the wrist kept to side-to-side cocking (20 + 30 degrees) the
  club stops short of level at the top. Real golfers also bend the lead wrist back (extension) to get
  there; that is not modelled yet. The finish is the least real position.
- **No curves, textures or club heads yet:** boxes, flat quads, capsules and image decals only.
  3D club illustrations need a parametric club (head, loft, lie, length from real specs) first.
- **Painter's-algorithm drawing:** big faces that cut through each other can draw in the wrong
  order. Split them into smaller boxes if a render looks wrong.
- **Not built yet:** loading real 3D models (Krea `generate_3d` produces GLB files; reading them
  needs a mesh library), animation to video.

## Measurements still needed (Swing Shack)

Bay width, depth and ceiling height; screen size and height off the floor; where the ball sits;
where the TrackMan unit is mounted; wall and floor finish. One bay measured once makes every render
real.
