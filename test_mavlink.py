"""python test_mavlink.py -- talks to a fake vehicle on loopback, no hardware."""
import threading
import time

from pymavlink import mavutil

from control import Channels, ZERO
from drone import MavDrone, mav_axes

# The mapping is the part that kills you silently: mid-throttle must be 500.
assert mav_axes(ZERO) == (0, 0, 500, 0)
assert mav_axes(Channels(0, 0, 100, 0))[2] == 1000, "full up"
assert mav_axes(Channels(0, 0, -100, 0))[2] == 0, "full down"
assert mav_axes(Channels(100, 0, 0, 0)) == (0, 1000, 500, 0), "roll -> y"
assert mav_axes(Channels(0, 100, 0, 0)) == (1000, 0, 500, 0), "pitch -> x"
assert mav_axes(Channels(0, 0, 0, -100)) == (0, 0, 500, -1000), "yaw -> r"

PORT = 14577
veh = mavutil.mavlink_connection(f"udpout:127.0.0.1:{PORT}", source_system=1)
stop = threading.Event()


def heartbeats():
    while not stop.is_set():
        veh.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_QUADROTOR,
                               mavutil.mavlink.MAV_AUTOPILOT_ARDUPILOTMEGA, 0, 0, 3)
        time.sleep(0.1)


threading.Thread(target=heartbeats, daemon=True).start()
d = MavDrone(f"udpin:127.0.0.1:{PORT}", fly_mode="ALT_HOLD")
assert d.connected and not d.flying

d.takeoff()
assert d.flying and d._mode == "GUIDED", d._mode

d.send_rc(Channels(0, 40, 0, 0))  # BCI "forward" pulse
assert d._mode == "ALT_HOLD", "first input must hand over from GUIDED"

d.emergency()

deadline = time.time() + 3
got = []
while time.time() < deadline:
    msg = veh.recv_match(blocking=True, timeout=0.3)
    if msg:
        got.append(msg)

mc = [m for m in got if m.get_type() == "MANUAL_CONTROL"]
assert mc, f"vehicle never received MANUAL_CONTROL, saw {sorted({m.get_type() for m in got})}"
assert (mc[0].x, mc[0].y, mc[0].z, mc[0].r) == (400, 0, 500, 0), mc[0]

# mode strings must resolve to real ArduPilot Copter mode numbers, not silently no-op
modes = [m.param2 for m in got
         if m.get_type() == "COMMAND_LONG" and m.command == mavutil.mavlink.MAV_CMD_DO_SET_MODE]
assert 4 in modes, f"GUIDED (4) never sent: {modes}"
assert 2 in modes, f"ALT_HOLD (2) never sent: {modes}"

cmds = [m.command for m in got if m.get_type() == "COMMAND_LONG"]
assert mavutil.mavlink.MAV_CMD_NAV_TAKEOFF in cmds, "no takeoff command"

# emergency must carry the force-disarm magic, or ArduPilot ignores it in flight
dis = [m for m in got if m.get_type() == "COMMAND_LONG"
       and m.command == mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM]
assert dis and dis[-1].param1 == 0 and dis[-1].param2 == 21196, dis
seen = {m.get_type() for m in got}

stop.set()
d.close()
print("ok - fake vehicle got", sorted(seen))
