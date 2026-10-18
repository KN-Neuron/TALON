"""Acquisition/decoder tests without Bluetooth; no synthetic fallback in production."""
import threading
import time
import unittest
import numpy as np
from talon_eeg import Session, CHANNELS, FREQUENCIES, DIRECTIONS


class EegTests(unittest.TestCase):
    def session(self):
        session = Session()
        session.connected = True
        session.begin("trial")
        return session

    def feed(self, session, data):
        session.event({"type": "samples", "batch": {"values": data}})

    def test_channel_mapping_and_all_four_directions(self):
        for frequency, direction in zip(FREQUENCIES, DIRECTIONS):
            session = self.session()
            t = np.arange(1000) / 250
            rng = np.random.default_rng(42)
            data = rng.normal(0, .03, (32, 1000))
            for index in CHANNELS:
                data[index] += np.sin(2*np.pi*frequency*t) + .3*np.sin(4*np.pi*frequency*t)
            # Non-SSVEP channels contain a different, stronger frequency.
            for index in set(range(32)) - set(CHANNELS):
                data[index] += 100*np.sin(2*np.pi*FREQUENCIES[(FREQUENCIES.index(frequency)+1)%4]*t)
            self.feed(session, data)
            result = session.classify("trial", 4)
            self.assertEqual(result["direction"], direction)
            self.assertEqual(result["sampleCount"], 1000)
            with self.assertRaises(RuntimeError):
                session.classify("trial", 4)  # cannot replay the same capture

    def test_new_capture_discards_old_samples(self):
        session = self.session()
        self.feed(session, np.ones((32, 1000)))
        session.begin("next")
        self.assertEqual(session.count, 0)
        self.assertEqual(session.blocks, [])

    def test_cancel_wakes_waiter_and_rejects_old_capture(self):
        session = self.session()
        errors = []
        def wait():
            try:
                session.classify("trial", 4)
            except RuntimeError as error:
                errors.append(str(error))
        worker = threading.Thread(target=wait)
        worker.start()
        time.sleep(.05)
        session.cancel()
        worker.join(1)
        self.assertFalse(worker.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertEqual(session.count, 0)

    def test_flat_signal_and_wrong_montage_cannot_classify(self):
        session = self.session()
        self.feed(session, np.ones((32, 1000)))
        with self.assertRaises(ValueError):
            session.classify("trial", 4)
        session.begin("bad")
        self.feed(session, np.zeros((8, 10)))
        with self.assertRaises(RuntimeError):
            session.classify("bad", 4)

    def test_capture_memory_is_bounded(self):
        session = self.session()
        for _ in range(100):
            self.feed(session, np.zeros((32, 100)))
        self.assertLessEqual(session.count, 3000)
        session.cancel()
        self.feed(session, np.zeros((32, 100)))
        self.assertEqual(session.count, 0)

    def test_requires_connection(self):
        with self.assertRaises(RuntimeError):
            Session().begin("trial")


if __name__ == "__main__":
    unittest.main()
