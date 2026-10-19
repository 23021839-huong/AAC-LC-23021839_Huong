#!/usr/bin/env python3
"""Benchmark a PYNQ AXI DMA overlay for the QC Step 0 transfer matrix.

The default round-trip mode requires MM2S to be connected to S2MM through an
AXI4-Stream loopback. One-way modes require a hardware sink or source that
consumes or produces exactly the requested byte count.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import platform
import sys
import time
from pathlib import Path

import numpy as np
import pynq
from pynq import Overlay, allocate


def resolve_ip(overlay: Overlay, dotted_name: str):
    value = overlay
    for part in dotted_name.split("."):
        value = getattr(value, part)
    return value


def require_irq(channel, label: str) -> None:
    if getattr(channel, "_interrupt", None) is None:
        raise RuntimeError(f"{label} has no connected interrupt; IRQ mode is invalid")


async def wait_irq(dma, direction: str) -> None:
    if direction == "roundtrip":
        require_irq(dma.sendchannel, "MM2S")
        require_irq(dma.recvchannel, "S2MM")
        await asyncio.gather(
            dma.sendchannel.wait_async(), dma.recvchannel.wait_async()
        )
    elif direction == "mm2s":
        require_irq(dma.sendchannel, "MM2S")
        await dma.sendchannel.wait_async()
    else:
        require_irq(dma.recvchannel, "S2MM")
        await dma.recvchannel.wait_async()


def submit(dma, direction: str, input_buffer, output_buffer) -> None:
    if direction == "roundtrip":
        dma.recvchannel.transfer(output_buffer)
        dma.sendchannel.transfer(input_buffer)
    elif direction == "mm2s":
        dma.sendchannel.transfer(input_buffer)
    elif direction == "s2mm":
        dma.recvchannel.transfer(output_buffer)
    else:
        raise ValueError(direction)


def wait_channel_poll(channel, deadline: float) -> None:
    while not channel.idle:
        if channel.error:
            channel.wait()  # Let the PYNQ driver decode and raise the DMA error.
        if time.perf_counter() >= deadline:
            raise TimeoutError("DMA polling timeout; check sink/source and TLAST")
    channel.wait()  # Performs driver bookkeeping and cache invalidation.


def wait_poll(dma, direction: str, timeout_s: float) -> None:
    deadline = time.perf_counter() + timeout_s
    if direction == "roundtrip":
        wait_channel_poll(dma.sendchannel, deadline)
        wait_channel_poll(dma.recvchannel, deadline)
    elif direction == "mm2s":
        wait_channel_poll(dma.sendchannel, deadline)
    else:
        wait_channel_poll(dma.recvchannel, deadline)


def run_transfer(
    dma, direction: str, wait_mode: str, input_buffer, output_buffer, event_loop,
    timeout_s: float
) -> tuple[int, int]:
    wall_start = time.perf_counter_ns()
    cpu_start = time.thread_time_ns()
    submit(dma, direction, input_buffer, output_buffer)
    if wait_mode == "poll":
        wait_poll(dma, direction, timeout_s)
    else:
        event_loop.run_until_complete(
            asyncio.wait_for(wait_irq(dma, direction), timeout=timeout_s)
        )
    cpu_ns = time.thread_time_ns() - cpu_start
    wall_ns = time.perf_counter_ns() - wall_start
    return wall_ns, cpu_ns


def parse_list(value: str, converter=str) -> list:
    return [converter(item.strip()) for item in value.split(",") if item.strip()]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bitstream", type=Path, required=True)
    parser.add_argument("--dma-name", default="axi_dma_0")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sizes", default="4096,8192,16384,32768")
    parser.add_argument("--directions", default="roundtrip")
    parser.add_argument("--wait-modes", default="poll,irq")
    parser.add_argument("--cache-modes", default="cacheable,noncacheable")
    parser.add_argument("--iterations", type=int, default=200)
    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=2.0)
    parser.add_argument(
        "--allow-one-way",
        action="store_true",
        help="confirm that the overlay has the required one-way stream source/sink",
    )
    args = parser.parse_args()

    sizes = parse_list(args.sizes, int)
    directions = parse_list(args.directions)
    wait_modes = parse_list(args.wait_modes)
    cache_modes = parse_list(args.cache_modes)
    if args.iterations < 1 or args.warmup < 0 or args.timeout <= 0.0:
        parser.error("iterations/timeout must be positive and warmup non-negative")
    if not sizes or not directions or not wait_modes or not cache_modes:
        parser.error("sizes, directions, wait modes, and cache modes must be non-empty")
    if any(direction not in {"mm2s", "s2mm", "roundtrip"} for direction in directions):
        parser.error("directions must contain only mm2s, s2mm, or roundtrip")
    if any(direction != "roundtrip" for direction in directions) and not args.allow_one_way:
        parser.error("one-way DMA requires --allow-one-way and matching source/sink hardware")
    if any(mode not in {"poll", "irq"} for mode in wait_modes):
        parser.error("wait modes must contain only poll or irq")
    if any(mode not in {"cacheable", "noncacheable"} for mode in cache_modes):
        parser.error("cache modes must contain only cacheable or noncacheable")

    bitstream_path = args.bitstream.resolve()
    overlay = Overlay(str(bitstream_path), download=True)
    dma = resolve_ip(overlay, args.dma_name)
    send_channel = getattr(dma, "sendchannel", None)
    recv_channel = getattr(dma, "recvchannel", None)
    if any(direction in {"mm2s", "roundtrip"} for direction in directions) and send_channel is None:
        raise RuntimeError("requested direction requires an MM2S channel")
    if any(direction in {"s2mm", "roundtrip"} for direction in directions) and recv_channel is None:
        raise RuntimeError("requested direction requires an S2MM channel")
    if "irq" in wait_modes:
        if any(direction in {"mm2s", "roundtrip"} for direction in directions):
            require_irq(send_channel, "MM2S")
        if any(direction in {"s2mm", "roundtrip"} for direction in directions):
            require_irq(recv_channel, "S2MM")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    event_loop = asyncio.new_event_loop() if "irq" in wait_modes else None
    try:
        for size in sizes:
            if size <= 0:
                raise ValueError("DMA sizes must be positive")
            for cache_mode in cache_modes:
                requested_cacheable = cache_mode == "cacheable"
                with allocate(
                    shape=(size,), dtype=np.uint8, cacheable=requested_cacheable
                ) as input_buffer, allocate(
                    shape=(size,), dtype=np.uint8, cacheable=requested_cacheable
                ) as output_buffer:
                    actual_input_cacheable = bool(getattr(input_buffer, "cacheable", False))
                    actual_output_cacheable = bool(getattr(output_buffer, "cacheable", False))
                    if actual_input_cacheable != requested_cacheable or actual_output_cacheable != requested_cacheable:
                        raise RuntimeError(
                            "allocator did not honor requested cache mode: "
                            f"requested={cache_mode}, input={actual_input_cacheable}, "
                            f"output={actual_output_cacheable}"
                        )
                    input_buffer[:] = (np.arange(size, dtype=np.uint16) * 17 + 29) & 0xFF
                    output_buffer[:] = 0

                    for direction in directions:
                        logical_bytes = size * (2 if direction == "roundtrip" else 1)
                        submissions = 2 if direction == "roundtrip" else 1
                        for wait_mode in wait_modes:
                            for _ in range(args.warmup):
                                run_transfer(
                                    dma, direction, wait_mode, input_buffer,
                                    output_buffer, event_loop, args.timeout
                                )
                            for iteration in range(args.iterations):
                                if direction == "roundtrip":
                                    output_buffer[:] = 0
                                wall_ns, cpu_ns = run_transfer(
                                    dma, direction, wait_mode, input_buffer,
                                    output_buffer, event_loop, args.timeout
                                )
                                if direction == "roundtrip" and not np.array_equal(
                                    input_buffer, output_buffer
                                ):
                                    mismatch = int(np.flatnonzero(input_buffer != output_buffer)[0])
                                    raise RuntimeError(
                                        f"DMA loopback mismatch at byte {mismatch}, size={size}"
                                    )
                                rows.append(
                                    {
                                        "iteration": iteration,
                                        "direction": direction,
                                        "wait_mode": wait_mode,
                                        "cache_mode": cache_mode,
                                        "size_bytes": size,
                                        "wall_ns": wall_ns,
                                        "cpu_ns": cpu_ns,
                                        "logical_bus_bytes": logical_bytes,
                                        "dma_submissions": submissions,
                                    }
                                )
    finally:
        if event_loop is not None:
            event_loop.close()

    with args.output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    metadata = {
        "schema_version": 1,
        "machine": platform.machine(),
        "platform": platform.platform(),
        "python_version": sys.version,
        "pynq_version": getattr(pynq, "__version__", "unknown"),
        "bitstream": str(bitstream_path),
        "bitstream_sha256": sha256(bitstream_path),
        "dma_name": args.dma_name,
        "sizes": sizes,
        "directions": directions,
        "wait_modes": wait_modes,
        "cache_modes": cache_modes,
        "iterations": args.iterations,
        "warmup": args.warmup,
        "timeout_s": args.timeout,
        "note": "logical_bus_bytes and dma_submissions are software job-level counts, not AXI burst counts",
    }
    hwh_path = bitstream_path.with_suffix(".hwh")
    if hwh_path.is_file():
        metadata["hwh"] = str(hwh_path)
        metadata["hwh_sha256"] = sha256(hwh_path)
    args.output.with_suffix(".json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote {len(rows)} measurements to {args.output}")


if __name__ == "__main__":
    main()
