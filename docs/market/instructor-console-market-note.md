# Is the instructor console a product? - a first look

Written 14 Oct 2026, overnight, in answer to "there are GCS on the market
but nothing as an instructor console for a simulator - perhaps we should
see if this can become a product".

**Read this first: this is a desk exercise, not market research.** It is
one night of web searching and reading, by someone who has not spoken to a
single prospective buyer. Everything below is a hypothesis to be tested
with people, and the last section says how. Treat any of it as fact at
your peril.

## The claim, stated precisely enough to be wrong

> Ground control stations are a solved, free problem. What does not exist
> is the instructor's half: failure injection, scenario control, repeatable
> conditions and session records, sitting alongside a standard GCS rather
> than replacing it.

That is worth separating into two claims, because they are not equally
true.

**Claim A - nobody sells an instructor console.** FALSE as stated. Every
serious military and large-commercial UAV simulator has an Instructor
Operator Station, and has for years:

| product | who | what its IOS does |
| ------- | --- | ----------------- |
| [MISSIM](https://www.elbitsystems.com/unmanned/aerial/uav-simulators/missim-uav-mission-simulator) | Elbit | OneSim IOS: session preparation and management |
| [Predator Mission Trainer](https://www.ga-asi.com/training-and-support-services/predator-mission-aircrew-training-system) | General Atomics | IOS for crew training, monitoring, evaluation, integrated debrief |
| [Zen UAV Simulator](https://www.zentechnologies.com/zen-uav-training-simulator.html) | Zen Technologies | IOS with a 2D map of the training area and after-action review |
| [Quantum3D](https://quantum3d.com/products-overview/), [MVR FPV UAV](https://www.mvrsimulation.com/products/fpv-uav-simulator.html) | - | full-stack simulation with instructor control |

So the concept is mature and well understood. Anyone pitching "nobody has
thought of this" will be corrected in the first meeting.

**Claim B - nobody sells one for the small-UAS training market, paired
with the free GCS those operators actually fly.** This looks much more
defensible. The products above are defence and large-enterprise: bespoke,
procured, and priced accordingly. At the other end, the small-UAS training
simulators - [Zephyr](https://zephyr-sim.com/),
[AeroSIM-RC](https://www.aerosimrc.com/en/drone-training.htm) - are aimed
at the *student*: stick skills, scenarios, scoring. They are closed
products with their own flight models and their own interfaces.

The gap is in the middle: **an instructor console that drives a real PX4
and sits beside real QGroundControl**, so that what the student learns to
operate is the software they will actually use on the job.

## What makes this one different, if anything

Three things, and they are only worth something together:

1. **The student flies the real thing.** Standard QGroundControl, standard
   PX4 behaviour, real MAVLink. Not a training-only interface the student
   will never see again. Verified on this machine: QGC and the station run
   side by side on separate MAVLink links, and a failure injected from the
   console is seen by both.
2. **The instructor half is the product.** Forty-two controls, of which
   the ones nothing else offers are failure injection, scenario reset,
   weather and time of day, and the session record.
3. **It is honest about being a training device, not a certification.**
   The CAP 722B readiness note in this project already states plainly that
   software cannot be CAP 722B compliant on its own. That is the right
   posture and it is unusually rare in this market.

## The regulatory tailwind, which is real but not ours alone

[CAP 722B](https://www.caa.co.uk/data-and-publications/publications/documents/content/cap-722b/)'s
Fifth Edition (March 2025) added requirements and guidance for **Flight
Simulator Training Devices used in remote pilot competence training**.
That is a genuine change: it creates a reason for an RAE to want a device
that produces evidence, rather than a game.

Two cautions:

* it applies to every RAE in the UK, so it is a tailwind for competitors
  too, and the established simulator vendors will read it as an
  opportunity before we do;
* the clause numbers cited throughout this codebase were checked against
  the document on 14 Oct 2026. `5.3(c)`, `5.2(d)` and `5.5(l)` are right;
  `2.2(f)` was wrong and is now `2.1(f)`. See the readiness note.

## The honest risks

**The moat is thin.** The hard parts here are PX4, Gazebo and QGC, and all
three are free. A competent developer could rebuild the instructor half in
a few months. What is defensible is the *teaching* content - the exercise
designs, the assessment criteria, the records that satisfy an RAE - not
the code.

**QGC is moving into this space.**
[PR #14578](https://github.com/mavlink/qgroundcontrol/pull/14578) adds a
PX4 failure-injection setup page to QGroundControl itself. It is a setup
screen for testing rather than an instructor console, but it shows the
direction, and "inject a failure" alone will not be a differentiator for
long. The differentiator has to be the *lesson*: repeatable scenarios,
the record, the debrief.

**The requirement is more specific than the pitch assumes.** Reading
CAP 722B properly turned up three things in `5.3` - predefined loadable
scenarios, and control of temperature, barometric pressure and
turbulence - that the station does not have, and one, `5.3(f)`, that is
about the room rather than the software: the instructor's display must be
positioned so the remote pilot cannot see it. A buyer who has read the
document will ask about all four. That is an argument for building
against the clauses rather than against an idea of what an instructor
console should be - and the clauses are public, so a competitor can read
them too.

**The addressable market may be small.** UK RAEs number in the dozens, not
thousands. A product priced for that market has to either be cheap and
self-serve, or be sold alongside training content at a price that reflects
the content.

**This project is young.** In two days of testing it produced a ground
that rendered black in seven worlds, a log that reached 19.5 GB, a chase
camera with no boom, and a GPS failure button that reported an injection
it never made. All now fixed, but a buyer evaluating it today would find
more. It is not yet a product; it is a working prototype with good bones.

## What would actually test this

In rough order of how much they would teach per hour spent:

1. **Ring ten UK RAEs.** Ask what they use for simulated training today,
   what their CAP 722B FSTD plans are, and what they would pay. Ten calls
   settles more than another month of building.
2. **Ask one assessor** what evidence a device would have to produce for
   them to accept simulated hours.
3. **Price-test against the alternative**: Zephyr and similar are the
   obvious comparator, and a buyer will anchor on them.
4. **Check the licences before anything is sold.** QGC is dual Apache-2.0
   / GPLv3, PX4 is BSD-3, Gazebo is Apache-2.0; the map imagery is the
   sharp one - this station reads tiles QGC cached, which is fine on one's
   own machine and is NOT a basis for redistributing imagery.

## My own view, for what it is worth

The instructor console is the right thing to have built, and pairing it
with real QGC rather than replacing it is the right call - it is both
better training and a smaller thing to maintain.

Whether it is a *product* depends on something not in this repository:
whether the teaching content around it is good enough that an RAE would
buy the pair. The software is a reasonable moat for about a year. The
course material, the exercise designs and the evidence trail are the part
a competitor cannot copy in a weekend.

So: worth ten phone calls before another hundred hours of code.
