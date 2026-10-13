**To:** Your Getac account manager (copy technical support)
**Subject:** X600 serial RN3XXX0003 — discrete GPU retrofit, or upgrade path

---

Hello,

We operate a UAV training academy. Our Getac X600 is the host for a
fixed-wing VTOL flight simulator and ground control station that we use
to train remote pilots. The machine has been faultless and we would like
to stay with Getac; our question is only about graphics.

**Our unit, as the machine itself reports it**

| | |
|---|---|
| Make and model | GETAC X600 |
| Serial number | RN3XXX0003 |
| BIOS | INSYDE Corp. R1.15.070520, 09/04/2025 |
| CPU | 11th Gen Intel Core i5-11500H @ 2.90 GHz, 6 cores / 12 threads |
| Memory | 31.1 GB |
| Storage | 502 GB, 384 GB free |
| Graphics | Intel TigerLake-H GT1 [UHD Graphics] — **integrated only; no discrete card fitted** |
| Operating system | Ubuntu 24.04.4 LTS, kernel 7.0.0-31-generic, x86_64 |
| Purchased | [MONTH, YEAR] from [SUPPLIER] |

**Where we are**

The CPU, memory and storage are all comfortable for our workload. The
graphics are the single constraint: our 3D simulation runs at 19–28
frames per second, and the integrated GPU has no dedicated video memory
at all. The renderer we want to move to asks for a DirectX 11/12 card
with 8 GB or more of dedicated VRAM, so this is a hardware limit rather
than something we can solve in software.

We understand the X600 is offered with optional discrete NVIDIA
graphics — Quadro RTX 3000, RTX A4500 and GTX 1650 are the options we
have seen published.

**Our questions**

1. **Retrofit.** Can a discrete GPU be fitted to our existing unit,
   serial RN3XXX0003, as a service operation? If so, which options are
   available for this chassis and configuration, and what are the cost
   and the turnaround time?

2. **If not, the replacement path.** Which current X600 configuration
   ships with the NVIDIA RTX A4500, and what are its price and lead time?
   We would also want to know whether our existing memory and storage
   can be carried across.

3. **VRAM, confirmed.** Could you confirm the dedicated VRAM of each
   discrete option you offer for the X600? Published sources disagree on
   the Quadro RTX 3000 — some list 6 GB, others 8 GB — and that figure
   decides whether it is sufficient for us, so we need it from you
   rather than from a review.

4. **Linux.** We run Ubuntu 24.04 LTS, not Windows. Are the discrete
   configurations supported under Linux, and is there a driver version
   you recommend or validate for them?

Many thanks — any upgrade path you can offer would be genuinely useful
to us, and we would rather not move to a non-rugged machine.

Kind regards,

[YOUR NAME]
[JOB TITLE]
DroneSync UAS
dronesync@icloud.com
[PHONE]
