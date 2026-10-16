# The plan: better than Gazebo looks now, with nothing to sign

12 October 2026.

> "what is the plan and what i can use without having licence, paid
> subscriptions and legal restrains it does not have to be super
> realistic but far better than gazebo view"

## The finding that shapes the plan

The biggest improvements need **no external data at all**. What makes
the picture poor is this project's own content, measured:

* A normal map with zero variation - no surface relief in any world.
  **Fixed.**
* Seven worlds with no ground texture whatsoever. **Fixed.**
* Scenery built from untextured flat-colour boxes - 40 to 130 per world.
* No sky material; a flat near-white ceiling. **Fixed** - painted dome.
* Ambient light at 0.40, washing every surface out. **Fixed** - 0.26.
* An untextured aircraft.
* Global illumination available in ogre2 and switched off.

None of that needs an account, a token, a licence or an internet
connection. It is ours.

## Phase 1 - entirely ours. No licence, no account, works offline.

| Step | State |
|---|---|
| 1. Real normal maps, generated from a height field | **done** - 12 Oct |
| 2. Textured ground in the seven plane worlds | **done** - 12 Oct |
| 3. PBR materials on the scenery, instead of flat-colour boxes | **done** - 12 Oct |
| 4. A real sky, and haze where fog cannot go | **done** - 12 Oct. There is no fog in this renderer; see below |
| 5. Texture the aircraft | next |
| 6. Global illumination on, frame rate measured | last, because it costs |

Step 3 matters most for the payload view, which is what a sensor
operator trains on: 40 to 130 objects per world currently have no
surface at all.

### How step 2 was done, since it looked impossible

SDF gives a heightmap `<texture><size>` - "repeat this every N metres" -
and gives a plane visual nothing. So one texture on a 220 km plane would
be 215 metres per pixel, worse than a flat colour.

The answer is a **flat heightmap**: Gazebo builds terrain from an image,
and a uniform image gives dead-level ground that CAN tile a texture.
Each plane world now carries an 8 km flat heightmap as a visual, grass
tiled every 16 m with a real normal map, over the existing 220 km plane
which is left alone for the far field. Visual only - the 220 km
collision box still carries every landing.

## Phase 2 - public data, attribution only, optional

| Source | What | The only condition |
|---|---|---|
| **Copernicus Sentinel-2** | 10 m imagery, global | attribution: "Copernicus Sentinel data [Year]" |
| **Copernicus DEM GLO-30** | 30 m elevation, global | same family |
| **USGS NAIP / Landsat** | 1 m / 30 m, **USA only** | public domain, nothing required |

The Copernicus legal notice grants reproduction, distribution and
adaptation. **Self-hosting, offline use and commercial use are all
permitted.** No account for the licence; a free Copernicus Data Space
account to download, and the mosaicking is ours to write.

## Phase 3 - OpenStreetMap buildings

ODbL. Buildings, roads, water and land use as vectors, extruded into
real geometry that appears in **every** camera view including the
gimbal. This is the only free route to structures a sensor operator can
be taught to find.

**The one caveat to keep in view:** ODbL's share-alike applies to
derived databases. Using it internally is clear; baking extruded OSM
geometry into world files that are then distributed with a product needs
a look. Attribution is required either way.

## What is deliberately NOT in the plan

| Rejected | Why |
|---|---|
| Google Photorealistic 3D Tiles | caching and offline use prohibited; no self-hosting ever |
| Cesium ion | licence excludes including it in a solution made commercially available to others |
| EOX s2cloudless 2018+ | non-commercial (CC BY-NC-SA) |
| Mapbox as the foundation | token, terms, no offline. Fine for a demo, wrong as a base |
| Isaac Sim / Pegasus | multirotor only - cannot fly this aircraft |

## How good will Phase 1 get?

Honestly: it will not look like Google's mesh of a real city, and it is
not meant to. It will look like a real field, in real light, with real
objects on it, from every camera. That is the difference between a
trainer somebody takes seriously and one they do not - and it is
reachable in days, with nothing to sign and nothing to renew.

## Where it stands

Steps 1 and 2 are committed and pushed. Neither has been seen in
Gazebo. `tools/test_surface_maps.py` checks the maps have real relief,
decode to unit normals, tile without a seam, and that no world is left
with untextured ground.


## Added 12 Oct 2026, after step 4

**There is no fog in Gazebo Harmonic.** gz-sim8's `RenderUtil.cc` reads
`Ambient()`, `Background()` and `Sky()` out of `<scene>` and nothing
else; the word "fog" does not appear in the file. sdformat will accept
`<scene><fog>` and gz-sim will ignore it. So the hard horizon is
softened with a painted haze band on the sky dome instead - it looks
like haze, it attenuates nothing.

**The ambient light mattered more than any of the materials.** At 0.40,
flat from every direction, a normal map has no direction to shade
against and roughness has no highlight to sharpen. Steps 1 to 3 were
all being washed out by one number. It is now 0.26.
