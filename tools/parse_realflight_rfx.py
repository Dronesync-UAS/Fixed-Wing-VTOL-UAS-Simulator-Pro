#!/usr/bin/env python3
"""Parse an MFE-style RealFlight .rfvehicle into a mass/geometry model
usable for a Gazebo SDF. RealFlight frame: X=right, Y=nose(+forward),
Z=up. Gazebo aircraft frame: X=forward, Y=left, Z=up.
Conversion: Xg = Yr ; Yg = -Xr ; Zg = Zr
"""
import re

import sys
RFV = sys.argv[1] if len(sys.argv) > 1 else "rfv.txt"  # unzip the .RFX, strip CR: tr -d '\r' < fighterVTOL.rfvehicle > rfv.txt
raw = open(RFV, encoding="latin-1").read()

# Motor weights (kg) from the .electricTorque spec files
MOT_LIFT_KG = 7.8 * 0.0283495   # MFE M5015S KV220
MOT_FWD_KG = 11.4 * 0.0283495   # MFE X5120S KV190
# Battery: LiPoly '20000 mah', 6.4 oz/cell. The real aircraft flies
# 2x 6S 16000mAh; model this as a 6S pack of that cell weight * 6.
BATT_KG = 6.4 * 0.0283495 * 6

def vec(s):
    return tuple(float(x) for x in s.split(","))

# Walk the file, tracking indentation-based nesting to resolve absolute
# RealFlight positions. Each component block: ComponentNameTSTRING / Type /
# LocationInParentMTR / WeightKG. Nesting depth = leading spaces / 3.
lines = raw.split("\n")
stack = []   # (depth, abs_pos)  parent chain
comps = []   # dict per component

cur = None
cur_depth = None
for ln in lines:
    m = re.match(r"( *)ComponentID=INT:(\d+)", ln)
    if m:
        depth = len(m.group(1))
        # pop stack to parent depth
        while stack and stack[-1][0] >= depth:
            stack.pop()
        parent_abs = stack[-1][1] if stack else (0.0, 0.0, 0.0)
        cur = {"id": int(m.group(2)), "depth": depth, "parent_abs": parent_abs,
               "loc": (0.0, 0.0, 0.0), "name": "", "type": "", "wkg": 0.0,
               "torque": None, "chord_r": None, "chord_t": None, "span": None}
        comps.append(cur)
        stack.append([depth, parent_abs])  # abs updated once we read loc
        continue
    if cur is None:
        continue
    if "ComponentNameTSTRING=STRING:" in ln:
        cur["name"] = ln.split("STRING:", 1)[1].strip()
    elif "ComponentType=STRING:" in ln:
        cur["type"] = ln.split("STRING:", 1)[1].strip()
    elif "LocationInParentMTR=VECTOR3:" in ln:
        cur["loc"] = vec(ln.split("VECTOR3:", 1)[1].strip())
        pa = cur["parent_abs"]
        cur["abs"] = tuple(pa[i] + cur["loc"][i] for i in range(3))
        stack[-1][1] = cur["abs"]
    elif "WeightKG=FLOAT:" in ln:
        cur["wkg"] = float(ln.split("FLOAT:", 1)[1].strip())
    elif "TorqueGeneratorElectric=STRING:MFE" in ln:
        cur["torque"] = ln.split("STRING:", 1)[1].strip()
    elif "ChordAtRootMTR=FLOAT:" in ln:
        cur["chord_r"] = float(ln.split("FLOAT:", 1)[1])
    elif "ChordAtTipMTR=FLOAT:" in ln:
        cur["chord_t"] = float(ln.split("FLOAT:", 1)[1])
    elif "SpanLengthMTR=FLOAT:" in ln:
        cur["span"] = float(ln.split("FLOAT:", 1)[1])
    elif re.match(r" *MassKG=FLOAT:", ln):
        cur["wkg"] = float(ln.split("FLOAT:", 1)[1].strip())

for c in comps:
    c.setdefault("abs", c["parent_abs"])

# Assemble point masses in Gazebo frame
def to_gz(p):  # (Xr,Yr,Zr) -> (Xf, Yl, Zu)
    return (round(p[1], 4), round(-p[0], 4), round(p[2], 4))

pts = []  # (name, gz_pos, mass_kg)
for c in comps:
    n, t = c["name"], c["type"]
    if t in ("RootComponent", "CameraComponent", "TurbineComponent",
             "PulseJetComponent", "FuelStoredEnergy", "MovablePod", "Detachable"):
        # still count Detachable boom structural weight
        if t == "Detachable" and c["wkg"] > 0:
            pts.append((n, to_gz(c["abs"]), c["wkg"]))
        continue
    if t == "PropellerComponent":
        m = MOT_FWD_KG if (c["torque"] or "").startswith("MFE X5120") else MOT_LIFT_KG
        pts.append((n, to_gz(c["abs"]), m))
        continue
    if t == "BatteryStoredEnergy":
        pts.append((n, to_gz(c["abs"]), BATT_KG))
        continue
    if c["wkg"] > 0:
        pts.append((n, to_gz(c["abs"]), c["wkg"]))

M = sum(m for _, _, m in pts)
cg = tuple(sum(p[i] * m for _, p, m in pts) / M for i in range(3))
# Inertia about CG (point-mass approximation)
Ixx = sum(m * ((p[1]-cg[1])**2 + (p[2]-cg[2])**2) for _, p, m in pts)
Iyy = sum(m * ((p[0]-cg[0])**2 + (p[2]-cg[2])**2) for _, p, m in pts)
Izz = sum(m * ((p[0]-cg[0])**2 + (p[1]-cg[1])**2) for _, p, m in pts)
Ixy = -sum(m * (p[0]-cg[0]) * (p[1]-cg[1]) for _, p, m in pts)
Ixz = -sum(m * (p[0]-cg[0]) * (p[2]-cg[2]) for _, p, m in pts)
Iyz = -sum(m * (p[1]-cg[1]) * (p[2]-cg[2]) for _, p, m in pts)

print("=== POINT MASSES (Gazebo frame: X fwd, Y left, Z up) ===")
for n, p, m in pts:
    print(f"  {n:16s} pos={p}  m={m:.3f} kg")
print(f"\nTOTAL MASS      : {M:.3f} kg")
print(f"CG (from origin): ({cg[0]:.4f}, {cg[1]:.4f}, {cg[2]:.4f}) m")
print(f"Inertia @ CG    : Ixx={Ixx:.4f} Iyy={Iyy:.4f} Izz={Izz:.4f}")
print(f"                  Ixy={Ixy:.4f} Ixz={Ixz:.4f} Iyz={Iyz:.4f}")

print("\n=== WINGS (chord/span read by dedicated block scan) ===")
# Wing geometry lines sit at the top of each Wing block, before its
# ComponentID. Scan each 'ComponentType=STRING:Wing' block backward/forward.
blocks = raw.split("ComponentType=STRING:Wing")
wing_names = ["Main Wing", "Horizontal Tail", "Vertical Tail"]
for i, name in enumerate(wing_names):
    seg = blocks[i] + "ComponentType=STRING:Wing" + blocks[i + 1][:2000]
    cr = re.search(r"ChordAtRootMTR=FLOAT:([\d.]+)", seg)
    ct = re.search(r"ChordAtTipMTR=FLOAT:([\d.]+)", seg)
    sp = re.search(r"SpanLengthMTR=FLOAT:([\d.]+)", seg)
    if cr and ct and sp:
        cr, ct, sp = float(cr.group(1)), float(ct.group(1)), float(sp.group(1))
        area = (cr + ct) / 2 * sp * 2
        wc = next((c for c in comps if c["name"] == name and c["type"] == "Wing"), None)
        pos = to_gz(wc["abs"]) if wc else "?"
        print(f"  {name:16s} gzpos={pos}  chord {cr:.3f}->{ct:.3f}  "
              f"span/side {sp:.3f}  full-span {sp*2:.3f}  area(both) {area:.4f} m2")

print("\n=== LIFT MOTOR POSITIONS (for the quad-X arm geometry) ===")
for c in comps:
    if c["type"] == "PropellerComponent" and c["name"].startswith("ENGINE_"):
        print(f"  {c['name']:10s} gzpos={to_gz(c['abs'])}")
    if c["type"] == "PropellerComponent" and c["name"] == "Engine":
        print(f"  {'FWD PUSHER':10s} gzpos={to_gz(c['abs'])}")
