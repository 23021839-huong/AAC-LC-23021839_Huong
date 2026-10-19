"""Integration contract: real FDK output must reflect the selected window policy."""
import argparse
import csv
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
import wave

MODES = {
    "SINE_ONLY": [0, 0, 0, 0],
    "KBD_ONLY": [1, 1, 1, 1],
    "SINE_LONG_KBD_SHORT": [0, 0, 1, 0],
    "KBD_LONG_SINE_SHORT": [1, 1, 0, 1],
}
SEQUENCES = ["ONLY_LONG_SEQUENCE", "LONG_START_SEQUENCE",
             "EIGHT_SHORT_SEQUENCE", "LONG_STOP_SEQUENCE"]


def fixture(path, channels=1):
    # Deterministic attacks separated by quiet intervals, not a mock transform.
    samples = []
    state = 12345
    for n in range(48000):
        state = (1664525 * state + 1013904223) & 0xffffffff
        active = (n % 12000) < 2500 and n > 4000
        v = ((state >> 16) - 32768) // 2 if active else 0
        samples.extend([v] * channels)
    with wave.open(str(path), "wb") as f:
        f.setparams((channels, 2, 48000, 0, "NONE", "not compressed"))
        f.writeframes(struct.pack("<" + "h" * len(samples), *samples))


class NativeWindowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.wav = self.root / "attacks.wav"
        fixture(self.wav)

    def tearDown(self):
        self.tmp.cleanup()

    def run_encoder(self, mode, channels=1):
        if channels != 1:
            fixture(self.wav, channels)
        folder = self.root / mode
        p = subprocess.run([str(BINARY), "--input", str(self.wav), "--output-dir", str(folder),
                            "--mode", mode, "--runs", "2"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        return folder

    def test_four_policies_reach_bitstream_and_preserve_sequence(self):
        sequences = []
        bitstreams = []
        for mode, table in MODES.items():
            folder = self.run_encoder(mode)
            with (folder / "frame_trace.csv").open() as trace:
                rows = list(csv.DictReader(trace))
            meta = json.loads((folder / "run_metadata.json").read_text())
            self.assertTrue(meta["complete"])
            self.assertEqual(len(meta["encoding_time_ms"]), 2)
            self.assertGreater(min(meta["encoding_time_ms"]), 0)
            self.assertEqual(meta["target_bitrate_bps"], 64000)
            self.assertEqual(meta["decoder_errors"], 0)
            self.assertTrue(meta["measured_bitstreams_equal_warmup"])
            self.assertEqual(len(rows), meta["adts_frames"])
            self.assertEqual(set(r["window_sequence"] for r in rows), set(SEQUENCES))
            last_shape = 0
            for r in rows:
                seq = int(r["window_sequence_id"])
                self.assertEqual(int(r["window_shape"]), table[seq])
                self.assertEqual(int(r["previous_window_shape"]), last_shape)
                last_shape = table[seq]
            # Read the actual shape/sequence bits independently from mono ADTS.
            data = (folder / "encoded.aac").read_bytes()
            pos = 0
            for r in rows:
                length = ((data[pos+3] & 3) << 11) | (data[pos+4] << 3) | (data[pos+5] >> 5)
                self.assertEqual((data[pos+2] >> 6) + 1, 2)
                header = 7 if data[pos+1] & 1 else 9
                bits = "".join(f"{b:08b}" for b in data[pos+header:pos+length])
                self.assertEqual(int(bits[:3], 2), 0)  # SCE
                self.assertEqual(int(bits[16:18], 2), int(r["window_sequence_id"]))
                self.assertEqual(int(bits[18], 2), int(r["window_shape"]))
                pos += length
            self.assertEqual(pos, len(data))
            sequences.append([r["window_sequence_id"] for r in rows])
            bitstreams.append(data)
            with wave.open(str(folder / "decoded.wav")) as f:
                self.assertEqual(f.getframerate(), 48000)
                self.assertEqual(f.getnchannels(), 1)
                self.assertGreaterEqual(f.getnframes(), 48000 + meta["encoder_delay_samples"])
        self.assertTrue(all(s == sequences[0] for s in sequences))
        self.assertEqual(len(set(bitstreams)), 4)

    def test_stereo_policy_applied_to_both_channels(self):
        folder = self.run_encoder("KBD_LONG_SINE_SHORT", 2)
        with (folder / "frame_trace.csv").open() as trace:
            rows = list(csv.DictReader(trace))
        self.assertEqual(set(int(r["channel"]) for r in rows), {0, 1})
        for r in rows:
            self.assertEqual(int(r["window_shape"]), 0 if int(r["window_sequence_id"]) == 2 else 1)
        with wave.open(str(folder / "decoded.wav")) as f:
            self.assertEqual(f.getnchannels(), 2)

    def test_invalid_mode_fails_without_success_metadata(self):
        folder = self.root / "invalid"
        p = subprocess.run([str(BINARY), "--input", str(self.wav), "--output-dir", str(folder),
                            "--mode", "INVALID"], capture_output=True, text=True)
        self.assertNotEqual(p.returncode, 0)
        self.assertFalse((folder / "run_metadata.json").exists())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True)
    args, rest = parser.parse_known_args()
    BINARY = Path(args.binary).resolve()
    unittest.main(argv=[__file__] + rest)
