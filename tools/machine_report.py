#!/usr/bin/env python3
"""
What this machine is: model, serial, CPU, memory, graphics, disk.

    python3 tools/machine_report.py

WHY IT EXISTS. Two separate needs kept coming up and both were being
answered by pasting half a dozen commands into a terminal and reading
them back. The first is capability: the simulator's frame rate is set by
the graphics hardware, and whether a different renderer is even possible
is a hardware question, not a software one. The second is paperwork: a
warranty or upgrade enquiry wants the model and serial number exactly as
the machine reports them, not as somebody remembers them.

So this prints both, in one go, and says plainly what it could not read.

NOTHING HERE CHANGES ANYTHING. It only reads. The model and serial live
in DMI, which on Linux is readable by root only, so those two lines need

    sudo python3 tools/machine_report.py

and the rest does not. Run it without sudo first; it will say so.
"""
import glob
import os
import platform
import re
import shutil
import subprocess
import sys


def run(command, timeout=6):
    """A command's output, or None. Never raises, never prints."""
    try:
        done = subprocess.run(command, capture_output=True, text=True,
                              timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    out = (done.stdout or "").strip()
    return out or None


def first_file(*paths):
    for path in paths:
        try:
            with open(path) as handle:
                value = handle.read().strip()
            if value:
                return value
        except OSError:
            continue
    return None


missing = []


def row(label, value, note=None):
    if value:
        print("  %-22s %s" % (label + ":", value))
    else:
        print("  %-22s could not read" % (label + ":"))
        missing.append(note or label)


def section(title):
    print("\n%s" % title)


# --- the machine itself ------------------------------------------------

def identity():
    section("The machine")
    vendor = first_file("/sys/class/dmi/id/sys_vendor")
    product = first_file("/sys/class/dmi/id/product_name")
    row("Make and model",
        " ".join(bit for bit in (vendor, product) if bit))
    row("Serial number",
        first_file("/sys/class/dmi/id/product_serial",
                   "/sys/class/dmi/id/chassis_serial"),
        "serial number - needs sudo")
    row("BIOS",
        " ".join(bit for bit in
                 (first_file("/sys/class/dmi/id/bios_vendor"),
                  first_file("/sys/class/dmi/id/bios_version"),
                  first_file("/sys/class/dmi/id/bios_date")) if bit))


def operating_system():
    section("Operating system")
    pretty = None
    try:
        with open("/etc/os-release") as handle:
            for line in handle:
                if line.startswith("PRETTY_NAME="):
                    pretty = line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    row("Distribution", pretty)
    row("Kernel", "%s %s" % (platform.system(), platform.release()))
    row("Architecture", platform.machine())
    row("Python", platform.python_version())


# --- what decides the frame rate --------------------------------------

def processor():
    section("Processor and memory")
    model, cores, threads = None, None, None
    try:
        with open("/proc/cpuinfo") as handle:
            text = handle.read()
        found = re.search(r"^model name\s*:\s*(.+)$", text, re.MULTILINE)
        model = found.group(1).strip() if found else None
        threads = len(re.findall(r"^processor\s*:", text, re.MULTILINE)) or None
        ids = set(re.findall(r"^core id\s*:\s*(\d+)", text, re.MULTILINE))
        cores = len(ids) or None
    except OSError:
        pass
    row("CPU", model)
    row("Cores / threads",
        "%s / %s" % (cores or "?", threads or "?") if threads else None)

    total = None
    try:
        with open("/proc/meminfo") as handle:
            for line in handle:
                if line.startswith("MemTotal:"):
                    total = int(line.split()[1]) / (1024.0 * 1024.0)
    except OSError:
        pass
    row("Memory", "%.1f GB" % total if total else None)


def graphics():
    section("Graphics - what sets the simulator's frame rate")
    cards = []
    if shutil.which("lspci"):
        listing = run(["lspci"]) or ""
        for line in listing.splitlines():
            if re.search(r"VGA compatible controller|3D controller|Display controller",
                         line):
                cards.append(line.split(":", 2)[-1].strip())
    if not cards:
        # No lspci: fall back to the kernel's own list of DRM devices.
        for path in sorted(glob.glob("/sys/class/drm/card?/device/uevent")):
            name = first_file(path)
            if name:
                cards.append(name.replace("\n", " "))

    if cards:
        for number, card in enumerate(cards, 1):
            row("Graphics %d" % number, card)
        discrete = [c for c in cards
                    if re.search(r"NVIDIA|Radeon|AMD/ATI|Arc ", c, re.I)]
        integrated = [c for c in cards if c not in discrete]
        print()
        if discrete:
            print("  A discrete graphics card is fitted. This machine can be")
            print("  considered for a renderer heavier than Gazebo.")
        elif integrated:
            print("  INTEGRATED GRAPHICS ONLY - no discrete card is fitted.")
            print("  Integrated graphics share system memory and have no")
            print("  dedicated video memory, so a renderer asking for 8 GB of")
            print("  VRAM (any Unreal Engine 5 front end, for one) will not")
            print("  run usefully here however it is configured in software.")
    else:
        row("Graphics", None, "graphics - neither lspci nor DRM readable")

    # The driver in use says more than the card alone: a card with no
    # working driver renders on the CPU and is slower than integrated.
    if shutil.which("glxinfo"):
        out = run(["glxinfo", "-B"]) or ""
        for key, label in (("OpenGL renderer string", "OpenGL renderer"),
                           ("OpenGL version string", "OpenGL version")):
            found = re.search(re.escape(key) + r":\s*(.+)", out)
            print()
            row(label, found.group(1).strip() if found else None,
                "%s - install mesa-utils for it" % label)
    else:
        print()
        print("  glxinfo is not installed, so the driver actually in use")
        print("  cannot be confirmed. It is in the mesa-utils package.")


def storage():
    section("Disk")
    try:
        usage = shutil.disk_usage(os.path.expanduser("~"))
        row("Home filesystem",
            "%.0f GB total, %.0f GB free"
            % (usage.total / 1e9, usage.free / 1e9))
    except OSError:
        row("Home filesystem", None)


def simulator():
    section("The simulator's own pieces")
    gz = run(["gz", "sim", "--versions"]) or run(["gz", "--version"])
    row("Gazebo", gz.splitlines()[0] if gz else None,
        "Gazebo version - is gz on the PATH?")
    px4 = os.path.expanduser("~/PX4-Autopilot")
    if os.path.isdir(px4):
        tag = run(["git", "-C", px4, "describe", "--tags", "--always"])
        row("PX4-Autopilot", "%s  (%s)" % (tag or "version unknown", px4))
    else:
        row("PX4-Autopilot", None, "PX4-Autopilot - not at ~/PX4-Autopilot")


def main():
    print("MACHINE REPORT")
    print("Nothing here is changed. Reading only.")
    identity()
    operating_system()
    processor()
    graphics()
    storage()
    simulator()

    print("\n" + "-" * 68)
    if missing:
        print("\nCould NOT read:")
        for item in dict.fromkeys(missing):
            print("  - %s" % item)
        if any("sudo" in item for item in missing) and os.geteuid() != 0:
            print("\nFor the model and serial number, run it again as root:")
            print("    sudo python3 tools/machine_report.py")
    else:
        print("\nEverything read.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
