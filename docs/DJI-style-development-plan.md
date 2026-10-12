# Making this console work the way a DJI ground station does

Written 12 Oct 2026, overnight, in answer to "research how DJI GCS is set
up and what can be duplicated, then prepare a strategic development plan".

## How good the research is

Honest about the source, because it changes how much weight the table
below can carry.

DJI's own Pilot 2 manual could not be opened from this machine: the
network policy here blocks most outside hosts at DNS, the same block that
stopped the CAP 722B PDF being read. What is below comes from web search
results describing Pilot 2 and FlightHub 2 - retailer pages, Heliguy's
knowledge base, pilot forums - not from DJI's documentation.

That is good enough to plan against, and not good enough to copy exactly.
Before building anything in Phase 2 or later, open the real manual.

## What DJI's enterprise ground station actually gives a pilot

From the research, the things Pilot 2 is built around:

1. **One picture, everything on it.** Camera full screen, telemetry
   overlaid, map inset. Tap the map to swap it to full screen.
2. **A pre-flight checklist** that confirms aircraft status and parameter
   settings before takeoff.
3. **PinPoints** - mark a point on the ground from the camera; it stays
   marked, in the picture and on the map, and can be edited or deleted.
4. **Waypoint missions** - fly a route by points, save it, reload it, fly
   it again. Record a route by flying it manually and marking as you go.
5. **A home point that is always shown** on the map and in the picture.
6. **Alerts as conditions change**, rather than only at the moment of
   failure.
7. **Customisable buttons** on the controller and on screen.
8. **FlightHub 2** behind it: the fleet, the records, team sync.

## Where this console already stands

| DJI capability | This station today | Gap |
|---|---|---|
| Camera full screen, telemetry over it, map inset | Yes - hero plus two corner tiles, any view swappable | None |
| Pre-flight checklist | **No** | Build it |
| Home point marked in the picture | Yes, as of 12 Oct - projected through the camera's real field of view | None |
| Home point marked on the map | Yes, labelled, with a leg to the aircraft | None |
| PinPoints | **No** | Build it |
| Waypoint missions | **No** | Build it - this is the big one |
| Alerts as conditions change | Yes - limits, low altitude, sink rate, battery, all visible and spoken | None |
| Customisable layout | Yes - every panel moves, resizes and turns | Better than Pilot 2 |
| Fleet / records behind it | Partly - a CSV event log per session | See the CAP 722B readiness note |
| Instructor-side failure injection | Yes - and DJI has no equivalent, because DJI is not a trainer | n/a |

The honest summary: the *flying* picture is already close to Pilot 2. What
is missing is everything about **planning a flight and recording what was
flown** - checklist, pinpoints, missions - and that is also most of what
an assessment body wants.

## The plan

Ordered by what unblocks the most, not by what is easiest.

### Phase 1 - finish what tonight started (hours)

Nothing new; close the loop on the audit.

* Fly every control that was rebuilt against the PX4 source and has never
  been flown: TAKEOFF, ARM, LOITER, CLIMB / DESCEND TO, FORWARD FLIGHT,
  NEW SESSION hard reset, all four failure injections.
* Check `SYS_FAILURE_EN` is 1 on the training machine.
* Settle the CAP 722B clause numbers - see the readiness note.

### Phase 2 - the pre-flight checklist (a day)

The smallest thing with the largest return, because it serves both the DJI
parity goal and the assessment-record gap at once.

* A list the instructor works down before an exercise, some items filled
  in from telemetry automatically (arming readiness, satellites, battery,
  link age, limits), some ticked by hand (area clear, weather, briefing).
* Refuses to let the exercise start until the automatic ones are green.
* Writes the completed checklist to the event log, so the record shows the
  flight was started from a known state.

### Phase 3 - pinpoints (two days)

* Click the map, or press a key over the camera, to drop a marked point.
* Drawn in both camera views by the same projection the home marker
  already uses, and on the map.
* Range and bearing from the aircraft shown.
* For training this becomes "fly to the point I just marked", which is a
  real exercise, not a gadget.

### Phase 4 - waypoint missions (a week)

The largest piece, and the one that turns this from a flying console into
a training device.

* Build a route on the map; save it under a name; load it again.
* Upload to PX4 as a real mission (MISSION_ITEM_INT / MISSION_COUNT), fly
  it with PX4's own mission mode, so the student sees what a real mission
  flight looks like.
* Record a route by flying it and marking points as you go, the way Pilot
  does on the older app.
* **This also gives the syllabus hook the assessment record needs**: a
  mission is a named exercise, and the log can then say which exercise was
  flown rather than only what happened.

### Phase 5 - the assessment record proper (a week)

Everything in the CAP 722B readiness note's gap list: who was flying,
which exercise, pass criteria, retention. Needs the Head of Training to
decide the content; the plumbing is small once the content is decided.

### Phase 6 - polish towards Pilot 2 (ongoing)

* A second camera payload view (DJI's wide / zoom pair).
* Obstacle markers on the map.
* On-screen customisable shortcut buttons.
* A flight replay: the log already holds the track and the events, so
  playing a lesson back afterwards is mostly a drawing job.

## What NOT to copy

* **FlightHub's cloud sync.** This station has to work with no internet -
  that is why the satellite imagery is downloaded once and cached. A
  cloud-dependent feature would break the thing that makes it usable.
* **DJI's geofencing.** The station has its own CAP-shaped limit
  envelope, which is the one an instructor is teaching to.
* **Automatic return on signal loss, silently.** In a trainer the loss of
  signal IS the exercise. The station injects it on purpose and watches
  what the student does.
