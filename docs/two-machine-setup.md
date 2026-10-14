# Student on one computer, instructor on another

Written 14 Oct 2026, in answer to "the student will operate QGC from a
separate computer and GCS from another and they need to sync together".

**Read this first: none of it has been tried on two machines.** There is
one computer here. What follows is worked out from what the parts
actually do on this one - the ports were measured, the broadcast setting
was read off the running aircraft - but every line marked NOT TESTED is a
reasoned expectation, not a result. The last section says what to check
first, and it should be done before a lesson rather than during one.

## What runs where

The simulator is the heavy part and it has to sit with the instructor,
because the instructor's station talks to Gazebo over local topics that
do not cross a network.

| | Instructor machine | Student machine |
|---|---|---|
| PX4 SITL | yes | no |
| Gazebo | yes | no |
| Instructor station (this project) | yes | no |
| QGroundControl | no | **yes** |
| Graphics card needed | yes | no |

The student machine runs **nothing of this project**. It runs a standard,
unmodified QGroundControl. That is the whole point of the arrangement
settled on 13 Oct: the student learns the software they will actually
use.

## What has to cross the network

Only two things, both UDP.

| What | Port | Direction |
|---|---|---|
| MAVLink - telemetry, and the student's commands | 14550 | instructor → student, and back |
| Video - the aircraft's camera | 5600 | instructor → student |

Nothing else. The instructor's console is a web page served on the
instructor's own machine and never leaves it.

## MAVLink: probably nothing to do

PX4 is already set to broadcast. Read off the running aircraft on 14 Oct
2026:

    MAV_0_BROADCAST = 1        (1 = always broadcast)

It broadcasts its heartbeat to the subnet on 14550, which is the port
QGroundControl listens on out of the box. So a QGC on a second machine on
the **same subnet** should find the aircraft with nothing typed into it,
exactly as the QGC on this machine does.

**NOT TESTED.** It has only ever been seen working to a QGC on the same
computer, where the broadcast never leaves the loopback interface.

If it does not connect, in order:

1. Check the two machines can see each other at all - from the student
   machine:

```bash
ping 10.1.12.164
```

(10.1.12.164 is this instructor machine's address today. Check it with
`hostname -I` - it will change on a different network.)

2. Open UDP 14550 inbound on the student machine's firewall.

3. If the two are on different subnets, broadcast will not cross the
   router and PX4 has to be told the address instead. That is a change to
   `ROMFS/px4fmu_common/init.d-posix/px4-rc.mavlink`, which is PX4's file
   rather than this project's, and it is the point at which to stop and
   ask rather than edit PX4 by hand before a lesson.

## Video: one argument

The camera stream is sent by this project, and until 14 Oct 2026 it could
only send to 127.0.0.1. It now takes the student machine's address:

```bash
python3 tools/stream_to_qgc.py --host 192.168.1.50
```

Put the student machine's real address in place of 192.168.1.50. Find it
by running `hostname -I` on the student machine.

In QGroundControl on the student machine, once: **Application Settings >
Video**, Source **UDP h.264 Video Stream**, Port **5600**. That is the
same setting the QGC here already carries.

UDP 5600 has to be open inbound on the student machine.

**NOT TESTED across a network.** The stream itself is proven - it is the
same pipeline that fills the video panel of the QGC on this machine - but
it has only ever been sent to the loopback address, which cannot drop a
packet or run out of bandwidth. At 1280x720 it measured roughly 3900 UDP
datagrams in ten seconds. On a busy wireless network expect to need:

```bash
python3 tools/stream_to_qgc.py --host 192.168.1.50 --width 960 --height 540
```

Use a wired connection between the two machines if there is any choice in
it. Video over wifi is the first thing that will fall over in front of a
class.

## What "sync" does and does not mean

They are not two copies kept in step. They are two windows onto **one**
aircraft:

* the aircraft exists once, inside PX4 on the instructor's machine;
* the student's QGC and the instructor's station each hold their own
  MAVLink link to it;
* a failure the instructor injects changes the aircraft itself, so the
  student sees it because it is real - not because anything was copied
  across.

There is therefore nothing to synchronise and nothing that can drift.
What CAN happen is one of the two links going quiet while the other
stays up, and the instructor's console shows the age of its own link in
the top bar for that reason.

One consequence worth stating plainly: **the instructor's station can fly
the aircraft, and so can the student's QGC.** Both are full ground
stations with the same authority. Nothing in this arrangement stops them
commanding opposite things at the same moment. That is a teaching
protocol - who has control, and how it is handed over - not something the
software decides, and it should be written into the lesson plan before
two people sit down at two keyboards.

## The requirement this also satisfies

CAP 722B **5.3(f)**: "The instructor station visual display must be
positioned in a manner that obscures it from the view of the remote
pilot."

Two machines in two places satisfies that far more convincingly than two
windows on one screen, which is how all the testing to date has been
done and which would NOT meet it in an assessment. See
`docs/CAP722B-readiness.md`.

## What to check before trusting it

In this order, on a quiet afternoon rather than before a class:

1. Both machines on the same subnet, and `ping` works between them.
2. QGC on the student machine finds the aircraft on its own, with
   nothing typed in. If it does, the MAVLink half needs no work at all.
3. Video arrives, and stays arriving for a full twenty-minute sortie
   rather than the first thirty seconds.
4. An instructor-injected failure - GPS is the clearest - appears on the
   student's screen, and how long it takes to get there.
5. The flight log on the instructor's machine still records the
   student's responses, since it is the station's own MAVLink link that
   feeds it and that link has not changed.

Item 4 is the one that matters most and is the one no amount of reading
can settle.
