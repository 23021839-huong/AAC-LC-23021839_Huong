"""Measure real AAC round trips. NumPy is used for metrics/alignment, not MDCT."""
import argparse
import json
from pathlib import Path
import wave
import numpy as np

SAMPLE_RATES = [96000, 88200, 64000, 48000, 44100, 32000, 24000,
                22050, 16000, 12000, 11025, 8000, 7350]


def pcm_float(pcm):
    pcm = np.asarray(pcm)
    return pcm.astype(np.float64) / 32768.0 if np.issubdtype(pcm.dtype, np.integer) else pcm.astype(np.float64)


def read_pcm_wav(path):
    """Read integer WAV without changing rate/channels/gain. Units: full scale."""
    with wave.open(str(path), "rb") as f:
        rate, channels, width, count = f.getframerate(), f.getnchannels(), f.getsampwidth(), f.getnframes()
        raw = f.readframes(count)
    if len(raw) != count * channels * width:
        raise ValueError("Truncated PCM WAV")
    if width == 1:
        values = (np.frombuffer(raw, np.uint8).astype(np.float64) - 128) / 128
    elif width == 2:
        values = np.frombuffer(raw, "<i2").astype(np.float64) / 32768
    elif width == 3:
        b = np.frombuffer(raw, np.uint8).reshape(-1, 3).astype(np.int32)
        values = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        values = ((values ^ 0x800000) - 0x800000).astype(np.float64) / 8388608
    elif width == 4:
        values = np.frombuffer(raw, "<i4").astype(np.float64) / 2147483648
    else:
        raise ValueError("Metrics reader requires integer PCM8/16/24/32 WAV")
    return values.reshape(-1, channels), rate


def distortion_metrics(original, decoded):
    x, y = pcm_float(original), pcm_float(decoded)
    if x.shape != y.shape or not x.size:
        raise ValueError("Metrics require matching nonempty PCM arrays")
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError("Metrics require finite PCM")
    error_energy = float(np.sum((x - y) ** 2, dtype=np.float64))
    reference_energy = float(np.sum(x ** 2, dtype=np.float64))
    result = {"mse": error_energy / x.size, "mse_units": "full_scale_squared",
              "reference_energy": reference_energy, "error_energy": error_energy,
              "metric_status": "ok"}
    if reference_energy == 0:
        result.update(snr_db=None, nrmse_percent=None, metric_status="zero_reference_energy")
    else:
        result["nrmse_percent"] = 100 * float(np.sqrt(error_energy / reference_energy))
        result["snr_db"] = float(10 * np.log10(reference_energy / error_energy)) if error_energy else float("inf")
    return result


def align_pcm(original, decoded, expected_delay, search_radius=1024):
    """Recover sample lag with normalized correlation on a strong 4096-sample probe.

    Keep all original samples. No gain correction, resampling or error-minimizing
    shift beyond the stated delay search. Reject ambiguous/weak correlation.
    """
    x, y = pcm_float(original), pcm_float(decoded)
    if x.ndim == 1:
        x = x[:, None]
    if y.ndim == 1:
        y = y[:, None]
    if x.ndim != 2 or y.ndim != 2 or x.shape[1] != y.shape[1] or not len(x):
        raise ValueError("Alignment requires matching nonempty channel arrays")
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError("Alignment requires finite PCM")
    channel = int(np.argmax(np.sum(x * x, axis=0)))
    if float(np.sum(x[:, channel] ** 2)) == 0:
        raise ValueError("Cannot align reference with zero energy")
    size = min(4096, len(x))
    starts = np.arange(0, max(1, len(x) - size + 1), max(1, size // 2))
    energies = [float(np.sum(x[s:s+size, channel] ** 2)) for s in starts]
    start = int(starts[int(np.argmax(energies))])
    probe = x[start:start+size, channel]
    probe = probe - probe.mean()
    probe_energy = float(probe @ probe)
    if probe_energy == 0:
        raise ValueError("Cannot align reference without varying probe energy")
    low = max(0, int(expected_delay) - int(search_radius))
    high = min(int(expected_delay) + int(search_radius), len(y) - start - size)
    if high < low:
        raise ValueError("Decoded signal cannot cover alignment probe")
    segment = y[start+low:start+high+size, channel]
    sums = np.concatenate([[0.0], np.cumsum(segment)])
    squares = np.concatenate([[0.0], np.cumsum(segment * segment)])
    energy = squares[size:] - squares[:-size] - (sums[size:] - sums[:-size]) ** 2 / size
    numerators = np.correlate(segment, probe, mode="valid")
    denom = np.sqrt(np.maximum(energy, 0) * probe_energy)
    scores = np.divide(numerators, denom, out=np.full_like(numerators, -np.inf), where=denom > 0)
    best = int(np.argmax(scores))
    correlation = float(scores[best])
    # A low-frequency probe has a broad correlation main lobe: neighboring
    # samples on that same slope are not independent delay hypotheses.
    # Compare distinct local maxima, retaining search endpoints and plateaus
    # so genuinely periodic/ambiguous probes are still rejected.
    competitors = np.r_[0, np.flatnonzero((scores[1:-1] >= scores[:-2]) &
                                         (scores[1:-1] >= scores[2:])) + 1, len(scores)-1]
    competitors = competitors[competitors != best]
    next_best = float(np.max(scores[competitors])) if len(competitors) else -1.0
    if not np.isfinite(correlation) or correlation < 0.4 or correlation - next_best < 0.005:
        raise ValueError(f"Cannot establish reliable sample alignment: correlation={correlation:.6g}, runner_up={next_best:.6g}")
    lag = low + best
    if lag + len(x) > len(y):
        raise ValueError("Decoded signal cannot cover every original sample after alignment")
    aligned = y[lag:lag+len(x)]
    return aligned, {"alignment_delay_samples": lag, "expected_delay_samples": int(expected_delay),
                     "alignment_search_radius": int(search_radius), "alignment_correlation": correlation,
                     "alignment_runner_up_correlation": next_best, "alignment_probe_start_sample": start,
                     "alignment_competitor_rule": "distinct_local_maxima_and_search_endpoints",
                     "alignment_probe_samples": size, "alignment_channel": channel,
                     "compared_samples_per_channel": len(x), "compared_scalar_samples": x.size,
                     "leading_trim_samples": lag, "trailing_padding_samples": len(y)-lag-len(x),
                     "gain_correction": False, "resampling": False}


class Bits:
    def __init__(self, data):
        self.data, self.position = data, 0

    def take(self, n):
        if self.position + n > len(self.data) * 8:
            raise ValueError("Truncated AAC element")
        value = 0
        for _ in range(n):
            value = (value << 1) | ((self.data[self.position // 8] >> (7 - self.position % 8)) & 1)
            self.position += 1
        return value


def first_ics(payload):
    """Independent syntax probe for the first mono SCE or stereo CPE ICS.

    No spectral decoding. Non-common CPE's second ICS is verified by the native
    decoder, not by this header-only probe.
    """
    bits = Bits(payload)
    kind = bits.take(3)
    if kind not in (0, 1):
        raise ValueError(f"First audio element is not SCE/CPE (id={kind})")
    tag = bits.take(4)
    common = bits.take(1) if kind == 1 else 0
    if not common:
        bits.take(8)  # global_gain
    if bits.take(1):
        raise ValueError("ics_reserved_bit is nonzero")
    sequence, shape = bits.take(2), bits.take(1)
    return {"element_id": kind, "element_tag": tag, "common_window": common,
            "window_sequence_id": sequence, "window_shape": shape}


def inspect_adts(data, inspect_ics=False):
    frames, position, headers = [], 0, 0
    config = None
    while position < len(data):
        if len(data) - position < 7:
            raise ValueError("truncated ADTS header")
        b = data[position:position+7]
        if b[0] != 255 or b[1] & 0xf6 != 0xf0:
            raise ValueError("Invalid ADTS sync/layer")
        aot, rate_id = (b[2] >> 6) + 1, (b[2] >> 2) & 15
        channels = ((b[2] & 1) << 2) | (b[3] >> 6)
        if aot != 2 or rate_id >= len(SAMPLE_RATES) or channels not in (1, 2):
            raise ValueError("Expected AAC-LC mono/stereo ADTS configuration")
        if b[6] & 3:
            raise ValueError("Multiple raw data blocks per ADTS frame unsupported")
        size = ((b[3] & 3) << 11) | (b[4] << 3) | (b[5] >> 5)
        header = 7 if b[1] & 1 else 9
        if size < header or position + size > len(data):
            raise ValueError("truncated ADTS frame")
        current = (aot, SAMPLE_RATES[rate_id], channels)
        if config is not None and current != config:
            raise ValueError("ADTS configuration changes inside file")
        config = current
        frame = {"frame_index": len(frames), "offset_bytes": position, "frame_bytes": size, "header_bytes": header}
        if inspect_ics:
            frame.update(first_ics(data[position+header:position+size]))
        frames.append(frame)
        headers += header
        position += size
    if not frames:
        raise ValueError("Empty ADTS file")
    duration = len(frames) * 1024 / config[1]
    return {"adts_frames": len(frames), "sample_rate": config[1], "channels": config[2], "aot": config[0],
            "coded_samples_per_channel": len(frames) * 1024, "coded_duration_seconds": duration,
            "aac_size_bytes": len(data), "header_bytes": headers, "payload_bytes": len(data)-headers,
            "actual_bitrate_kbps": len(data) * 8 / duration / 1000,
            "payload_bitrate_kbps": (len(data)-headers) * 8 / duration / 1000, "frames": frames}


def measure_files(original_path, decoded_path, expected_delay):
    original, sample_rate = read_pcm_wav(original_path)
    decoded, decoded_rate = read_pcm_wav(decoded_path)
    if sample_rate != decoded_rate:
        raise ValueError("Sample rates differ; resampling is not part of this experiment")
    aligned, alignment = align_pcm(original, decoded, expected_delay)
    return {**alignment, **distortion_metrics(original, aligned), "sample_rate": sample_rate,
            "channels": original.shape[1], "source_duration_seconds": len(original) / sample_rate}, aligned


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("original", type=Path)
    parser.add_argument("decoded", type=Path)
    parser.add_argument("--expected-delay", type=int, required=True)
    args = parser.parse_args()
    result, _ = measure_files(args.original, args.decoded, args.expected_delay)
    print(json.dumps(result, indent=2))
