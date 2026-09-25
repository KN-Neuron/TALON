                    ___                                 ___
                   /   \                               /   \
              ____|  o  |_____________________________|  o  |____
             /____|_____|_____________________________|_____|____\
                    |                                   |
                    |          ┌─────────────┐          |
                    |          │   ▄▄▄▄▄▄▄   │          |
                    └──────────┤  █ ◉◉◉◉◉ █  ├──────────┘
                               │  █ ◉   ◉ █  │
                               │  █ ◉◉◉◉◉ █  │
                               │   ▀▀▀▀▀▀▀   │
                    ┌──────────┤  ╔═══════╗  ├──────────┐
                    |          │  ║ TALON ║  │          |
                    |          │  ║ ░░░░░ ║  │          |
                    |          │  ╚═══════╝  │          |
                    |          └──────┬──────┘          |
                    |               ╱ │ ╲               |
              _____|_____         ╱   │   ╲         _____|_____
             /___________\       ╱  ╔═╧═╗  ╲       /___________\
              \    |    /       ╱   ║▓▓▓║   ╲      \    |    /
                   |           ╱    ╚═╤═╝    ╲          |
                   ◉          ╱       │       ╲         ◉
                              ════════╧════════
                                   ╲  │  ╱
                                    ╲ │ ╱
                                     ╲│╱
                                      ▼
                              ░ ░ ░ ░ ░ ░ ░
                           ░ ░ ░ ░ ░ ░ ░ ░ ░ ░
                              ░ ░ ░ ░ ░ ░ ░

                    ▶ UNIT-07 ▪ AUTONOMOUS ▪ ARMED ◀

# drone control

PS4 pad + BCI -> drone. The pad always wins.

    pip install -r requirements.txt
    python main.py --mock                          # UI only, no drone
    python main.py --sim                           # 3D sim + SSVEP windows
    python main.py                                 # DJI Tello
    python main.py --connect COM3                  # ArduPilot over USB serial
    python main.py --connect udpin:0.0.0.0:14550   # ArduPilot over SITL/wifi bridge

    python test_control.py && python test_mavlink.py && python test_sim.py

## Pad

| input | does |
|---|---|
| left stick | forward/back (pitch), strafe left/right (roll) |
| right stick | up/down (throttle), rotate left/right (yaw) |
| triangle / `T` | take off |
| cross / `L` | land |
| circle / `SPACE` | EMERGENCY — motors off, it drops |
| square / `P` | photo -> `photos/YYYYmmdd-HHMMSS.jpg` |
| L1 / `B` | arm / disarm the BCI |
| `1` `2` `3` `4` | fake BCI up / down / forward / rotate-right |

Button indices differ per driver — the console prints `[pad] button N` for
every press, so correct the `BTN_*` constants in `main.py` once.

## Simulator

`--sim` opens two more windows next to the control UI and flies those instead
of a drone:

- **`sim.py`** — a 3D chase-cam quadcopter on a ground grid. It is a normal
  drone backend (`SimDrone`), so takeoff, land, emergency, RC and even photo
  all go through the same code path as a Tello. Velocity-control model with
  altitude hold; the knobs are at the top of the file. Runs standalone too —
  arrows + WASD fly it, `T` / `L` / `SPACE`. `V` switches between the chase
  cam and FPV (camera on the nose, `FPV_PITCH` tilt).
  The track is a clockwise square of 8 gates (the BCI can only turn right),
  some on the ground and some raised so you have to climb or descend. The next
  gate is green, the HUD counts gates and laps. It forgives a noisy decoder:
  7x3.5m holes, and touching a frame only stops the drone, it does not crash.
  Layout and sizes: `TRACK`, `GATE_W`, `GATE_H` in `sim.py`.
- **`ssvep.py`** — four flashing squares on an even 2x2 grid, each labelled with
  its frequency and command:

  | **6.67 Hz** `up` `[1]` | **8.57 Hz** `forward` `[3]` |
  |---|---|
  | **5.45 Hz** `down` `[2]` | **12.00 Hz** `rotate right` `[4]` |

  Those are 60/11, 60/9, 60/7 and 60/5, so they land on whole frames at a
  60Hz refresh. Brightness is a sinusoid sampled off the wall clock, so the
  frequency holds whatever your monitor does — but watch the on-screen FPS,
  because dropped frames smear the spectrum. `SQUARE_WAVE = True` for hard
  on/off flicker instead, `FILL` for the square-to-gap ratio.

All three windows are resizable: maximise the stimulus window and the squares
spread further apart rather than just growing, which is what you want if
neighbouring flicker is bleeding into the same recording.

Picking a square (keys `1`-`4`, or a click) posts `{"cmd": "up"}` to UDP
127.0.0.1:9001, which is `main.py`'s BCI inbox — so the SSVEP window stands in
for a decoder until you have one. **The BCI still has to be armed** (L1 / `B`)
or the command is logged and dropped.

## BCI hookup

Your BCI code calls four methods on the `BCI` instance in `main.py`:

    bci.up(); bci.down(); bci.forward(); bci.rotate_right()

Or, from any process, send the name to UDP 127.0.0.1:9001 as
`{"cmd": "forward"}` — those four plus `stop`, whitelisted
on arrival.

Each fires a 1s pulse at 40% (`BCI_SPEED` / `BCI_PULSE` in `control.py`).
Call again to refresh, `bci.stop()` to cut it. Safe to call from another thread.
**Calls are ignored until `bci.armed` is True** (L1 on the pad) — the drone
should not react to thoughts the moment the app opens.

## Priority and failsafes

- `mix()` in `control.py`: while the pad is moving — and for `PAD_HOLD` (1.5s)
  after you let go — the drone follows the pad and BCI pulses are dropped.
  Grab the sticks and the BCI is gone.
- BCI pulses expire, so a BCI that stops sending leaves the drone hovering.
- Pad disconnects mid-flight: the BCI is disarmed and the drone lands. The pad
  is the emergency stop; without it, nothing should be flying.

## Talking to the drone

`TelloDrone` in `drone.py` is the only real transport: djitellopy sends UDP
text commands (`rc <lr> <fb> <ud> <yaw>`) to 192.168.10.1:8889 at 20Hz, over
the drone's own wifi AP. State comes back on :8890, video on :11111. Note your
laptop joins the *drone's* wifi, so that adapter has no internet; the PS4 pad
is Bluetooth so it does not care.

Other drone: write a class with `takeoff / land / emergency / send_rc /
battery / photo / close` and return it from `make_drone`. Nothing else in the
project knows what a drone is.

- **Crazyflie 2.x** — `cflib` over the Crazyradio USB dongle;
  `send_setpoint(roll, pitch, yaw, thrust)`. 27g, common in BCI labs.
- **Toy drone, proprietary 2.4GHz** — no library. Either a reverse-engineered
  BLE protocol, or feed PPM/SBUS/CRSF into a real transmitter's trainer port.

## ArduPilot / PX4 (`MavDrone`)

Flash **ArduPilot**, not Betaflight — MAVLink is native, LOITER holds position,
failsafes are real features. `--connect` takes anything pymavlink understands:
`COM3`, `/dev/ttyUSB0` (SiK radio), `udpin:0.0.0.0:14550` (SITL or ESP32 bridge).

- `send_rc` sends `MANUAL_CONTROL`. x/y/r are -1000..1000, **z is throttle
  0..1000 with 500 = hold** — true only in a self-levelling mode. In STABILIZE
  500 is half throttle and the drone drops. `FLY_MODE` in `drone.py` is LOITER;
  set it to `ALT_HOLD` if you have no GPS (indoors).
- Takeoff arms, switches to GUIDED and auto-climbs to `TAKEOFF_ALT`. It stays
  in GUIDED until your first stick or BCI input, so the climb is undisturbed.
  GUIDED needs a happy EKF — GPS outdoors, optical flow indoors.
- Emergency sends force-disarm (the `21196` magic). Motors off, it falls.
- ArduPilot drops our overrides after `RC_OVERRIDE_TIME` (3s) of silence and
  hands control back to a bound transmitter. **Keep a real TX bound.** A PS4 pad
  on laptop Bluetooth is a convenience, not a safety system; with real props the
  transmitter is your emergency stop and this program is the thing it overrides.

`test_mavlink.py` runs the backend against a fake vehicle on loopback and
asserts the wire format: axis mapping, mode numbers, takeoff, force-disarm.
It has never touched a real airframe.