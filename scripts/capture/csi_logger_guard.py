#!/usr/bin/env python3
"""Run the privileged CSI logger until stdin requests shutdown or closes."""

import argparse
import select
import signal
import subprocess
import sys
import os
import time


STOP_REQUESTED = False


def request_stop(_signum, _frame):
    global STOP_REQUESTED
    STOP_REQUESTED = True


def stop_child(child):
    if child.poll() is not None:
        return child.returncode
    for signal_value, timeout_sec in (
        (signal.SIGINT, 5.0),
        (signal.SIGTERM, 3.0),
        (signal.SIGKILL, 2.0),
    ):
        child.send_signal(signal_value)
        try:
            return child.wait(timeout=timeout_sec)
        except subprocess.TimeoutExpired:
            continue
    return child.poll()


def netlink_ready(pid):
    with open("/proc/net/netlink") as handle:
        for line in handle.readlines()[1:]:
            fields = line.split()
            if len(fields) >= 4 and fields[1] == "11" and fields[2] == str(pid):
                return int(fields[3], 16) != 0
    return False


def run(command, ready_json=False):
    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGHUP, request_stop)

    child = subprocess.Popen(command, stdout=sys.stderr if ready_json else None)
    intentional_stop = False
    try:
        if ready_json:
            deadline = time.monotonic() + 8
            while child.poll() is None and not STOP_REQUESTED:
                if netlink_ready(child.pid) and os.path.isfile(command[-1]):
                    print('{"ready": true}', flush=True)
                    break
                if time.monotonic() > deadline:
                    raise RuntimeError("logger netlink preparation timeout")
                time.sleep(0.05)
        while child.poll() is None:
            if STOP_REQUESTED:
                intentional_stop = True
                break
            readable, _, _ = select.select([sys.stdin], [], [], 0.25)
            if readable:
                # A command or EOF means the controlling capture process ended.
                sys.stdin.readline()
                intentional_stop = True
                break
    finally:
        if child.poll() is None:
            stop_child(child)

    if intentional_stop:
        return 0 if child.poll() is not None else 1
    return child.returncode if child.returncode is not None else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description="Guard a CSI logger subprocess")
    parser.add_argument("--ready-json", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if not args.command:
        parser.error("a logger command is required")
    return run(args.command, args.ready_json)


if __name__ == "__main__":
    sys.exit(main())
