"""The simulated Newmark NSC-A1 controller and PerformaxCom.dll for the SHV
stage tests, copied unchanged from the standalone Newmark_motor_test.py's
--dry-run (on main), which the modular branch does not carry (user,
2026-11-01).  Test use only; nothing here touches hardware."""
import ctypes
import math
import re
import time

PRODUCT_STRING_SIZE = 256
SERIAL_OPTION, DESCRIPTION_OPTION = 0, 1
FULL_STEPS_PER_TURN = 200   # 1.8 deg motor (Lin 5718M-05P)
GEAR_RATIO = 72             # RM-5-110 worm gear
FULL_STEPS_PER_DEG = FULL_STEPS_PER_TURN * GEAR_RATIO // 360    # 40; x the microstep
MICROSTEP = 250
HOME_SWITCH = 1 << 3
INTEGER = re.compile(r"-?[0-9]{1,10}")


def _now():
    return time.monotonic()


class SimulatedNSC:
    """An NSC-A1 that answers as its manual describes, with a stage that turns in
    (simulated) time: DRVMS 250, the lab PC's QuickMotion microstep and the
    script's MICROSTEP, so 10000 steps/deg; the home switch is 37.5 deg on (+)
    from where the stage starts (PX ``px``).  It still answers RR, R2 and the
    DRV* reads, but the script never sends them (user, 2026-10-17).

    A motion is one segment {from, to, t0, t1} at a time, and HL queues the
    rest of its stages (manual, Figure 6.6): at the switch the counter becomes
    0, it runs on while it decelerates, comes back to the switch at low speed,
    goes past it by HCA and comes back to it at low speed (counter 0)."""

    def __init__(self, serials=("SIM-NSC-A1",), identity="Ace-Series-SDE", px=0):
        self.serials = list(serials)
        self.identity = identity
        self.version, self.name = "V231BL", "SDE01"
        self.handle = None
        self.calls = []             # DLL-level calls: ("timeouts", r, w), ("open", i), ("flush",), ("close", h)
        self.received = []          # every command, in order
        self.px, self.eo, self.mm = px, 1, 0
        self.hspd, self.lspd, self.acc = 1000, 100, 300
        self.inputs = 0             # MST input bits (3 home, 4/5 limit inputs, 8-10)
        self.latched = 0            # MST bits 6/7
        self.registers = {"POL": 0, "IERR": 0, "RZ": 0, "HCA": 0, "RT": 0, "SL": 0, "EDIO": 0, "TOC": 0}
        self.driver = {"DRVMS": 250, "DRVRC": 2000, "DRVIC": 500, "DRVIT": 50}
        self.driver_read = False
        self.silent_until = -math.inf   # RR: no communication for 2 s
        self.home_px = 375000 + px      # the home switch, in counter steps (+37.5 deg from where it started)
        self.motion = None

    # ---- the DLL's view ----------------------------------------------------
    def count(self):
        return len(self.serials)

    def product_string(self, index, option):
        if not 0 <= index < len(self.serials) or option not in (SERIAL_OPTION, DESCRIPTION_OPTION):
            return None
        return self.serials[index] if option == SERIAL_OPTION else "NSC-A1 (simulated)"

    def set_timeouts(self, read_ms, write_ms):
        self.calls.append(("timeouts", read_ms, write_ms))
        return True

    def open(self, index):
        if not 0 <= index < len(self.serials):
            return None
        self.calls.append(("open", index))
        self.handle = 0x5EED0 + index
        return self.handle

    def close(self, handle):
        self.calls.append(("close", handle))
        ok = handle == self.handle
        self.handle = None
        return ok

    def flush(self, handle):
        self.calls.append(("flush",))
        return handle == self.handle

    def send_recv(self, handle, data):
        """The 64-byte write buffer in, the reply bytes out; None = the transaction failed."""
        if self.handle is None or handle != self.handle or _now() < self.silent_until:
            return None
        command = bytes(data).split(b"\0", 1)[0].decode("ascii", "replace")
        self.received.append(command)
        text = self.reply(command)
        if self.registers["RT"] == 1:
            text = "#01" + text
        return (text + "\r").encode("ascii")

    # ---- the controller ------------------------------------------------------
    def turn(self):
        return 360 * FULL_STEPS_PER_DEG * self.driver["DRVMS"]

    def reply(self, command):
        now = _now()
        self._advance(now)
        moving = self.motion is not None
        reads = {"ID": self.identity, "VER": self.version, "DN": self.name, "MST": self._status(now),
                 "PX": self._position(now), "EO": self.eo, "HSPD": self.hspd, "LSPD": self.lspd,
                 "ACC": self.acc, "MM": self.mm, "PS": self.hspd if moving else 0,
                 "R2": 1 if self.driver_read else 0}
        reads.update(self.registers)
        # Driver values are valid only after RR (manual, Table 6.11).
        reads.update({name: value if self.driver_read else 0 for name, value in self.driver.items()})
        if command in reads:
            return str(reads[command])
        if command in ("ABS", "INC"):
            self.mm = 0 if command == "ABS" else 1
            return "OK"
        if command in ("EO=0", "EO=1"):
            self.eo = int(command[-1])
            return "OK"
        if command == "CLR":
            self.latched = 0
            return "OK"
        if command in ("STOP", "ABORT"):
            self._stop(command, now)
            return "OK"
        if command == "RR":
            self.driver_read = True
            self.silent_until = now + 2.0
            return "OK"
        name, equals, value = command.partition("=")
        if equals and name in ("HSPD", "LSPD", "ACC") and value.isdigit():
            setattr(self, name.lower(), int(value))
            return "OK"
        if equals and name == "PX" and INTEGER.fullmatch(value):
            if moving:
                return "?Moving"
            self.home_px += int(value) - self.px
            self.px = int(value)
            return "OK"
        if re.fullmatch(r"X-?[0-9]+", command) or command in ("HL+", "HL-"):
            if moving:
                return "?Moving"
            if self.latched:
                return "?State Error"
            if command.startswith("X"):
                target = int(command[1:]) if self.mm == 0 else self.px + int(command[1:])
                self._start(target, now)
            else:
                self._start_home(1 if command == "HL+" else -1, now)
            return "OK"
        return "?" + command

    def _start(self, target, now, homing=False, queue=()):
        duration = abs(target - self.px) / max(self.hspd, 1) + self.acc / 1000
        self.motion = {"from": self.px, "to": target, "t0": now, "t1": now + duration,
                       "homing": homing, "stopping": False, "queue": list(queue)}

    def _start_home(self, sign, now):
        """HL+/HL-: to the switch (at most one turn), then the stages after it."""
        turn = self.turn()
        switch = self.px + sign * ((sign * (self.home_px - self.px)) % turn or turn)
        overshoot = round((self.hspd + self.lspd) / 2 * self.acc / 1000)
        hca = abs(self.registers["HCA"])
        stages = [{"reset": True, "to": sign * overshoot, "duration": self.acc / 1000, "mst": 4},
                  {"to": 0, "duration": overshoot / max(self.lspd, 1), "mst": 1}]
        if hca:
            stages += [{"to": -sign * hca, "duration": hca / max(self.hspd, 1) + self.acc / 1000},
                       {"to": 0, "duration": hca / max(self.lspd, 1), "mst": 1}]
        self._start(switch, now, homing=True, queue=stages)

    def _position(self, now):
        motion = self.motion
        if motion is None:
            return self.px
        span = motion["t1"] - motion["t0"]
        fraction = 1.0 if span <= 0 else min(1.0, max(0.0, (now - motion["t0"]) / span))
        return round(motion["from"] + (motion["to"] - motion["from"]) * fraction)

    def _finished(self, now):
        return now >= self.motion["t1"]

    def _end_position(self, motion):
        return motion["to"]

    def _advance(self, now):
        while self.motion is not None and self._finished(now):
            motion, self.motion = self.motion, None
            self.px = self._end_position(motion)
            queue = motion.get("queue") or []
            if motion["stopping"] or not queue:
                return
            stage, t0 = queue[0], motion["t1"]
            if stage.get("reset"):
                self.px, self.home_px = 0, 0    # HL: the counter becomes 0 at the switch
            self.motion = {"from": self.px, "to": stage["to"], "t0": t0, "t1": t0 + stage["duration"],
                           "homing": True, "stopping": False, "idle": stage.get("idle", False),
                           "mst": stage.get("mst"), "queue": queue[1:]}

    def _status(self, now):
        bits = self.inputs | self.latched
        motion = self.motion
        if motion is not None and not motion.get("idle"):
            ramp = self.acc / 1000
            if motion["stopping"]:
                bits |= 4               # STOP decelerates (manual: "STOP will decelerate")
            elif motion.get("mst"):
                bits |= motion["mst"]   # an HL stage at one speed (low speed, or slowing down)
            else:
                bits |= 2 if now - motion["t0"] < ramp else 4 if motion["t1"] - now < ramp else 1
        elif motion is None and (self.px - self.home_px) % self.turn() == 0:
            bits |= HOME_SWITCH
        return bits

    def _stop(self, command, now):
        motion = self.motion
        if motion is None:
            return
        if command == "ABORT":
            self.px, self.motion = self._position(now), None
            return
        # STOP: from the present speed down to LSPD within ACC, then stop (manual, "Stopping Motor").
        ramp = min(max(motion["t1"] - now, 0.0), self.acc / 1000)
        span = motion["t1"] - motion["t0"]
        speed = 0.0 if span <= 0 or motion.get("idle") else abs(motion["to"] - motion["from"]) / span
        here = self._position(now)
        way = 1 if motion["to"] >= motion["from"] else -1
        there = here + way * min(round((speed + min(self.lspd, speed)) / 2 * ramp), abs(motion["to"] - here))
        self.motion = dict(motion, **{"from": here, "to": there, "t0": now, "t1": now + ramp, "stopping": True,
                                      "idle": False, "queue": []})


def _handle_value(handle):
    return getattr(handle, "value", handle)


class SimulatedPerformax:
    """PerformaxCom.dll's functions over a SimulatedNSC (for --dry-run), called
    exactly as the real DLL is called above."""

    def __init__(self, controller=None):
        self.controller = SimulatedNSC() if controller is None else controller

    def fnPerformaxComGetNumDevices(self, count):
        count[0] = self.controller.count()
        return 1

    def fnPerformaxComGetProductString(self, index, buffer, option):
        text = self.controller.product_string(int(index), int(option))
        if text is None:
            return 0
        data = text.encode("ascii")[:PRODUCT_STRING_SIZE - 1] + b"\0"
        ctypes.memmove(buffer, data, len(data))
        return 1

    def fnPerformaxComOpen(self, index, handle):
        value = self.controller.open(int(index))
        if value is None:
            return 0
        handle[0] = value
        return 1

    def fnPerformaxComClose(self, handle):
        return int(self.controller.close(_handle_value(handle)))

    def fnPerformaxComSetTimeouts(self, read_ms, write_ms):
        return int(self.controller.set_timeouts(int(read_ms), int(write_ms)))

    def fnPerformaxComSendRecv(self, handle, write, write_size, read_size, read):
        reply = self.controller.send_recv(_handle_value(handle), ctypes.string_at(write, int(write_size)))
        if reply is None:
            return 0
        ctypes.memmove(read, reply[:int(read_size)].ljust(int(read_size), b"\0"), int(read_size))
        return 1

    def fnPerformaxComFlush(self, handle):
        return int(self.controller.flush(_handle_value(handle)))
