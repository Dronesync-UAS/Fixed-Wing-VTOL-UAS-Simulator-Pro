**To:** Getac technical support / your Getac account manager
**Subject:** X600 — discrete GPU retrofit, and current configurations

---

Hello,

We operate a UAV training academy and use a Getac X600 as the host for a
fixed-wing VTOL flight simulator and ground control station. The machine
is excellent in every other respect; our question is only about graphics.

**Our unit**

- Model: Getac X600
- Serial number: [SERIAL NUMBER]
- Purchased: [MONTH, YEAR] from [SUPPLIER]
- Graphics as fitted, per `lspci` under Linux:
  `Intel Corporation TigerLake-H GT1 [UHD Graphics] (rev 01)` — integrated
  only, no discrete GPU enumerated.

**What we need**

Our 3D simulation work is GPU-limited. We are currently at 19–28 frames
per second and we need to move to a renderer whose published requirement
is a DirectX 11/12 card with 8 GB or more of dedicated video memory.

**Our questions**

1. Can the discrete GPU option be **retrofitted to our existing unit** as
   a service operation, given the serial number above? If so, which
   options are available to us, and what are the cost and turnaround?
2. If a retrofit is not possible, which **current X600 configuration**
   ships with the NVIDIA RTX A4500, and what are its price and lead time?
3. Could you **confirm the dedicated VRAM** of each discrete option you
   offer for the X600 — Quadro RTX 3000, RTX A4500 and GTX 1650? Public
   sources disagree on the RTX 3000 (6 GB in some places, 8 GB in
   others), and we need the correct figure before we commit.
4. Are the discrete configurations supported under Linux, and do you
   publish or recommend a particular driver for them?

We would rather stay with Getac than move to a non-rugged machine, so any
upgrade path you can offer is genuinely useful to us.

Thank you,

[YOUR NAME]
[JOB TITLE]
DroneSync UAS
dronesync@icloud.com
[PHONE]
