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

## THE OPEN PROBLEM, and it is a real one

Throughout the code, two clause numbers are cited:

* `CAP722B 5.3(c)` - the operational-limit envelope (range, ceiling, speed)
* `CAP722B 5.2(d)` - a visible indication of video feed freshness

**Neither has been verified against the document.** They were inherited
from earlier work in this project. The attempt to check them tonight
failed: the machine this session runs on cannot reach `caa.co.uk` - its
network policy denies the host outright, at DNS.

So the clause numbers may be right, may be from an older edition whose
numbering has since moved, or may be wrong. The behaviours they describe
are sensible either way, but a citation that has not been read is not
evidence, and this project has already been bitten once this week by a
comment claiming a value had been checked when it had not.

**To close this**, either:

1. allow `caa.co.uk` in the environment's network settings and say so, and
   this can be checked directly; or
2. put the CAP 722B PDF somewhere in the repository, and it can be read
   from there.

Until one of those happens, every `CAP722B 5.x` citation in the code
should be read as "the behaviour an instructor asked for", not as a
verified reference.

## What the station does today

| Capability | What it does | Where | Verified? |
|---|---|---|---|
| Operational limit envelope | 120 m ceiling, 500 m range, 30 m/s ground speed. Amber at 90% of a limit, red past it. Always on screen along the bottom. | `instructor_station.py` `LIMITS`, `_check_one` | Behaviour yes; clause no |
| Limit transitions recorded | Every ok -> warn -> breach change written to the event log once, not per poll | `instructor_station.py` `_limit_state` | Yes |
| Video feed freshness | Age of the last telemetry message and measured camera frames per second, both on screen, both turning red when stale | `instructor_station.py` `/health`, `video_feed.fps()` | Behaviour yes; clause no |
| Assessment record | Every instructor action and every observed student response to an injected failure, timestamped, to CSV | `event_logger.py` | Format is a starting point, not a final design |
| Session grouping | A session id stamped on every row, generated once per run | `event_logger.py` | Yes |
| Failure response timing | Time from injecting a failure to the student's first mode change, logged | `simulator_link.py` `_check_failure_response` | Yes |
| Arming readiness | PX4's own verdict and its own words for why it refuses | `simulator_link.py` `_update_arm_readiness` | Yes, against PX4 source |
| Low altitude / sink rate / battery warnings | Visible and audible | `flight_display.py` | Figures are this project's own, and say so |

## Gaps worth closing, in the order they are worth closing

1. **The clause numbers.** Above. Nothing else on this list matters as
   much, because it decides whether the rest is pointed at the right
   requirements.

2. **Who was flying.** The log has no concept of a student or an
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
