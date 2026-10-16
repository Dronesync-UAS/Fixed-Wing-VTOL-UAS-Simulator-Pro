# What real VTOL/fixed-wing UAS simulators and ground stations do

Researched 12 Oct 2026, on the instruction to "conduct a deep research of
all functions built and to be built to find best practice from
authoritative sources of real sim for VTOL FW UAS".

**Read the caveats in each section.** Several of the questions asked here
do not have an authoritative public answer, and where that is the case
this document says so rather than filling the gap with something that
sounds right. Anything marked **UNVERIFIED** has not been checked against
a primary source and must not be quoted to a student or an auditor.

---

## 1. Driving a gimbal: PX4's way, and the way this project went

**What PX4 offers.** PX4 v1.15 implements the MAVLink gimbal protocol v2.
A ground station sends high-level *gimbal manager* commands; the manager
turns those into lower-level *gimbal device* commands. A MAVLink gimbal
is enabled by setting `MNT_MODE_IN` and `MNT_MODE_OUT` to the MAVLink
gimbal protocol v2 values, and PX4 auto-creates a manager only for a PWM
gimbal or for the first MAVLink gimbal with a matching system ID.
([PX4 v1.15 gimbal control](https://docs.px4.io/v1.15/en/advanced/gimbal_control.html))

**What this project does instead.** The station publishes joint positions
straight to Gazebo. A `gz-sim` `JointPositionController` listens on
`/model/<model>/joint/<joint>/<axis>/cmd_pos` and takes a
`gz::msgs::Double`; a `<topic>` element overrides that default.
([gz-sim 8 JointPositionController](https://gazebosim.org/api/sim/8/classgz_1_1sim_1_1systems_1_1JointPositionController.html))

**Why.** Going through PX4 would mean giving PX4 a gimbal device to
manage, setting the mount parameters, and routing every payload command
console → MAVLink → PX4 → gimbal. The station already talks to Gazebo
directly for the lights and the camera feeds.

**The cost, stated plainly.** The gimbal is not in PX4's view of the
world: it does not appear in a PX4 log, and PX4 does not stabilise it. A
student who later flies an aircraft whose gimbal is driven through the
autopilot will see slightly different behaviour. For teaching *find,
hold, measure*, that difference does not change the lesson. If this
project ever needs the gimbal in the flight log alongside the autopilot's
own data, the PX4 route is the one to take.

## 2. Zoom

**UNRESOLVED.** No documented way to change a camera sensor's
`horizontal_fov` at runtime in gz-sim 8 was found. The sensors API
exposes a `HorizontalFOV()` getter with no setter in the pages found
([gz-sensors](https://gazebosim.org/api/sensors/8/classgz_1_1sensors_1_1GpuLidarSensor.html)),
and the legacy `SetFOV` on the old Gazebo `Camera` class is from Gazebo
0.5/0.6 and does not apply.

So the zoom in this project is **digital**: the middle of the frame is
cropped and scaled back up. That is what the digital zoom on a real
payload does, and it is labelled as digital on screen. A real EO ball
also has an optical zoom, and this simulator does not model one. If that
matters later, the options are a second camera sensor at a narrow fixed
FOV switched in at a threshold, or re-creating the sensor on a FOV
change - both ugly, both deferred.

## 3. What a payload operator's screen should show

There is no public HMI standard for a UAS sensor operator's console that
this search could find. MIL-STD and STANAG human-factors material on this
specifically was not located. What follows is drawn from integration
guidance and product material, and is **weaker evidence than the sections
above**:

* **A range reading needs its age and its provenance on it.** An EO/IR
  integration guide argues that a laser rangefinder reading should carry
  validity, confidence and last-update time rather than appearing as a
  bare number, so a stale or low-confidence measurement is not treated as
  certain.
  ([Sentia EO/IR integration guide](https://www.sentiacu.com/blog/ir-gimbal-systems-for-uav-isr-sensor-payload-laser-rangefinder-stabilization-and-integration-guide.html))
  **This project follows it**: every range says whether it was measured
  by the laser or computed from the aircraft's own height, and how many
  seconds old it is.
* **The operator must be able to tell thermal contrast from a processing
  artefact** - same source. **This project goes further and says the IR
  views are not thermal at all**, because nothing in these worlds has a
  temperature. A standing note sits on screen while a rendered view is on.
* **Slew-to-cue then confirm.** Counter-UAS descriptions have the gimbal
  slewed to supplied coordinates and a tracker acquiring, with the
  operator confirming rather than searching.
  ([Inside Unmanned Systems](https://insideunmannedsystems.com/the-edge-of-visibility-eo-ir-system-design-realities-for-modern-c-uas/))
  **This project follows the sequence**: TRACK, click, slew, settle,
  range, lock - the range is taken *after* the slew, not before.
* **Slew rate.** One published UAS EO payload quotes 360° continuous pan,
  -90° to +30° elevation and 120°/s slew.
  ([Unmanned Systems Technology](https://www.unmannedsystemstechnology.com/expo/electro-optical-systems/))
  **This project matches the travel exactly** and sets the joint velocity
  limit to 2.1 rad/s, which is 120°/s.
* **Separate pilot and payload roles.** Predator-era descriptions have
  the pilot and the sensor operator at different workstations.
  ([Airborne sensor operator](https://en.wikipedia.org/wiki/Airborne_sensor_operator))
  **Not followed, deliberately**: this academy teaches one person at a
  time, and the payload view is a tab rather than a second station. Worth
  revisiting if two-crew training is ever on the syllabus.

## 4. STANAG 4586, and whether it matters here

NATO's STANAG 4586 defines the interface between a UAV and a Core UAV
Control Station, with five Levels of Interoperability. **Level 3 is
payload control and monitoring**; levels 4 and 5 add vehicle control
without and with launch and recovery. Payload and vehicle commands are
translated by a Vehicle Specific Module, and a system is not considered
compliant if the VSM lives only on the control station.
([NATO STO educational note](https://www.sto.nato.int/publications/STO%20Educational%20Notes/STO-EN-SCI-271/EN-SCI-271-01.pdf),
[Kutta](https://kuttatech.com/stanag-4586-interoperability/))

**Relevance to this project: low, and worth saying so.** This is a
training simulator for UK civil remote pilots, not a NATO control
station. The useful borrowing is the *vocabulary* - "payload control and
monitoring" as a thing distinct from vehicle control is exactly the split
this console now has between the rails and the payload screen. Claiming
any level of STANAG 4586 compliance would be false and must not be done.

## 5. CAP 722B, FSTDs and flight logs

* The fifth edition of CAP 722B (March 2025) added requirements and
  guidance on **Flight Simulator Training Devices** for remote pilot
  competence training.
  ([CAA CAP 722B](https://www.caa.co.uk/data-and-publications/publications/documents/content/cap-722b/))
* Record keeping: the CAA's AMC1 Article 8(2) guidance requires remote
  pilots to keep accurate flight logs in accordance with the operator's
  procedures and UAS.SPEC.050(1)(g), and those logs must be **auditable**
  by an RAE(PC) and/or the CAA, verifiable against a corresponding
  aircraft technical log entry.
  ([CAA regulatory library](https://regulatorylibrary.caa.co.uk/2019-947/Content/Article%208/AMC1%20Article%208%202%20Remote%20Pilot.htm))
* A 2023 CAA consultation proposed a digital record of competency for
  every registered remote pilot. **That is a proposal, not current rule.**

**UNVERIFIED and still open.** The FSTD section's actual requirements -
what a device has to do to be acceptable, what credit a simulated hour
earns, what qualification standard applies - were not retrieved. The CAA
PDF is the only authority and it was not readable from here. Every clause
number quoted in this project's code and docs
(`5.3(c)`, `5.2(d)`, and the AMC1 reference above) remains **unverified
against the printed edition** and is marked as such wherever it appears.
**Somebody with the PDF needs to check them before this is shown to an
auditor.**

What the project does in the meantime is the part that is clearly right
regardless of clause numbering: it writes an auditable record. Every
flight is logged automatically from ARM to DISARM, with a half-second
track in CSV and a summary beside it (`flight_log.py`), and every
instructor action is in a separate CSV (`event_logger.py`). Neither
invents a student identity, which is a decision for the Head of Training
and is noted as such.

## 6. The flight model

PX4 SITL's own dynamics, running against Gazebo's LiftDrag system and the
`standard_vtol` airframe's own mass, inertia and aerofoil coefficients,
**is** the reference implementation. There is nothing this project could
do to make it more faithful, and hand-tuning its coefficients would make
it less. The IMU in that model already carries Gaussian noise with a
dynamic bias and a 1000 s correlation time - PX4's own figures.

The one thing that was unrealistic was the **air**. Every world shipped
with `<wind><linear_velocity>0 0 0</linear_velocity>`, and nothing set it
unless an instructor pressed a button. The PX4 documentation for the
Gazebo wind plugin describes setting a mean wind speed with variance on
speed and direction, and gusts with a start time and duration
([PX4 Gazebo simulation](https://docs.px4.io/v1.13/en/simulation/gazebo)).
The worlds in this project already carry that variation structure; only
the mean was zero.

**What was done about it**: `plugins/conditions.py` sets the air by
Beaufort force, using the standard scale so "Force 4" means what it means
in a forecast, and the station applies Force 1 at start-up so an
untouched session is not flown in mathematically still air. Nothing in
the airframe or its parameters was touched.

**UNVERIFIED.** No flight has been flown at any wind setting, and
`plugins/wind_gust.py` still flags its direction convention as reasoned
from the world's ENU frame rather than measured. One flight settles it:
set the wind from the west and confirm the aircraft drifts east.

## 7. DJI's interface, and what was actually copied

**Weak evidence.** No authoritative description of DJI Pilot 2's layout
was found; the search returned reseller write-ups and two "manuals" on a
domain that could not be verified as DJI's. What a reseller does say is
that the app was reworked so drone and payload controls can be reached
in one tap, and that camera views are also on the controller's own
buttons.

So what this console borrows from DJI is only the ideas that are
independently defensible:

* the camera selector is always visible and never more than one press
  away - it is the leftmost thing on the top bar;
* the payload controls are a single strip, not a menu;
* everything set once and left alone is behind one menu icon, at the far
  right where every tablet puts it.

**Nothing here is a claim that DJI does it this way.** If matching DJI
precisely matters, somebody needs to sit in front of DJI Pilot 2 and
write down what is actually on the screen.

---

## What still needs a primary source

1. **CAP 722B fifth edition, the FSTD section and the clause numbers.**
   The one that matters most, and the one that is least resolved.
2. **DJI Pilot 2's actual layout**, from the application rather than from
   a reseller.
3. **Runtime field-of-view change in gz-sim 8**, if optical zoom is ever
   wanted.
4. **A human-factors reference for sensor operator consoles.** Nothing
   authoritative was found; if the academy has access to MIL-STD-1472 or
   equivalent, that is where to look.

## Sources

- [PX4 v1.15 gimbal control](https://docs.px4.io/v1.15/en/advanced/gimbal_control.html)
- [gz-sim 8 JointPositionController](https://gazebosim.org/api/sim/8/classgz_1_1sim_1_1systems_1_1JointPositionController.html)
- [gz-sim 8 joint controllers overview](https://gazebosim.org/api/sim/8/jointcontrollers.html)
- [gz-sensors GpuLidarSensor](https://gazebosim.org/api/sensors/8/classgz_1_1sensors_1_1GpuLidarSensor.html)
- [CAA CAP 722B](https://www.caa.co.uk/data-and-publications/publications/documents/content/cap-722b/)
- [CAA AMC1 Article 8(2) Remote Pilot Competence](https://regulatorylibrary.caa.co.uk/2019-947/Content/Article%208/AMC1%20Article%208%202%20Remote%20Pilot.htm)
- [CAA consultation: the future of remote pilot competency (2023)](https://consultations.caa.co.uk/rpas/remote-pilot-competency-rpcwg/user_uploads/the-future-of-remote-pilot-competency-in-the-specific-category--july-2023-.pdf)
- [NATO STO EN-SCI-271 on interoperability levels](https://www.sto.nato.int/publications/STO%20Educational%20Notes/STO-EN-SCI-271/EN-SCI-271-01.pdf)
- [Kutta on STANAG 4586](https://kuttatech.com/stanag-4586-interoperability/)
- [Sentia EO/IR gimbal integration guide](https://www.sentiacu.com/blog/ir-gimbal-systems-for-uav-isr-sensor-payload-laser-rangefinder-stabilization-and-integration-guide.html)
- [Inside Unmanned Systems on EO/IR for C-UAS](https://insideunmannedsystems.com/the-edge-of-visibility-eo-ir-system-design-realities-for-modern-c-uas/)
- [Unmanned Systems Technology, EO systems](https://www.unmannedsystemstechnology.com/expo/electro-optical-systems/)
- [Airborne sensor operator](https://en.wikipedia.org/wiki/Airborne_sensor_operator)
- [PX4 Gazebo simulation, wind plugin](https://docs.px4.io/v1.13/en/simulation/gazebo)
