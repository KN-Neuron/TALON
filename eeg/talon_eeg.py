"""TALON-owned EEG subprocess. JSON lines on stdin/stdout; no network port.

Hardware and FBCCA match Miner. --simulate is only for explicit automated tests;
connection errors never fall back to generated EEG.
"""
from __future__ import annotations
import argparse
import json
import sys
import threading
import time
import numpy as np
from fbcca import fbcca_predict

FREQUENCIES = [10.25, 13.75, 14.25, 14.75]
DIRECTIONS = ["Up", "Left", "Right", "Down"]
# MAXI 009 montage, same source indices as Interface, ordered POz PO3 PO4 Oz O1 O2.
CHANNELS = [27, 26, 28, 30, 29, 31]
write_lock = threading.Lock()


def emit(message):
    with write_lock:
        print(json.dumps(message, allow_nan=False, separators=(",", ":")), flush=True)


class Session:
    def __init__(self, simulate=False):
        self.simulate = simulate
        self.hardware = None
        self.connected = False
        self.fs = 250.0
        self.capture_id = None
        self.blocks = []
        self.count = 0
        self.capture_started = 0.0
        self.condition = threading.Condition()
        self.closing = False

    def event(self, event):
        kind = event.get("type")
        if kind == "samples":
            data = np.asarray(event["batch"]["values"], dtype=float)
            with self.condition:
                if self.capture_id is None:
                    return
                if data.ndim != 2 or data.shape[0] != 32 or not np.isfinite(data).all():
                    self.capture_id = None
                    emit({"type": "lost", "error": "Nieprawidłowe próbki EEG."})
                else:
                    self.blocks.append(data[CHANNELS].copy())
                    self.count += data.shape[1]
                    # Bound memory even if Unity stops reading or cancels late.
                    while self.blocks and self.count > self.fs * 12:
                        self.count -= self.blocks.pop(0).shape[1]
                self.condition.notify_all()
        elif kind in ("device-disconnected", "bridge-error"):
            with self.condition:
                self.connected = False
                self.capture_id = None
                self.condition.notify_all()
            emit({"type": "lost", "error": event.get("reason", event.get("message", "Utracono EEG."))})

    def connect(self):
        if self.connected:
            return
        if self.simulate:
            self.connected = True
            return
        import brainaccess_bridge as bridge
        bridge.emit = self.event
        if self.hardware is not None:
            self.hardware.shutdown()
        self.hardware = bridge.BrainAccessSession()
        try:
            devices = self.hardware.scan()
            if not any(d["name"] == "BA MAXI 009" for d in devices):
                raise RuntimeError('Nie znaleziono czepka Bluetooth „BA MAXI 009”.')
            info = self.hardware.connect("BA MAXI 009")
            if info["channelCount"] != 32:
                raise RuntimeError("Montaż MAXI 009 wymaga dokładnie 32 kanałów EEG.")
            self.fs = float(info["sampleRateHz"])
            if self.fs <= 200:
                raise RuntimeError("FBCCA wymaga próbkowania powyżej 200 Hz.")
            # Set before starting so a disconnect callback cannot be overwritten.
            self.connected = True
            self.hardware.start_stream()
        except Exception:
            self.connected = False
            self.hardware.shutdown()
            raise

    def cancel(self):
        with self.condition:
            self.capture_id = None
            self.blocks.clear()
            self.count = 0
            self.condition.notify_all()

    def begin(self, request_id):
        with self.condition:
            if not self.connected:
                raise RuntimeError("Czepek nie jest połączony.")
            self.capture_id = request_id
            self.capture_started = time.monotonic()
            self.blocks = []
            self.count = 0

    def classify(self, capture_id, seconds):
        if not 4 <= seconds <= 10:
            raise ValueError("Czas próby musi wynosić 4–10 s.")
        required = round(seconds * self.fs)
        deadline = time.monotonic() + 3
        with self.condition:
            while True:
                if self.capture_id != capture_id or not self.connected:
                    raise RuntimeError("Próba EEG została anulowana.")
                if self.simulate:
                    self.count = int((time.monotonic() - self.capture_started) * self.fs)
                if self.count >= required:
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self.capture_id = None
                    raise RuntimeError("Za mało próbek EEG; dron pozostaje w miejscu.")
                self.condition.wait(min(.02, remaining))
            if self.simulate:
                t = np.arange(required) / self.fs
                rng = np.random.default_rng(19)
                eeg = np.array([np.sin(2*np.pi*14.25*t + c*.13) +
                                .3*np.sin(2*np.pi*28.5*t) + .05*rng.normal(size=required)
                                for c in range(6)])
            else:
                eeg = np.concatenate(self.blocks, axis=1)[:, -required:]
            self.capture_id = None
            self.blocks = []
            self.count = 0
        winner, scores = fbcca_predict(eeg, FREQUENCIES, self.fs)
        return {"direction": DIRECTIONS[FREQUENCIES.index(winner)],
                "winnerHz": winner, "scores": scores.tolist(), "sampleCount": required}

    def close(self):
        self.closing = True
        self.cancel()
        if self.hardware is not None:
            self.hardware.shutdown()
        self.connected = False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--simulate", action="store_true")
    session = Session(parser.parse_args().simulate)
    workers = []

    def respond(request):
        rid = request["id"]
        command = request["command"]
        try:
            result = {}
            if command == "connect":
                session.connect()
                result = {"sampleRateHz": session.fs, "simulated": session.simulate}
            elif command == "begin":
                session.begin(rid)
            elif command == "classify":
                result = session.classify(request["captureId"], float(request["seconds"]))
            else:
                raise ValueError("Nieznane polecenie EEG.")
            emit({"type": "response", "id": rid, "command": command, "ok": True, **result})
        except Exception as exc:
            emit({"type": "response", "id": rid, "command": command, "ok": False, "error": str(exc)})

    emit({"type": "ready"})
    try:
        for line in sys.stdin:
            request = json.loads(line)
            command = request["command"]
            if command == "shutdown":
                break
            if command == "cancel":
                session.cancel()
            elif command in ("connect", "classify"):
                workers = [w for w in workers if w.is_alive()]
                if workers:
                    emit({"type": "response", "id": request["id"], "command": command,
                          "ok": False, "error": "Poprzednia operacja EEG jeszcze trwa. Spróbuj ponownie."})
                    continue
                worker = threading.Thread(target=respond, args=(request,), daemon=True)
                workers.append(worker)
                worker.start()
            else:
                respond(request)
    finally:
        # Wake classifiers; allow an in-progress SDK call to finish before disposal.
        session.cancel()
        for worker in workers:
            worker.join()
        session.close()


if __name__ == "__main__":
    main()
