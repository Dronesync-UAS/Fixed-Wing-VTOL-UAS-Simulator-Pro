# Image quality: what is actually wrong, and the durable options

12 October 2026

> "still not happy about the very poor quality of the image of the
> aircraft and environment ... i cant believe that gazebo is still used
> in 2026 with such poor design like video games from the 1980's. find
> durable options"

## First: Gazebo is not the main cause of what you are looking at

This was measured, not assumed. The three ground textures every world
uses:

| File | Size | Mean RGB | Spread |
|---|---|---|---|
| `flat_normal.png` | 256 x 256 | 128, 128, 255 | **0, 0, 0** |
| `grass_diffuse.png` | 256 x 256 | 193, 164, 119 | 19, 19, 19 |
| `ground_fine.png` | 1024 x 1024 | 180, 161, 125 | 136, 136, 135 |

Read those three rows carefully:

* **`flat_normal.png` has zero spread.** 128,128,255 with no variation
  is the definition of a FLAT normal map - it is the "no bump at all"
  value. Every heightmap world declares a normal map and that normal map
  does nothing. There is no surface relief anywhere in any world.
* **`grass_diffuse.png` has a spread of 19 out of 255.** That is
  effectively a flat colour with noise. It is 256 pixels square and it is
  tiled every 16 metres, so across an 8 km view it repeats about five
  hundred times. Five hundred repeats of a near-flat swatch is exactly
  the smear that reads as "1980s".
* The seven PLANE worlds - coast, airfield, estate, flood, forest,
  lowlands, flat_test - have **no ground texture at all**. Their ground
  is one flat colour.

And the aircraft and the scenery are untextured primitives: boxes,
cylinders and spheres with flat colours. `scenery.py` builds 40 to 130
of them per world. No textures, no materials, no meshes.

Gazebo Harmonic's renderer (ogre2) supports a full metal/roughness PBR
workflow with albedo, normal, roughness and metalness maps - the API is
documented in gz-rendering 9 and gz-common 5. **This project uses almost
none of it.** Two of the three textures it does use are placeholders.

So the honest finding: the renderer has capability this project has never
asked for. That is where the cheap, large improvement is.

## What can be done inside Gazebo, roughly in order of payoff

1. **Use the satellite imagery as the ground.** We already download
   1.4 m/pixel Mapbox imagery for all twelve areas and it is sitting in
   `sim/worlds/satellite/`. At the moment it is only drawn on the plan
   view. Laid on the ground as an albedo map over the central few
   kilometres, every world would show the real place from the air
   instead of a green swatch. This is the single biggest change
   available and the assets exist.
2. **Replace the two placeholder textures.** A real normal map and a
   real diffuse at 2k or 4k, from a CC0 source (Poly Haven, ambientCG).
   The flat normal map is a one-file fix that changes every heightmap
   world.
3. **Fix the tiling scale.** A detail texture at 16 m plus a macro
   texture at kilometre scale, blended, removes the repeat. Gazebo
   heightmaps take multiple `<texture>` blocks with blend heights.
4. **PBR on the aircraft.** Albedo, normal and roughness maps instead of
   flat colours. A VTOL that reads as a moulded composite airframe
   rather than a toy.
5. **Sky and atmosphere.** A real sky with cloud, and distance fog.
   Nothing says "game engine from decades ago" faster than a flat
   gradient to the horizon.
6. **Meshes for the scenery.** Buildings, trees and vehicles as actual
   models rather than boxes. Open libraries exist; licences need
   checking one by one.
7. **Camera settings.** Anti-aliasing on the camera sensors, and our own
   JPEG quality, which is currently 88 and is NOT the bottleneck - the
   content is.

Items 1 to 3 are days of work and would change the look of every
training area. Items 4 to 6 are weeks and are where "professional"
lives.

## If you want photorealism, the honest state of the art

Searched today. **Nothing open source gives photorealistic rendering,
PX4, and fixed-wing VTOL all three.** The near misses:

| Option | Photoreal | PX4 | Fixed-wing VTOL | Licence |
|---|---|---|---|---|
| **Pegasus Simulator** on NVIDIA Isaac Sim | yes | yes | **no - multirotor only, by its own documentation** | BSD-3; Isaac Sim free for individuals |
| **Colosseum** (community AirSim fork, Unreal Engine 5) | yes | yes (SITL) | **unconfirmed** | MIT-ish, inherits AirSim |
| **AirSim** (Microsoft) | yes | yes | unconfirmed | archived by Microsoft |
| **FlightForge** (2025) | yes, plus procedural environments | unconfirmed | unconfirmed | open source |
| **Gazebo Harmonic** (what we use) | no - a 2025 paper says plainly it "lacks photorealistic rendering" | yes | **yes** | Apache 2.0 |

Pegasus is the one everybody recommends and it cannot fly our aircraft:
only multirotors are supported, with other topologies listed as future
work. That is the single most important fact on this page.

Isaac Sim also has a performance cost worth knowing: a user report on
NVIDIA's own forum has a two-drone example at 55-60 fps dropping to
about 12 fps with three cameras and a lidar on one drone. We run three
cameras and a lidar.

## The structural point that protects the work either way

The instructor station talks **MAVLink to PX4** and reads **camera
topics from Gazebo**. PX4 is the flight model, and PX4 does not change
in any of the options above - it is the common element in all of them.

So if the renderer is ever replaced, what has to be rewritten is the
camera subscription in `video_feed.py` and the Gazebo service calls in a
handful of plugins. The flight commands, the console, the payload
screen, the flight log, the mission planner, the limits and the training
record all survive untouched. None of that work is at risk from this
decision.

## Recommendation

Two tracks, in this order.

**Now, in Gazebo:** items 1 to 3 above. The satellite imagery is already
on disk and the flat normal map is a one-file replacement. This is days,
not weeks, and it will change what the CEO sees.

**In parallel, evaluated not adopted:** stand up Colosseum on Unreal
Engine 5 against PX4 SITL and find out whether it will fly a
standard_vtol at all. That is the question that decides whether a
photoreal version of this trainer is possible, and it has a yes/no
answer that a day's work would settle. Do not commit to it before that
answer exists.

**What I would not do:** move to Isaac Sim. It is the most photorealistic
option and it cannot fly a fixed-wing VTOL today.

## Sources

- Pegasus Simulator: https://github.com/PhoenixAI-LLC/PegasusSimulator and the paper at https://arxiv.org/abs/2307.05263
- AirSim: https://github.com/microsoft/airsim
- PX4 simulation docs: https://docs.px4.io/main/en/simulation/
- FlightForge: https://arxiv.org/html/2502.05038v1
- Gazebo PBR API: https://gazebosim.org/api/rendering/9/classgz_1_1rendering_1_1Material.html and https://gazebosim.org/api/common/5/classgz_1_1common_1_1Pbr.html
- The texture measurements above are from this repository's own
  `sim/worlds/media/` and can be reproduced with Pillow.
