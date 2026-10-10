# CubePilot Herelink — Saved Documentation

Source: docs.cubepilot.org, "Herelink" section of the left-hand navigation (5 top-level pages + the 10 sub-pages under "Herelink User Guides"). Saved 2026-09-05. Each section below is one page; the URL is given so you can jump back to the live version (e.g. for embedded images/screenshots, which aren't reproduced here).

---

## 1. Herelink Overview
`https://docs.cubepilot.org/herelink/herelink-overview`

Herelink is an integrated remote controller, ground station and wireless digital transmission system designed for Cube Autopilot, Ardupilot, or PX4. It enables RC control, HD video, and telemetry transmission up to 20 km. Herelink 1.1 improves on 1.0 with higher display brightness (1000 nit), an added Ethernet interface on the airunit, and SD card slot support.

**Firmware note:** use the latest `flasher_win` to upgrade both the Herelink 1.1 controller and airunit.

### Technical specifications

**Airunit and Controller (shared)**

| Component | Specification |
|---|---|
| Processor | SoC – Pinecone S1 |
| SOC | 4× Cortex A53 2.2GHz / 4× Cortex A53 1.4GHz |
| GPU | 4 Core, Mali-T860 |
| SDR | A7 + DSP |
| Memory | Airunit LPDDR3 1GB / Controller LPDDR3 2GB |
| Storage | Airunit EMMC 4GB / Controller EMMC 8GB |
| Transmission distance | FCC 20km / CE, SRRC, MIC 12km |
| Video delay | 110 ms |
| Image resolution | 720p@30fps / 1080p@30/60fps |
| Frequency band | 2.4GHz ISM |
| Receive sensitivity | -99dBm @ 20MHz BW |
| Recovery | < 1s |

**Controller**

| Spec | Details |
|---|---|
| Case material | Plastic |
| Weight | 1.0: 516g / 1.1: 536g (incl. 2 antennas) |
| Size | 217×106.5×31mm (excl. antennas/joysticks) |
| Screen | 5.46", 1080P, 16M colors, capacitive touch |
| Screen brightness | 1.0: 600nit / 1.1: 1000nit |
| Audio | 1× speaker, 2× mic |
| Remotes | Hall-effect gimbals, removable sticks ×2, scroll wheel ×1, 6× backlit bottom buttons, 1× top button |
| Wireless comms | Bluetooth / WiFi / GPS / 2.4G map transmission |
| Indicator lights | Tricolour LED ×2 (upper corners) |
| Interface | MicroUSB ×1, MicroSD ×1 (max 64GB) |
| External antenna | Directional (5dBi) ×1 detachable, omni (2dBi) ×1 detachable |
| Built-in antenna | WiFi + GPS antennas, external GPS antenna port ×1 |
| Power | Built-in 4950 mAh LiPo |
| Charging | MicroUSB, 5V 2A |
| Power consumption | ≤4W avg (video-only, medium brightness, WiFi/GPS off) |

**Airunit 1.0**

| Spec | Details |
|---|---|
| Case material | Aluminum alloy |
| Weight (w/ antenna) | 95g |
| Size | 78.5×30×15mm |
| Signal bandwidth | 20MHz / 10MHz |
| Power consumption | ≤4W avg |
| Micro HDMI 1 | Camera video in (recommended) |
| Micro HDMI 2 | Camera video in |
| Power input | 7V recommended, 6–12V range; don't share BEC with servos |
| UART | 3.3V UART |
| S.bus | Dual RCout, S.bus1 + S.bus2 |
| Micro USB | Debug/upgrade, OTG (needs external power for USB device) |
| Button | Pairing / state reset |
| Indicator lights 1,2 | Pairing / video transmission state |
| MMCX antenna jacks 1,2 | Signal + ground comms |

**Airunit 1.1** — same as 1.0 except: weight 98g; Micro USB OTG needs no external power; adds **SD slot** (future use) and **ETH interface** (network device access), both 1.1-only.

### Airunit interface pinouts (1.0 & 1.1)

**Power:** 1=Power (7–12.6V max, 3S LiPo OK), 2=GND
**UART:** 1=RXD (3.3V TTL), 2=TXD (3.3V TTL), 3=GND
**S.bus:** 1=S.bus out 1 (control signal), 2=GND, 3=S.bus out 2 (gimbal signal), 4=GND
**ETH (1.1 only):** 1=TX+, 2=TX-, 3=GND, 4=RX+, 5=RX- (all AUTO MDIX)

### Accessories (in box)
HereLink Airunit ×1 · Controller ×1 · Omni antenna ×1 · Directional antenna ×1 · Airunit antenna ×2 · Joystick ×2 · HDMI cable ×1 · Power cable ×1 · Telemetry cable ×1 · S.bus cable ×1 · USB cable ×1 · Back board ×1 · M1.6×16mm fan screw ×5 · M1.6 fan nut ×5 · Fan washer ×5 · Fan O-ring ×20 · M1.6×3mm airunit case screw ×5 · M3×10mm back board screw ×3 · M3 nut ×3 · Fan ×1 (Herelink 1.1 only)

### AirUnit LEDs
**LED1:** solid green = HDMI1 signal · solid red = HDMI2 signal · solid yellow = flight control data · green/red alternating = 2 video streams · green/yellow/red alternating = 2 streams + FC data · off = no valid signal
**LED2:** green flicker = pairing · solid green = valid control signal, power OK · solid yellow = unpaired/no signal · red flicker = unstable power · off = unpowered
**Pair/Reset button:** controller pairing + enter upgrade mode

### Controller buttons & LEDs
| Button | Function |
|---|---|
| Upper left wheel | Gimbal control (configurable) |
| Upper right button | Take photo (configurable) |
| Button B / C / D | Configurable |
| Power button | Power on/off, unlock screen |
| Home button | RTL options (configurable) |

**Battery LED (left):** flashing red = critical · solid red = low · solid yellow = medium · solid green = sufficient

---

## 2. Herelink User Guides (index)
`https://docs.cubepilot.org/herelink/herelink-user-guides`

Index page only — links to the 10 sub-pages reproduced in full below (§2.1–§2.10). No standalone content of its own beyond that list.

### 2.1 Assembly and Connection
`.../herelink-user-guides/assembly-and-connection`

**Install controller antenna:** plug the omni antenna into the top-left hole, align the pointer/mounting hole, press and rotate clockwise to lock. *Rotation is fixed at 90° — don't force it further.*

**Airunit connection:**
1. Mount the airunit to the drone, position chosen by cable length.
2. Mount the airunit antenna(s) — keep off metal/conductors (carbon fiber counts), install vertically at ~15° for best gain.
3. S.bus on airunit → RCIN on flight controller.
4. UART on airunit → TELEM1 or TELEM2 on flight controller.
5. Power: 5–12.6V max (3S LiPo OK) to the airunit's power input.
6. Camera → HDMI1 (preferred); if using two streams, second camera → HDMI2. Switch Stream 1/2 on the controller.

**Back board assembly:** M1.6×3mm screws mount airunit to back board; M3×10mm screw + M3 nut mount airunit to the rover.

**Cooling fan install:** M1.6×16mm screws + nut + washer from the kit; snap into the 4 mounting holes on top of the airunit with washers/o-rings, tighten per diagram; wire fan +/- to the 5–12V supply.

### 2.2 How To Update Firmware
`.../herelink-user-guides/upgrading-firmware`

Upgrade on PC/Mac/Linux, or over-the-air via WiFi (OTA) if Solex TX is installed.

**Which method?** Controller: if it opens QGC directly on boot and Solex isn't installed → PC upgrade; otherwise → OTA. Airunit: if it won't pair, or shows no/garbled firmware version → PC upgrade; otherwise → OTA.

**1. PC upgrade**
Download `flasher_win`/`flasher_mac`/`flasher_linux` from `herelinkfw.cubepilot.org` (`/flasher_win.zip`, `/flasher_mac.zip`, `/flasher_linux.zip`).
- *Controller:* connect via USB → hold **Power+D** while powering on to enter Fastboot (≥1 antenna attached) → run the extracted flasher app → auto-restarts when done → boots to Activation screen.
- *Airunit:* run the flasher app → power airunit with 7–12V, connect via USB (≥1 antenna attached, UART/SBUS not needed) → PC needs internet → auto-writes and restarts on completion.
- *Driver issues on Windows:* Power+D into Fastboot, install driver from `developer.android.com/studio/run/win-usb`, or if already installed, uninstall via Device Manager (check "also uninstall driver") and reinstall, or use `herelinkfw.cubepilot.org/driver.msi`.

**2. Activation** (needs 5GHz WiFi internet): connect WiFi from settings → select region → Proceed → enter the 16-digit activation key (on the back of the controller for newer units; pre-April-2020 units need the key from your reseller) → Done → Register → auto-downloads latest software.

**3. OTA upgrade (via WiFi)** — only if Solex is installed.
- *Controller:* needs 5.8GHz WiFi, IP **not** in `192.168.0.x`, correct region, clock within 5 min → pull down settings cog → About phone → System Update → Check for update → installs automatically. Error checklist: stable 5G WiFi, correct device time, correct IP, correct key.
- *Airunit* (only if its firmware version is visible from the controller): connect controller to 5G WiFi w/ internet → pair airunit → Herelink Settings → AIRUNIT tab → check version → **Download Air Firmware** (to ground station) → **Transfer to Airunit** → **Update Airunit**, waiting for each progress bar to reach 100% before the next step.

### 2.3 Pairing, RC Calibration & Setup
`.../herelink-user-guides/one-time-setup`

⚠️ Before configuring Sbus buttons, check flight-mode settings on the Mavlink-button page and button settings in Solex/QGC.

**Controller calibration** — App Launcher → notification drawer → **HW JS CAL**. Screen shows SAVE, a Calibrated status dot (red=needed, green=done), HW WHEEL CAL, HW JS CAL, SBUS OUT CAL, plus SBUS/AXIS/INPUT/REV/DZ/EXPO/CH# and Wheel Acc/Throt Cent 0/Mode/Dual Cont/MAIN/IP fields.

1. **Wheel cal:** HW WHEEL CAL → Start rollwheel → follow steps, confirm values change → Pass.
2. **Joystick cal:** HW JS CAL → Start Calibration → follow the on-screen arrows/box (on-screen stroke won't match the real stick at first) → Pass if satisfied, Fail to retry pressing harder into the corners.
3. **SBUS output cal:** move each RC stick through its full range and the wheel through its range; "Calibrated" turns green when done.

**Controller settings:**
- *RC transmitter mode:* pick at the bottom, SAVE. Use "Throt Cent 0" if a model needs mid-throttle adjustment.
- *Wheel:* set as a W-axis input; REV reverses it; CH# sets the output channel (SBUS1: 1–16, SBUS2: 17–32); Wheel Acc stacks outputs.
- *Dual control:* two controllers to one airunit over WiFi hotspot or LAN. Master: Dual Cont + MAIN + SAVE, then map secondary channels onto master control channels. Secondary: Dual Cont, select IP (hotspot `192.168.43.1`, or check master's IP under WiFi settings for LAN).
- *Trainer mode:* connect master+secondary; secondary's X2/Y2/Z2/R2 map to master channels 1–4; hold the CAM button to hand control to the secondary, release to return to master.

### 2.4 Configure Modes & Mavlink Buttons
`.../herelink-user-guides/mavlink_buttons`

Herelink has 6 programmable buttons + 1 wheel, controllable two ways: as Sbus channel outputs from the airunit's dual S.bus connector, or as MAVLink commands sent via Solex/QGC.

**Available MAVLink button commands:** Vehicle Mode, Home Mode Prompt, Take Picture, Toggle Video, Camera Switch, Map/Video toggle, Toggle HUD, Set Servo, Non-Latch Servo, Set Relay, MAVLink command, Arm, Disarm, Toggle Arm, Wheel Settings, Clear Wheel Settings.

**Important:** flight-mode changes must go through MAVLink button commands (Solex/QGC), not Sbus — "a secure command link for flight mode changes, immune to system restarts and signal loss." You must also disable ArduPilot's default Sbus-channel-5 mode selection by setting **`FLTMODE_CH = 0`** when using Herelink. After configuring modes, confirm Fail Safe is set correctly and test before flying. Home button supports RTL via short/long press.

**In Solex:** hamburger menu → Button Mapping → each button gets a Click and a Long-Click function; for flight modes use the gear icon to pick the mode.
**In QGC:** gear icon → Button settings → pick a button → choose the function from the dropdown.
**Wheel:** outputs to servo channels 1–16, reconfigurable via Wheel Settings including PWM range.

### 2.5 Configure Sbus Buttons & Wheel
`.../herelink-user-guides/sbus_buttons`

Same 6 buttons + wheel, this time as raw Sbus outputs.

⚠️ **`FLTMODE_CH = 0`** is required here too — ArduPilot's mode selection must never be wired to Sbus; use MAVLink commands in Solex/QGC instead for mode changes (reliable across reboots/signal loss).

**Sbus outputs:** programmable buttons (A, B, C, D, Cam, Wheel) drive the airunit's dual Sbus buses — Bus 1 = channels 5–16 (1–4 reserved for RC), Bus 2 = channels 1–16.

**Button modes:**
- **Toggle (T):** latches between two PWM values on short/long press.
- **Momentary (M):** active while held, returns to default on release.
- **Multi:** jumps to a preset PWM; multiple buttons can be stacked on one channel for staged values.

**Steps:** Herelink Settings → button → NEW → name the profile → pick a button from the dropdown → ADD → tap T or M (blank = Multi) → for Multi, set the target PWM → set the Sbus channel + bus → SAVE. Remove entries with the bin icon. For Multi mode, at least one button per channel must be marked as the power-on default.

### 2.6 Wireless Communication
`.../herelink-user-guides/wireless-communication`

**Pairing:** App Launcher → pull down notification drawer → Herelink Setting → Pair → hold the airunit's Pair/Reset button until LED2 blinks.

**Region:** pick your country (or closest FCC/CE match) under Herelink Settings.

**Frequency settings** (Herelink Settings → FREQUENCY):
- **Freq:** manual fixed-frequency selection.
- **DL BW:** downlink bandwidth — 10M/20M for less interference, 20M for long range; 1.4M preferred in heavy-interference environments.
- **Uplink bandwidth:** 1.4M/10M/20M, same trade-off.
- **Hopping:** auto-selects best frequency — recommended on.
- **Tx Ant:** antenna select.
- **PAIR / GET STATE / FREQ SCAN:** pair, upload current settings, scan for the best current frequency.

### 2.7 Video and Data Sharing
`.../herelink-user-guides/share-video-stream`

**Switching streams:** Solex — camera-select icon toggles Cam1/Cam2, confirm OK. QGC — pick Stream1 (=HDMI1) or Stream2 (=HDMI2) from the interface icon.

**Enabling video sharing (on Herelink):** App Launcher → notification drawer → Herelink Settings → enable "Video Sharing" (a GCS app must be running with the right stream selected).
**USB-OTG method:** enable USB debugging (Settings → Developer Options), use a USB-to-HDMI cable with its own power for a wired display.

**WiFi hotspot:** set hotspot name/password in Settings; video at `rtsp://192.168.43.1:8554/fpv_stream`.
- Mission Planner: port UDP, local port 14550, HUD→Video, IP `192.168.43.1`.
- QGC: Video Settings → Source → RTSP Video Stream → paste the RTSP URL.

**USB tethering:** video at `rtsp://192.168.42.129:8554/fpv_stream`. Mission Planner: port UDPCL, Herelink IP `192.168.42.129`, local port 14552, HUD Video IP `192.168.42.129`.

**Plain WiFi connection:** video at `rtsp://<herelink_wifi_ip>:8554/fpv_stream` (get the IP from WiFi settings). Mission Planner: port UDPCL, local port 14552, HUD Video → that IP.

**Playback:** VLC → Media → Open Network Stream → paste the Herelink IP/RTSP URL → Play.

### 2.8 Connecting to Mission Planner
`.../herelink-user-guides/connect-to-mission-planner`

- **On Herelink's own hotspot:** Mission Planner → port **UDP** (top right) → port **14550** → Connect.
- **Same WiFi network (not the hotspot):** port **UDPCL**, same IP used for the MAVLink step, port **14552**.
- **USB tether / Ethernet (non-WiFi):** must specify the Herelink's IP address to reach its UDP port.
- **Video in Mission Planner:** needs Mission Planner ≥ 1.3.70 beta. Start Solex or QGC first to confirm video works, then in Mission Planner right-click the HUD → Video → Herelink Video. You may need to disconnect from the Herelink hotspot briefly to download required playback files the first time.

### 2.9 Herelink 1.0 AirUnit to AirUnit Instruction
`.../herelink-user-guides/herelink-1.0-airunit-to-airunit-instruction`

For a point-to-point link between two airunits (no controller in the middle).

**Requirements:** 2× airunits, firmware ≥ `20211229`; an Ethernet adapter; cooling fans (recommended); USB-OTG+power cable if your adapter has no separate power input.

**Compatible Ethernet adapters:**
- **AX88772** — ground unit only (e.g. Plugable USB2-OTGE100)
- **AX88179** — both ground and air (e.g. UGREEN adapter)
- **R8152 / R8153** — air side only (e.g. Cable Matters, Anker USB 3.0)

**Before starting:** update both units to latest firmware first, with the internal toggle switches down; toggles can only be changed while in the down/default position.

**1. Setup**
- *Ground unit:* update firmware (switches down) → disconnect power → open the case → set switches: **v1.0 (no ETH port):** switch1 up, switch2 down. **v1.1 (has ETH port):** switch1 down, switch2 up → reconnect power.
- *Air unit:* update firmware, leave both switches down.

**2. Pairing:** hold the pair button on both units together for 3 seconds within a 30-second window; LED goes solid green once paired.

**3. Video:** connect a 1080p/720p source to HDMI port #3 after pairing.

**4. PC network setup:** disable PC WiFi → Control Panel → Network & Internet → Network Connections → right-click → Properties → Internet (TCP/IPv4) → Properties → "Use the following IP address" → `192.168.144.3` (subnet auto-fills).

**5. PC video/telemetry:**
- *VLC:* Media → Open Streaming → Communication Protocol → `rtsp://192.168.144.10:8554/H264Video` → Play.
- *Mission Planner:* right-click HUD → Video → Set GStreamer Source → enter the GStreamer pipeline for decode/buffering → OK. MAVLink: port UDPCL, IP `192.168.144.11`, port 14552.
- *QGC:* Setup → Application Settings → General → Fly View → Video Settings → Source → RTSP Video Stream → `rtsp://192.168.144.10:8554/H264Video`.

**6. VLC latency tuning:** Media → Open Network Stream → Network → "Show more options" → adjust caching; or Tools → Preferences → Input/Codecs → Network caching → "Lowest Latency".

### 2.10 System setting
`.../herelink-user-guides/system-setting`

**Language:** bottom-right menu icon → Settings → Languages & input → Languages → Add a Language; reorder to the top to make it the system language.

**Screen brightness:** not automatic — Settings → Display → turn off Adaptive brightness → Brightness level → drag to adjust.

**Network port:** any wired network device must be set to an IP in `192.168.144.x`; `.10` and `.11` are reserved for the airunit and controller respectively and can't be reused.

**Installing a custom APK:** install the latest platform-tools → enable Developer Mode (Settings → About Phone → tap Build Number) → Settings → Developer options → enable USB debugging → confirm with `adb devices` → install with `adb install <app_name>.apk` → remove with `adb uninstall org.myorg.appname`.

---

## 3. Herelink Accessories
`https://docs.cubepilot.org/herelink/herelink-accessories`

**Sunshades** — free downloadable STL files (any 3D printer) from Airbot Systems.
- **v1:** basic short / basic long — fits using thin double-sided foam tape or Velcro strips (removable).
- **v2 ("self-tight"):** short / long — adds two brackets, removable with a 1/4" screw for quick on/off.

---

## 4. Herelink Quick Start Guide
`https://docs.cubepilot.org/herelink/herelink-quickstart-guide`

⚠️ This page is a single infographic image with no title text beyond "Herelink Quick Start Guide" — there's no extractable body text to save. Open the live page to view the graphic itself.

---

## 5. Herelink FAQ
`https://docs.cubepilot.org/herelink/herelink-faq`

**Register failure** — needs all three: WiFi on 5.8GHz, IP in `192.168.0.x`, and correct region selected with clock within 5 minutes of correct time. Any mismatch fails registration.

**Solex as autostarting app** — see CubePilot's forum thread "Solex as autostarting app" (linked from this FAQ, not reproduced here).

**Screenshots** — recommends the open-source **scrcpy** to control/screen-mirror the Android controller from Windows/macOS.

**Compatible cameras (confirmed working):** Canon EOS M3; GoPro 3/4/5/7/8; ZCam E1; Flir Duo Pro; Sony AS200V, NEX-3N, a5100, A6000, A6300, A7R, A7Rii, RX1Rii, RX0 mkI, RX100VI, HX50, HDR-CX450/PJ620/CX440; Foxeer models; Hawkeye Firefly Split 4K; EKEN H9R; Blackmagic Micro Cinema; Workswell Wiris series.
**Not working:** Xiaomi Yi.

**Connection stability** — turn off Airplane/Flight mode on the controller; enabling it disconnects the airunit and breaks the link.

**Antenna connector** — controller uses **Mini BNC**.

**Calibration** — see §2.3 (Pairing, RC Calibration & Setup) above.

**Encryption** — over-the-air link uses **AES-128-CTR**.

**Ethernet passthrough** — supported with specific USB-Ethernet adapters using R8152/R8153 chips, plus ADB configuration and bootimage modifications (see §2.9 for the general Ethernet-adapter list).

**RF power output by region:** USA 23dB (200mW) · Europe 20dB (100mW) · China 20dB (100mW) · Japan 20dB (100mW).

**Airunit fan** — recommended when using Dual Streaming mode (the unit runs hot); install the fan on top using the screws/rubber rings/washers/nuts provided.

**Flasher "LIBUSB_ERROR_ACCESS"** — caused by a running `adb` process; fix with `adb kill-server`.

**Dual video stream (enable via ADB):**
```
adb shell setprop persist.multiple.videostream true
adb reboot
```
Streams then available at `rtsp://<wifi_ip_of_gcs>:8554/fpv_stream` and `fpv_stream1`.
**Disable:**
```
adb shell setprop persist.multiple.videostream false
adb reboot
```
