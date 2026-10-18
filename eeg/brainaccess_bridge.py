"""BrainAccess JSON-lines sidecar for KNeuron.

Protocol:
- stdin: one JSON request per line
- stdout: one JSON response/event per line
- stderr: diagnostic logs only

This process owns the BrainAccess SDK lifecycle. React and KNeuron modules never
import the BrainAccess Python package directly.
"""

from __future__ import annotations

import json
import sys
import threading
from typing import Any, Callable

import numpy as np

try:
    from brainaccess import core
    from brainaccess.core.eeg_manager import EEGManager
    import brainaccess.core.eeg_channel as eeg_channel
    from brainaccess.core.gain_mode import GainMode
except Exception as exc:
    print(f"BrainAccess import failed: {exc}", file=sys.stderr, flush=True)
    raise


PROTOCOL_VERSION = 1
TARGET_BATCH_SAMPLES = 10


_write_lock = threading.Lock()


def emit(message: dict[str, Any]) -> None:
    """Write exactly one protocol message to stdout."""
    payload = json.dumps(message, separators=(",", ":"), allow_nan=False)

    with _write_lock:
        sys.stdout.write(payload + "\n")
        sys.stdout.flush()


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


class BrainAccessSession:
    def __init__(self) -> None:
        self._core_initialized = False
        self._manager: EEGManager | None = None

        self._device_name: str | None = None
        self._sample_rate_hz: float | None = None
        self._eeg_count = 0

        self._streaming = False
        self._sequence_cursor = 0

        self._acquisition_lock = threading.Lock()
        self._pending_eeg: np.ndarray | None = None
        self._pending_sample_numbers = np.empty((0,), dtype=float)

    def ensure_core(self) -> None:
        if self._core_initialized:
            return

        core.init()
        self._core_initialized = True
        log("BrainAccess core initialized.")

    def scan(self) -> list[dict[str, str]]:
        if self._manager is not None:
            raise RuntimeError("Disconnect the active BrainAccess device before scanning.")

        self.ensure_core()

        devices = core.scan()

        return [
            {
                "name": str(device.name),
                "macAddress": str(getattr(device, "mac_address", "")),
            }
            for device in devices
        ]

    def connect(self, device_name: str) -> dict[str, Any]:
        if self._manager is not None:
            if self._device_name == device_name:
                return self.connection_info()

            raise RuntimeError(
                f'BrainAccess device "{self._device_name}" is already connected.'
            )

        self.ensure_core()

        manager = EEGManager()

        try:
            status = int(manager.connect(device_name))

            if status == 2:
                raise RuntimeError(
                    "BrainAccess stream is incompatible. Update the device firmware."
                )

            if status != 0:
                raise RuntimeError(
                    f"BrainAccess connection failed with status {status}."
                )

            features = manager.get_device_features()
            eeg_count = int(features.electrode_count())

            if eeg_count <= 0:
                raise RuntimeError("Connected BrainAccess device reports zero EEG electrodes.")

            # Configure all physical EEG electrodes exactly once at connection time.
            for channel_index in range(eeg_count):
                channel = eeg_channel.ELECTRODE_MEASUREMENT + channel_index
                manager.set_channel_enabled(channel, True)
                manager.set_channel_gain(channel, GainMode.X8)

            # This follows the BrainAccess SDK minimal acquisition example.
            # The exact montage/bias semantics must still be verified for the physical cap.
            manager.set_channel_bias(
                eeg_channel.ELECTRODE_MEASUREMENT + eeg_count - 1,
                True,
            )

            # Keep the native sample number for packet-loss accounting.
            manager.set_channel_enabled(eeg_channel.SAMPLE_NUMBER, True)

            # BrainAccess STREAMING reports Bluetooth stream continuity.
            manager.set_channel_enabled(eeg_channel.STREAMING, True)

            sample_rate_hz = float(manager.get_sample_frequency())

            manager.set_callback_disconnect(self._on_device_disconnect)

            self._manager = manager
            self._device_name = device_name
            self._sample_rate_hz = sample_rate_hz
            self._eeg_count = eeg_count
            self._reset_pending()

            battery: int | None = None
            try:
                battery = int(manager.get_battery_info().level)
            except Exception:
                pass

            info = self.connection_info()
            info["battery"] = battery

            log(
                f'Connected to "{device_name}" '
                f"({sample_rate_hz:g} Hz, {eeg_count} EEG channels)."
            )

            return info

        except Exception:
            try:
                manager.destroy()
            except Exception:
                pass

            raise

    def connection_info(self) -> dict[str, Any]:
        if self._manager is None or self._sample_rate_hz is None:
            raise RuntimeError("No BrainAccess device is connected.")

        return {
            "deviceName": self._device_name,
            "sampleRateHz": self._sample_rate_hz,
            "channelCount": self._eeg_count,
        }

    def start_stream(self) -> dict[str, Any]:
        manager = self._require_manager()

        if self._streaming:
            return {"streaming": True}

        self._reset_pending()
        self._sequence_cursor = 0

        manager.set_callback_chunk(self._on_chunk)
        manager.load_config()
        manager.start_stream()

        self._streaming = True
        log("BrainAccess EEG stream started.")

        return {"streaming": True}

    def stop_stream(self) -> dict[str, Any]:
        manager = self._manager

        if manager is None or not self._streaming:
            self._streaming = False
            self._reset_pending()
            return {"streaming": False}

        manager.stop_stream()

        self._streaming = False
        self._reset_pending()

        log("BrainAccess EEG stream stopped.")

        return {"streaming": False}

    def disconnect(self) -> dict[str, Any]:
        manager = self._manager

        if manager is None:
            return {"connected": False}

        try:
            if self._streaming:
                self.stop_stream()

            # Avoid reporting an intentional disconnect as an unexpected device loss.
            manager.set_callback_disconnect(None)
            manager.destroy()
        finally:
            self._manager = None
            self._device_name = None
            self._sample_rate_hz = None
            self._eeg_count = 0
            self._streaming = False
            self._reset_pending()

        log("BrainAccess device disconnected.")

        return {"connected": False}

    def shutdown(self) -> None:
        try:
            self.disconnect()
        finally:
            if self._core_initialized:
                core.close()
                self._core_initialized = False
                log("BrainAccess core closed.")

    def _require_manager(self) -> EEGManager:
        if self._manager is None:
            raise RuntimeError("No BrainAccess device is connected.")

        return self._manager

    def _reset_pending(self) -> None:
        with self._acquisition_lock:
            self._pending_eeg = None
            self._pending_sample_numbers = np.empty((0,), dtype=float)

    def _on_device_disconnect(self) -> None:
        self._streaming = False

        emit(
            {
                "type": "device-disconnected",
                "reason": "BrainAccess Bluetooth connection was lost.",
            }
        )

    def _on_chunk(self, chunk: list[Any], chunk_size: int) -> None:
        if not self._streaming:
            return

        try:
            arr = np.asarray(chunk, dtype=float)

            expected_rows = self._eeg_count + 2

            if arr.ndim != 2:
                raise RuntimeError(f"Unexpected BrainAccess chunk dimensions: {arr.shape}")

            if arr.shape[0] != expected_rows and arr.shape[1] == expected_rows:
                arr = arr.T

            if arr.shape[0] != expected_rows:
                raise RuntimeError(
                    f"Unexpected BrainAccess chunk row count: "
                    f"{arr.shape[0]}, expected {expected_rows}."
                )

            take = min(int(chunk_size), int(arr.shape[1]))

            if take <= 0:
                return

            # BrainAccess SDK ordering used by its own minimal example:
            # row 0                  -> SAMPLE_NUMBER
            # rows 1..N             -> EEG electrodes
            # final row             -> STREAMING
            sample_numbers = arr[0, :take].copy()
            eeg = arr[1 : self._eeg_count + 1, :take].copy()

            self._append_samples(eeg, sample_numbers)

        except Exception as exc:
            emit(
                {
                    "type": "bridge-error",
                    "message": f"BrainAccess sample callback failed: {exc}",
                }
            )

    def _append_samples(
        self,
        eeg: np.ndarray,
        sample_numbers: np.ndarray,
    ) -> None:
        batches: list[tuple[np.ndarray, np.ndarray, int]] = []

        with self._acquisition_lock:
            if self._pending_eeg is None:
                self._pending_eeg = eeg
            else:
                self._pending_eeg = np.concatenate((self._pending_eeg, eeg), axis=1)

            self._pending_sample_numbers = np.concatenate(
                (self._pending_sample_numbers, sample_numbers)
            )

            while (
                self._pending_eeg is not None
                and self._pending_eeg.shape[1] >= TARGET_BATCH_SAMPLES
            ):
                batch_eeg = self._pending_eeg[:, :TARGET_BATCH_SAMPLES].copy()
                batch_numbers = self._pending_sample_numbers[
                    :TARGET_BATCH_SAMPLES
                ].copy()

                self._pending_eeg = self._pending_eeg[:, TARGET_BATCH_SAMPLES:]
                self._pending_sample_numbers = self._pending_sample_numbers[
                    TARGET_BATCH_SAMPLES:
                ]

                sequence_start = self._sequence_cursor
                self._sequence_cursor += TARGET_BATCH_SAMPLES

                batches.append((batch_eeg, batch_numbers, sequence_start))

        for batch_eeg, batch_numbers, sequence_start in batches:
            finite_numbers = batch_numbers[np.isfinite(batch_numbers)]

            source_start: int | None = None
            if finite_numbers.size:
                source_start = int(round(float(finite_numbers[0])))

            emit(
                {
                    "type": "samples",
                    "batch": {
                        "sequenceStart": sequence_start,
                        "timestampStartMs": 0,
                        "sampleRateHz": self._sample_rate_hz,
                        "sampleCount": int(batch_eeg.shape[1]),
                        "channelCount": int(batch_eeg.shape[0]),
                        "values": batch_eeg.tolist(),
                        "sourceSampleNumberStart": source_start,
                    },
                }
            )


SESSION = BrainAccessSession()


def response_ok(request_id: str, result: Any = None) -> None:
    emit(
        {
            "type": "response",
            "id": request_id,
            "ok": True,
            "result": result,
        }
    )


def response_error(request_id: str, exc: Exception) -> None:
    emit(
        {
            "type": "response",
            "id": request_id,
            "ok": False,
            "error": str(exc),
        }
    )


def handle_request(request: dict[str, Any]) -> bool:
    request_id = str(request.get("id", ""))
    command = str(request.get("command", ""))
    payload = request.get("payload") or {}

    try:
        if command == "ping":
            response_ok(
                request_id,
                {
                    "protocolVersion": PROTOCOL_VERSION,
                },
            )

        elif command == "scan":
            response_ok(request_id, SESSION.scan())

        elif command == "connect":
            device_name = str(payload.get("deviceName", "")).strip()

            if not device_name:
                raise RuntimeError("connect requires payload.deviceName.")

            response_ok(request_id, SESSION.connect(device_name))

        elif command == "stream_info":
            response_ok(request_id, SESSION.connection_info())

        elif command == "start_stream":
            response_ok(request_id, SESSION.start_stream())

        elif command == "stop_stream":
            response_ok(request_id, SESSION.stop_stream())

        elif command == "disconnect":
            response_ok(request_id, SESSION.disconnect())

        elif command == "shutdown":
            SESSION.shutdown()
            response_ok(request_id, {"shutdown": True})
            return False

        else:
            raise RuntimeError(f'Unknown BrainAccess bridge command "{command}".')

    except Exception as exc:
        response_error(request_id, exc)

    return True


def main() -> None:
    emit(
        {
            "type": "ready",
            "protocolVersion": PROTOCOL_VERSION,
        }
    )

    try:
        for raw_line in sys.stdin:
            line = raw_line.strip()

            if not line:
                continue

            try:
                request = json.loads(line)

                if not isinstance(request, dict):
                    raise RuntimeError("Protocol request must be a JSON object.")

            except Exception as exc:
                emit(
                    {
                        "type": "bridge-error",
                        "message": f"Invalid JSON request: {exc}",
                    }
                )
                continue

            if not handle_request(request):
                break

    finally:
        try:
            SESSION.shutdown()
        except Exception as exc:
            log(f"BrainAccess shutdown warning: {exc}")


if __name__ == "__main__":
    main()
