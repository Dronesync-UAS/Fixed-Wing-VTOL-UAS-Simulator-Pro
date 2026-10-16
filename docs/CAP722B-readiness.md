# CAP 722B readiness - what the station does, and what is not yet known

Written 12 Oct 2026, overnight, in answer to "make this simulator 100%
CAP722B compliant".

## Read this first

**Software cannot be CAP 722B compliant on its own, and nothing here
claims it is.** CAP 722B sets out requirements for an *entity* - a
Recognised Assessment Entity for Remote Pilot Competence, RAE(PC) - and
approval is granted by the CAA against that entity's application, its
people, its procedures and its evidence. A simulator is one piece of
evidence in such an application, not the thing that is approved.

What this station can be is a training device that produces the records
and behaviours an RAE application needs, and that is what the table below
is about.

## What CAP 722B actually is

| | |
|---|---|
| Title | Recognised Assessment Entity for Remote Pilot Competence RAE(PC) |
| Publisher | UK Civil Aviation Authority |
| Current version | 5.2, dated 16 July 2026 (Fifth Edition, Amendment 2) |
| Relevance here | The fifth edition added requirements and guidance for **Flight Simulator Training Devices (FSTD)** used in remote pilot competence training |

That last row is why this document exists. This project IS an FSTD in the
sense CAP 722B uses the term, so the FSTD section is the part that governs
it.

## The clause numbers - CHECKED, 14 Oct 2026

This section used to say the citations were unverified and that the
machine could not reach `caa.co.uk`. They have now been read against the
document itself - CAP 722B Fifth Edition Amendment 2, July 2026,
downloaded from the CAA and extracted to text. Three of the four were
right. One was wrong.

| Cited as | What the clause actually says | Verdict |
|---|---|---|
| `5.3(c)` operational-limit envelope | "The UAS simulator must have a feedback tool that provides the instructor with visibility of whenever the UA limits, including crash limits, are approaching or have been exceeded." | **Correct.** "approaching or exceeded" is exactly the amber-at-90%/red-past-it behaviour |
| `5.2(d)` video feed freshness | "The FSTD must be equipped with a means to display the visual response time (ms) and frame rate (fps) of any display." | **Right clause, was half met.** Frame rate was shown; visual response time was not. Added 14 Oct 2026 - see the table below |
| `5.5(l)` GPS failure | "Modelling of GPS performance during nominal and degraded operation." Guidance: "A SOC is sufficient for this requirement." | **Correct**, and it answers the open question in DECISIONS-LOG: a Statement of Compliance is what this needs, not a sign-off |
| `2.2(f)` data protection | 2.2(f) is about **nominated persons** acting under the accountable manager. Nothing to do with data. The UK GDPR / DPA 2018 duty is **2.1(f)**. | **WRONG - off by one section.** Corrected in DECISIONS-LOG |

Chapter 5 is "Use of Flight Simulator Training Devices (FSTD)", and
**5.3 is titled "Instructor Station"**. The thing this project is was
given its own section by the CAA in the Fifth Edition.

## What reading it actually changed

Four things the readiness list had as open questions or did not have at
all turn out to be written down in the document.

**Retention and tamper-evidence are specified, not open.** `2.1(g)`: the
RAE must keep training records - including practical flight training
events and practical flight assessment - **for five years**, and "These
records must be stored in a secure manner to ensure that no damage to,
or tampering of, records can occur. It is recommended they are stored
digitally." So gap 3 has an answer (five years), and gap 6 is not a
question for the CAA after all: a CSV any text editor can alter does not
meet this.

**Predefined scenarios are a requirement.** `5.3(b)`: the instructor
station "must be capable of loading predefined training scenarios to
facilitate repeatable and timely training events in accordance with the
training plan." Gap 5 was listed here as a nice-to-have. It is not.

**Environmental control names its parameters.** `5.3(d)`: wind speed and
direction, temperature, barometric pressure, turbulence, and anything
else the training design calls for. The station has wind speed and
direction. It has **no temperature, no barometric pressure and no
turbulence** - verified by searching the whole repository on 14 Oct 2026,
which finds none of the three anywhere.

**Freeze and reposition are already right.** `5.3(a)` guidance asks for
"the functionality to freeze the simulation (for the purpose of
instructor discussion) and repositioning of the aircraft in the current
scenario", and says a statement of compliance is sufficient. Freeze /
Resume, Reset to Spawn Point and Set Home Here cover it.

**One requirement is about the room, not the software.** `5.3(f)`: "The
instructor station visual display must be positioned in a manner that
obscures it from the view of the remote pilot." The design settled on
13 Oct - student on QGroundControl, instructor on this station - means
the two displays must be on separate screens placed so the student
cannot see the instructor's. Running both on one machine, which is how
all of this has been tested, would not meet 5.3(f) in an assessment.
That is a setup instruction, not a code change, and it is not yet
written into any of the operating notes.

## What the station does today

| Capability | What it does | Where | Verified? |
|---|---|---|---|
| Operational limit envelope | 120 m ceiling, 500 m range, 30 m/s ground speed. Amber at 90% of a limit, red past it. Always on screen along the bottom. | `instructor_station.py` `LIMITS`, `_check_one` | Yes - behaviour, and 5.3(c) checked 14 Oct 2026 |
| Limit transitions recorded | Every ok -> warn -> breach change written to the event log once, not per poll | `instructor_station.py` `_limit_state` | Yes |
| Video feed freshness | Measured camera frames per second AND visual response time in ms, both on screen; telemetry age alongside, turning red when stale | `instructor_station.py` `/health`, `video_feed.fps()`, `video_feed.latency_ms()` | Yes - 5.2(d) checked 14 Oct 2026, and the response time added the same day |
| Environmental control | Wind speed (Beaufort) and direction. **Temperature, barometric pressure and turbulence are absent** - 5.3(d) names all three | `plugins/conditions.py` | Partial, and the gap is now measured against the clause |
| Freeze and reposition | Freeze / Resume, Reset to Spawn Point, Set Home Here | `plugins/freeze_resume.py`, `plugins/reset_spawn.py` | Yes - meets 5.3(a) guidance |
| Assessment record | Every instructor action and every observed student response to an injected failure, timestamped, to CSV | `event_logger.py` | Format is a starting point, not a final design |
| Session grouping | A session id stamped on every row, generated once per run | `event_logger.py` | Yes |
| Failure response timing | Time from injecting a failure to the student's first mode change, logged | `simulator_link.py` `_check_failure_response` | Yes |
| Arming readiness | PX4's own verdict and its own words for why it refuses | `simulator_link.py` `_update_arm_readiness` | Yes, against PX4 source |
| Low altitude / sink rate / battery warnings | Visible and audible | `flight_display.py` | Figures are this project's own, and say so |

## Gaps worth closing, in the order they are worth closing

1. ~~**The clause numbers.**~~ **Closed 14 Oct 2026** - read against the
   document. See the table above; one citation was wrong and is fixed.

2. **Temperature, barometric pressure and turbulence** - `5.3(d)` names
   them as parameters the instructor station must be able to control, and
   none of the three exists. Turbulence is the one that changes what a
   student actually has to fly. Routes checked the same day: PX4's
   `SIM_BARO_OFF_P` / `SIM_BARO_OFF_T` are the obvious lever for the
   first two but `SENS_EN_BAROSIM` is 0 on this build, so they do
   nothing as things stand; the barometer instead comes from the
   aircraft's Gazebo `air_pressure` sensor through `gz_bridge`, which
   reads the world's `<atmosphere>`. That is set at load, so it is a
   world-file edit plus a restart, not a runtime control.

3. **Predefined training scenarios** - `5.3(b)`, a REQUIREMENT, not the
   nice-to-have this list used to call it. A named, loadable set of
   conditions (area, time of day, weather, wind, failures) is what makes
   a training event repeatable. Mission plans can already be saved and
   loaded; the conditions around them cannot.

4. **Tamper-evidence** - `2.1(g)` requires records "stored in a secure
   manner to ensure that no damage to, or tampering of, records can
   occur". A CSV any text editor can alter does not meet that. This list
   used to call it a question for the CAA; it is not.

5. **Retention** - `2.1(g)` says **five years**, and nothing in the
   station says how long `~/uas_sim_logs` is kept or who may read it.

6. **Who was flying.** The log has no concept of a student or an
   instructor. An assessment record that cannot say who was assessed is
   not an assessment record. This was deliberately left un-guessed, and
   it now needs a decision: a name typed at the start of a session is
   probably enough, but it is the Head of Training's call.

3. **Retention.** Nothing says how long `~/uas_sim_logs` is kept, or who
   may read it. An RAE application will be asked.

4. **A pre-flight checklist.** CAP 722B governs assessment, and an
   assessment usually has a required sequence. The station has no
   checklist; DJI Pilot 2 does, and so do real assessment forms.

5. **Exercise definition.** There is no concept of "this is exercise 3,
   these are its pass criteria". Everything is a free-flight session with
   events logged. Until there is, a log cannot be read against a syllabus.

6. **Tamper-evidence.** The CSV can be edited with a text editor. Whether
   that matters is a question for the CAA, not for this file.

## What has been built against PX4's source rather than assumed

Everything in `docs/decision-log/12.10.2026 decisions-log-command-audit.md`
- the orbit centre, the takeoff target, the failure-injection unit
numbers, the altitude command, the transition sequence. Each names the PX4
v1.15.4 file and line it came from. That is the standard the CAP 722B
citations should be held to as well, and currently are not.
