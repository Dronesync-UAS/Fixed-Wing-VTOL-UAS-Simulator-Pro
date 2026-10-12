# What is worth taking from PteroSim

12 October 2026. Read from
https://github.com/PteroLabsAI/PteroSim-UAV-Simulator/releases

## First, a correction

An earlier note in `docs/image-quality-options.md` said - from a forum
post - that PteroSim keeps fixed wing and VTOL behind a paid tier. **Its
own release notes contradict that.** v0.3.0 lists the vehicles as
"x500, standard_vtol, tiltrotor, advanced_plane, quadtailsitter (PX4)"
and says plainly:

> "The Free tier counts simulation time only, and any aircraft flies on
> any tier."

So it does fly a standard VTOL on PX4, on the free tier, with simulation
time as the metered resource. The earlier note was wrong and is marked
as such.

## The find, and it is not PteroSim's technology

v0.4.0, the current release:

> "The Globe map can show Google's photorealistic 3D tiles with your own
> Cesium ion token."

**With your own token.** PteroSim is not providing the imagery - it is
plumbing in a data source that anyone can use, and we can use it without
PteroSim at all.

Google Maps Platform Photorealistic 3D Tiles is a streamed, textured 3D
mesh of the real world, delivered as OGC 3D Tiles through Cesium ion. It
is the thing that makes PteroSim's globe look like the world, and it has
nothing to do with its flight model, its engine, or its licence.

## Why this fits THIS project unusually well

The instructor station is a **browser application**. CesiumJS - the
reference 3D Tiles renderer - is a browser library, Apache 2.0.

So the shortest path to a photorealistic view here is not a new
simulator. It is a new VIEW in the console we already have:

* PX4 already gives us latitude, longitude, altitude and attitude, at
  the rate the station already polls.
* A CesiumJS page draws the real world at that position and attitude.
* It sits beside Chase, Nose, Payload and Map as another hero view.
* **Gazebo does not change at all.** It keeps flying the aircraft and
  keeps providing the physics, the collisions and the sensor cameras.

That is a few days of work, and if it is wrong it is deleted without
touching anything that flies.

## The terms, which decide whether this is durable

This is the part that matters for a product a training academy sells,
and it is not simple. Checked today; verify before committing money.

**Google's restrictions on the tiles**

| Restriction | Consequence for a trainer |
|---|---|
| **Caching and offline use are prohibited** | A classroom with no internet cannot fly. This is the serious one. |
| Non-visualisation use prohibited (e.g. training machine learning models) | Fine for us - we are visualising. |
| Attribution required, through Cesium's credit system | Fine, but the credits must not be stripped. |
| Self-hosting not available - SaaS only | No air-gapped install, ever. |

**Cesium ion's terms**

> the licence "does not permit you to include ion in your own solution
> that you make commercially available to other organizations" - for
> that, "contact us for an integration license and associated pricing".

So using it inside a simulator the academy sells or licenses to others
needs a commercial integration licence, negotiated. Using it for the
academy's own internal training is a different question and probably
sits inside an ordinary plan.

**Quotas and cost, as listed today and possibly out of date**

| Plan | Root tiles / month | Price as listed |
|---|---|---|
| Community | 1,000 | free for individuals |
| Commercial | 5,000 | $149 / month / individual |
| Premium | 10,000 | $499 / month / individual |

Google's own metering is separate and the sources conflict - one lists
1,000 free requests a month then $6.00 per 1,000; another describes a
$200 monthly credit across Maps Platform. Google's own pricing page is
the only authority and I have not read it.

## The honest verdict

**For a demonstration, and for the academy's own instructors: yes.** It
is the single biggest visual step available, it needs no new simulator,
and it drops into the console as another view.

**As the foundation of a product sold to other organisations: not
without a negotiated licence, and never offline.** A training provider
whose simulator stops working when the internet does has a problem that
no amount of photorealism answers. That argues for Cesium as an
ADDITIONAL view, not a replacement for the Gazebo one.

## Other things worth taking from PteroSim

1. **Engine sound driven by the flight model.** v0.4.0: "A prototype
   engine sound is driven by each aircraft's flight model." Ours was
   tuned by ear and says so in its own docstring. Driving it from thrust
   and rotor speed is the right way and we have those numbers.
2. **Vehicles as files - XML plus .glb meshes, loaded at runtime.** We
   already have this shape in SDF, but the `.glb` part is the
   interesting half: a proper textured mesh for the aircraft instead of
   the untextured primitives we have now.
3. **A vehicle editor.** Not for us. An instructor should not be tuning
   a JSBSim airframe mid-lesson.
4. **JSBSim as the flight model.** Worth knowing they chose it, and
   worth NOT following: we run the real PX4 firmware against Gazebo
   physics, and a wind-tunnel-derived JSBSim model would be a different
   kind of realism bought by giving up the autopilot-in-the-loop
   fidelity that matters for teaching a remote pilot.

## Recommendation

Three things, in order:

1. **Finish the Gazebo content work.** It is days, it is free, it needs
   no account, and it works offline. We have not seen its ceiling.
2. **Build a Cesium view as a fourth hero, on a free Community token.**
   Prove it, show it, and find out what it costs in frame rate. Keep the
   Gazebo views working the whole time.
3. **Before anything is sold, get the licensing answered in writing** -
   Cesium's integration licence and Google's offline prohibition. Those
   two answers decide whether this is a demo feature or a product
   feature.

## Sources

- PteroSim releases: https://github.com/PteroLabsAI/PteroSim-UAV-Simulator/releases
- Cesium on Google Photorealistic 3D Tiles: https://cesium.com/learn/photorealistic-3d-tiles-learn/
- Cesium ion pricing: https://cesium.com/platform/cesium-ion/pricing/
- Cesium ion terms of service: https://cesium.com/legal/terms-of-service/
- Cesium community, Google tile limitations: https://community.cesium.com/t/google-tiles-limitations/31034/2
