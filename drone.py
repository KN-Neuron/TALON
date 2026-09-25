"""Drone backends. Duck-typed, no base class needed.

Every backend has: takeoff / land / emergency / send_rc / battery / photo /
close, plus .name .flying .rc. `photo` returns where the image went, or False.
"""

# --- MAVLink calibration knobs ---
FLY_MODE = "LOITER"    # ALT_HOLD if you have no GPS (indoors). Sticks fly it in both.
TAKEOFF_ALT = 1.5      # metres for the GUIDED auto-takeoff


class MockDrone:
    """Prints instead of flying. Use this until the real drone is on the desk."""
    name = "MOCK"

    def __init__(self):
        self.flying = False
        self.rc = (0, 0, 0, 0)
        self.connected = True

    def takeoff(self):
        self.flying = True

    def land(self):
        self.flying = False

    def emergency(self):
        self.flying = False

    def send_rc(self, ch):
        self.rc = tuple(ch)

    def battery(self):
        return 100

    def photo(self, path):
        return False  # no camera to fake

    def close(self):
        pass


class TelloDrone:
    """DJI Tello over its own wifi. Swap this class for another drone's SDK."""
    name = "TELLO"

    def __init__(self):
        from djitellopy import Tello
        self.t = Tello()
        self.t.connect()
        self.connected = True
        self.flying = False
        self.rc = (0, 0, 0, 0)
        self._frames = None
        try:
            self.t.streamon()  # kept on so a photo is one frame grab, not a 2s wait
            self._frames = self.t.get_frame_read()
        except Exception as e:
            print(f"[drone] no video stream ({e})")

    def takeoff(self):
        self.t.takeoff()
        self.flying = True

    def land(self):
        self.t.land()
        self.flying = False

    def emergency(self):
        self.t.emergency()
        self.flying = False

    def send_rc(self, ch):
        self.rc = tuple(ch)
        self.t.send_rc_control(*ch)

    def battery(self):
        return self.t.get_battery()

    def photo(self, path):
        if self._frames is None:
            return False
        import cv2  # ships with djitellopy
        frame = self._frames.frame
        if frame is None:
            return False
        return path if cv2.imwrite(path, cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)) else False

    def close(self):
        try:
            if self.flying:
                self.t.land()
        finally:
            self.t.end()


class SimDrone:
    """The sim.py window, driven over UDP. Same surface as a real drone."""
    name = "SIM"

    def __init__(self, port=9000):
        import socket
        self.addr = ("127.0.0.1", port)
        self.s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.s.settimeout(0.15)  # localhost round trip; only ever hit if sim.py died
        self.connected = True
        self.rc = (0, 0, 0, 0)

    def _send(self, **msg):
        import json
        self.s.sendto(json.dumps(msg).encode(), self.addr)

    def _ask(self, key, **msg):
        """Send and wait briefly for one reply. None if the sim window is gone."""
        import json
        self._send(**msg)
        try:
            return json.loads(self.s.recv(512)).get(key)
        except OSError:
            return None

    @property
    def flying(self):
        # Ask the sim instead of remembering: its own window can take off and
        # land too, and a stale local flag means main.py never sends RC.
        # ponytail: one localhost round trip per read, cache it if the UI lags.
        return bool(self._ask("flying", c="state"))

    def takeoff(self):
        self._send(c="takeoff")

    def land(self):
        self._send(c="land")

    def emergency(self):
        self._send(c="emergency")

    def send_rc(self, ch):
        self.rc = tuple(ch)
        self._send(c="rc", v=list(ch))

    def battery(self):
        bat = self._ask("bat", c="bat")
        return 0 if bat is None else bat

    def photo(self, path):
        import os
        return self._ask("photo", c="photo", path=os.path.abspath(path)) or False

    def close(self):
        if self.flying:
            self.land()
        self.s.close()


def mav_axes(ch):
    """Channels (-100..100) -> MANUAL_CONTROL x, y, z, r.

    x/y/r are -1000..1000 but z is throttle 0..1000, where 500 means "hold" --
    only in a self-levelling mode. In STABILIZE 500 is literally half throttle.
    """
    lr, fb, ud, yaw = ch
    return fb * 10, lr * 10, 500 + ud * 5, yaw * 10


class MavDrone:
    """ArduPilot / PX4 over MAVLink.

    connect: "COM3" for USB serial, "udpin:0.0.0.0:14550" for SITL or an ESP32
    wifi bridge, "/dev/ttyUSB0" for a SiK telemetry radio on Linux.

    Safety property worth knowing: ArduPilot drops our overrides after
    RC_OVERRIDE_TIME (3s default) of silence and hands control back to a bound
    transmitter. Kill this program and the safety pilot has the drone.
    """
    name = "MAVLINK"

    def __init__(self, connect="udpin:0.0.0.0:14550", baud=57600, fly_mode=FLY_MODE):
        from pymavlink import mavutil
        self.mav = mavutil
        self.fly_mode = fly_mode
        self.m = mavutil.mavlink_connection(connect, baud=baud)
        if self.m.wait_heartbeat(timeout=10) is None:
            raise RuntimeError(f"no MAVLink heartbeat on {connect}")
        self.connected = True
        self.flying = False
        self.rc = (0, 0, 0, 0)
        self._mode = None
        self._battery = 0

    def _cmd(self, command, *params):
        self.m.mav.command_long_send(
            self.m.target_system, self.m.target_component, command, 0,
            *(list(params) + [0] * (7 - len(params))))

    def _set_mode(self, mode):
        self.m.set_mode(mode)
        self._mode = mode

    def takeoff(self):
        # GUIDED auto-takeoff needs a happy EKF: GPS outdoors, optical flow in.
        self._set_mode("GUIDED")
        self.m.arducopter_arm()
        self._cmd(self.mav.mavlink.MAV_CMD_NAV_TAKEOFF, 0, 0, 0, 0, 0, 0, TAKEOFF_ALT)
        self.flying = True

    def land(self):
        self._set_mode("LAND")
        self.flying = False

    def emergency(self):
        # param2=21196 is ArduPilot's "yes I really mean disarm in flight" magic
        self._cmd(self.mav.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 21196)
        self.flying = False

    def send_rc(self, ch):
        self._drain()
        self.rc = tuple(ch)
        # Stay in GUIDED so the auto-takeoff climbs undisturbed; the first real
        # stick or BCI input is what hands the drone over to the flying mode.
        if self.rc != (0, 0, 0, 0) and self._mode != self.fly_mode:
            self._set_mode(self.fly_mode)
        x, y, z, r = mav_axes(ch)
        self.m.mav.manual_control_send(self.m.target_system, x, y, z, r, 0)

    def _drain(self):
        # Read everything pending, else the socket backs up and we fly on stale
        # telemetry. Cheap: this is the only reader.
        while (msg := self.m.recv_match(blocking=False)) is not None:
            if msg.get_type() == "SYS_STATUS":
                self._battery = max(0, msg.battery_remaining)

    def battery(self):
        self._drain()
        return self._battery

    def photo(self, path):
        # Only does anything with a MAVLink camera on the bus, and the image
        # lands on the camera's own storage, never on this laptop.
        self._cmd(self.mav.mavlink.MAV_CMD_IMAGE_START_CAPTURE, 0, 0, 1)
        ack = self.m.recv_match(type="COMMAND_ACK", blocking=True, timeout=0.5)
        return "saved on camera" if ack and ack.result == 0 else False

    def close(self):
        try:
            if self.flying:
                self.land()
        finally:
            self.m.close()


def make_drone(mock=False, connect=None, sim=False):
    if mock:
        return MockDrone()
    if sim:
        return SimDrone()
    try:
        return MavDrone(connect) if connect else TelloDrone()
    except Exception as e:
        print(f"[drone] no drone ({e}) -> falling back to mock")
        return MockDrone()
