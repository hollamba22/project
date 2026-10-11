#!/usr/bin/env python3
"""Simple traffic generator for CSI collection tests."""

import argparse
import os
import socket
import sys
import time
import json
import math
import re


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send controlled UDP or TCP traffic to a receiver."
    )
    parser.add_argument("--target", required=True, help="Receiver IP address")
    parser.add_argument("--port", type=int, default=5005, help="Target port")
    parser.add_argument(
        "--mode",
        choices=("udp", "tcp"),
        default="udp",
        help="Traffic mode. UDP is recommended for CSI smoke tests.",
    )
    parser.add_argument("--duration", type=float, default=60.0, help="Seconds to run")
    parser.add_argument("--rate", type=float, default=20.0, help="Packets per second")
    parser.add_argument("--size", type=int, default=512, help="Payload bytes")
    parser.add_argument("--session-nonce", default=None, help="Optional CSI1 session tag (64 hex digits)")
    parser.add_argument("--result-json", default=None, help="Write machine-readable sender result")
    parser.add_argument(
        "--bind",
        default=None,
        help="Optional local source IP, useful when multiple interfaces exist.",
    )
    return parser.parse_args()


def make_payload(size: int) -> bytes:
    if size <= 0:
        raise ValueError("--size must be positive")
    seed = b"wifi-csi-test:"
    repeats = (size // len(seed)) + 1
    return (seed * repeats)[:size]


def send_udp(args: argparse.Namespace) -> int:
    payload = make_payload(args.size)
    nonce = getattr(args, "session_nonce", None)
    if nonce:
        prefix = b"CSI1:" + nonce.encode("ascii") + b":"
        if len(prefix) > len(payload):
            raise ValueError("payload too small for session tag")
        payload = prefix + payload[len(prefix):]
    interval = 1.0 / args.rate if args.rate > 0 else 0.0
    end_at = time.monotonic() + args.duration
    count = 0

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(5)
        if args.bind:
            sock.bind((args.bind, 0))
        next_send = time.monotonic()
        while time.monotonic() < end_at:
            sock.sendto(payload, (args.target, args.port))
            count += 1
            next_send += interval
            sleep_for = next_send - time.monotonic()
            if sleep_for > 0:
                time.sleep(sleep_for)

    return count


def send_tcp(args: argparse.Namespace) -> int:
    payload = make_payload(args.size)
    interval = 1.0 / args.rate if args.rate > 0 else 0.0
    end_at = time.monotonic() + args.duration
    count = 0

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        if args.bind:
            sock.bind((args.bind, 0))
        sock.settimeout(5)
        sock.connect((args.target, args.port))
        next_send = time.monotonic()
        while time.monotonic() < end_at:
            sock.sendall(payload)
            count += 1
            next_send += interval
            sleep_for = next_send - time.monotonic()
            if sleep_for > 0:
                time.sleep(sleep_for)

    return count


def main() -> int:
    args = parse_args()
    if not math.isfinite(args.duration) or args.duration <= 0:
        print("--duration must be positive", file=sys.stderr)
        return 2
    if not math.isfinite(args.rate) or args.rate <= 0:
        print("--rate must be positive", file=sys.stderr)
        return 2

    if args.size <= 0 or args.size > 65507 or (args.session_nonce and
            (not re.fullmatch(r"[0-9a-f]{64}", args.session_nonce) or args.size < 70)):
        print("invalid size or session nonce", file=sys.stderr)
        return 2

    started = time.time()
    print(
        f"Sending {args.mode.upper()} to {args.target}:{args.port} "
        f"for {args.duration:g}s at {args.rate:g} pkt/s, payload={args.size}B"
    )
    if args.bind:
        print(f"Binding source IP: {args.bind}")

    try:
        sent = send_udp(args) if args.mode == "udp" else send_tcp(args)
    except OSError as exc:
        print(f"send failed: {exc}", file=sys.stderr)
        return 1

    elapsed = max(time.time() - started, 1e-9)
    if args.result_json:
        with open(args.result_json, "x", encoding="utf-8") as handle:
            json.dump({"sent": sent, "elapsed_sec": elapsed, "duration_sec": args.duration,
                       "rate": args.rate, "size": args.size, "exit_code": 0}, handle)
    print(f"Done. Sent {sent} packets in {elapsed:.2f}s ({sent / elapsed:.1f} pkt/s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
