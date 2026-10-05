"""Simulates a Teams call: holds a power assertion (PreventUserIdleDisplaySleep)
via IOKit until it receives SIGINT/SIGTERM. Used to test the detector and the daemon without Teams.

Usage: fake_call.py [seconds]   (default: until interrupted)
"""
import ctypes
import ctypes.util
import signal
import sys
import time

iokit = ctypes.cdll.LoadLibrary(ctypes.util.find_library("IOKit"))
cf = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreFoundation"))

cf.CFStringCreateWithCString.restype = ctypes.c_void_p
cf.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
iokit.IOPMAssertionCreateWithName.restype = ctypes.c_int
iokit.IOPMAssertionCreateWithName.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
iokit.IOPMAssertionRelease.argtypes = [ctypes.c_uint32]

kCFStringEncodingUTF8 = 0x08000100
kIOPMAssertionLevelOn = 255


def cfstr(s: str):
    return cf.CFStringCreateWithCString(None, s.encode(), kCFStringEncodingUTF8)


# Becomes a Core Audio client (like Teams during a call): opens the default output unit
# and starts it, with no render callback -> plays silence. Without this the process tap
# cannot translate the PID into an audio object.
at = ctypes.cdll.LoadLibrary(ctypes.util.find_library("AudioToolbox"))


class AudioComponentDescription(ctypes.Structure):
    _fields_ = [("componentType", ctypes.c_uint32), ("componentSubType", ctypes.c_uint32), ("componentManufacturer", ctypes.c_uint32), ("componentFlags", ctypes.c_uint32), ("componentFlagsMask", ctypes.c_uint32)]


def fourcc(code: str) -> int:
    return int.from_bytes(code.encode("ascii"), "big")


desc = AudioComponentDescription(fourcc("auou"), fourcc("def "), fourcc("appl"), 0, 0)
at.AudioComponentFindNext.restype = ctypes.c_void_p
at.AudioComponentFindNext.argtypes = [ctypes.c_void_p, ctypes.POINTER(AudioComponentDescription)]
component = at.AudioComponentFindNext(None, ctypes.byref(desc))
unit = ctypes.c_void_p()
at.AudioComponentInstanceNew.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
at.AudioUnitInitialize.argtypes = [ctypes.c_void_p]
at.AudioOutputUnitStart.argtypes = [ctypes.c_void_p]
at.AudioOutputUnitStop.argtypes = [ctypes.c_void_p]
if component and at.AudioComponentInstanceNew(component, ctypes.byref(unit)) == 0 and at.AudioUnitInitialize(unit) == 0 and at.AudioOutputUnitStart(unit) == 0:
    print("audio client active", flush=True)
else:
    print("warning: could not become an audio client", file=sys.stderr, flush=True)

assertion_id = ctypes.c_uint32(0)
rc = iokit.IOPMAssertionCreateWithName(cfstr("PreventUserIdleDisplaySleep"), kIOPMAssertionLevelOn, cfstr("fake Teams call"), ctypes.byref(assertion_id))
if rc != 0:
    print(f"IOPMAssertionCreateWithName failed: {rc}", file=sys.stderr)
    sys.exit(1)

running = True


def _stop(signum, frame):
    global running
    running = False


signal.signal(signal.SIGINT, _stop)
signal.signal(signal.SIGTERM, _stop)
deadline = time.monotonic() + float(sys.argv[1]) if len(sys.argv) > 1 else None
print("in call (assertion active)", flush=True)
while running and (deadline is None or time.monotonic() < deadline):
    time.sleep(0.2)
iokit.IOPMAssertionRelease(assertion_id)
if unit:
    at.AudioOutputUnitStop(unit)
print("call ended", flush=True)
