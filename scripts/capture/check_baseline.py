#!/usr/bin/env python3
"""Compare the receiver against the recorded S24+ CSI link baseline."""

import argparse
import json
import os
import re
import subprocess
import sys


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEFAULT_BASELINE = os.path.join(
    PROJECT_ROOT, "docs", "s24_capture_baseline_20260814.json"
)


def run(command, timeout=5):
    try:
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            timeout=timeout,
            check=False,
        )
    except Exception as exc:
        return 127, "", str(exc)
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def first_match(pattern, text, flags=0):
    match = re.search(pattern, text, flags)
    return match.group(1).strip() if match else None


def add_check(results, name, expected, actual, ok):
    results.append({
        "name": name,
        "expected": expected,
        "actual": actual,
        "ok": bool(ok),
    })


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Check the RX PC against the recorded S24+ capture baseline"
    )
    parser.add_argument("--baseline", default=DEFAULT_BASELINE)
    parser.add_argument("--sender-ip", default=None)
    parser.add_argument("--skip-ping", action="store_true")
    args = parser.parse_args(argv)

    with open(args.baseline, "r", encoding="utf-8") as handle:
        baseline = json.load(handle)
    required = baseline["required"]
    interface = required["interface"]
    checks = []
    warnings = []

    _, kernel, _ = run(["uname", "-r"])
    add_check(checks, "kernel", required["kernel"], kernel, kernel == required["kernel"])

    connector_path = "/sys/module/iwlwifi/parameters/connector_log"
    try:
        with open(connector_path, "r", encoding="utf-8") as handle:
            connector = handle.read().strip()
    except OSError as exc:
        connector = "unavailable: {}".format(exc)
    add_check(
        checks,
        "connector_log",
        required["connector_log"],
        connector,
        connector == required["connector_log"],
    )

    mac_path = "/sys/class/net/{}/address".format(interface)
    try:
        with open(mac_path, "r", encoding="utf-8") as handle:
            receiver_mac = handle.read().strip().lower()
    except OSError as exc:
        receiver_mac = "unavailable: {}".format(exc)
    add_check(
        checks,
        "receiver_mac",
        required["receiver_mac"],
        receiver_mac,
        receiver_mac == required["receiver_mac"].lower(),
    )

    _, link, link_error = run(["iw", "dev", interface, "link"])
    ssid = first_match(r"^\s*SSID:\s*(.+)$", link, re.MULTILINE)
    frequency = first_match(r"^\s*freq:\s*(\d+)$", link, re.MULTILINE)
    connected = "Connected to" in link
    add_check(checks, "wifi_connected", True, connected, connected)
    add_check(checks, "ssid", required["ssid"], ssid, ssid == required["ssid"])
    add_check(
        checks,
        "frequency_mhz",
        required["frequency_mhz"],
        int(frequency) if frequency else None,
        frequency is not None and int(frequency) == required["frequency_mhz"],
    )
    if link_error:
        warnings.append("iw link stderr: {}".format(link_error))

    _, info, _ = run(["iw", "dev", interface, "info"])
    channel = first_match(r"^\s*channel\s+(\d+)", info, re.MULTILINE)
    add_check(
        checks,
        "channel",
        required["channel"],
        int(channel) if channel else None,
        channel is not None and int(channel) == required["channel"],
    )

    _, power, _ = run(["iw", "dev", interface, "get", "power_save"])
    power_value = first_match(r"Power save:\s*(\w+)", power)
    add_check(
        checks,
        "power_save",
        required["power_save"],
        power_value,
        power_value == required["power_save"],
    )

    _, module_path, _ = run(["modinfo", "-n", "iwlwifi"])
    add_check(
        checks,
        "driver_module_path",
        required["driver_module_path"],
        module_path,
        module_path == required["driver_module_path"],
    )

    firmware_link = "/lib/firmware/iwlwifi-5000-2.ucode"
    firmware_target = os.path.realpath(firmware_link)
    add_check(
        checks,
        "firmware_target",
        required["firmware_target"],
        firmware_target,
        firmware_target == required["firmware_target"],
    )

    _, address_text, _ = run(["ip", "-4", "addr", "show", interface])
    ipv4_cidr = first_match(r"^\s*inet\s+([^\s]+)", address_text, re.MULTILINE)
    add_check(checks, "ipv4_assigned", "DHCP IPv4", ipv4_cidr, bool(ipv4_cidr))

    _, route_text, _ = run(["ip", "-4", "route", "show", "default", "dev", interface])
    gateway = first_match(r"\bvia\s+([^\s]+)", route_text)
    add_check(checks, "wifi_gateway", "present", gateway, bool(gateway))

    if not args.skip_ping and gateway:
        code, output, error = run(
            ["ping", "-n", "-c", "1", "-W", "2", "-I", interface, gateway],
            timeout=5,
        )
        add_check(checks, "gateway_ping", "pass", "pass" if code == 0 else "fail", code == 0)
        if code != 0 and error:
            warnings.append("gateway ping stderr: {}".format(error))

    if args.sender_ip and not args.skip_ping:
        code, output, error = run(
            ["ping", "-n", "-c", "2", "-W", "2", "-I", interface, args.sender_ip],
            timeout=7,
        )
        add_check(
            checks,
            "sender_ping",
            "pass",
            "pass" if code == 0 else "fail",
            code == 0,
        )
        if code != 0 and error:
            warnings.append("sender ping stderr: {}".format(error))
    elif not args.sender_ip:
        warnings.append("sender ping not checked; pass --sender-ip CURRENT_TX_IP")

    observed = baseline.get("observed", {})
    current_bssid = first_match(r"Connected to\s+([0-9a-f:]+)", link, re.IGNORECASE)
    print("Baseline: {}".format(baseline.get("baseline_id", args.baseline)))
    print("Recorded BSSID/IP are informational because hotspot values can change.")
    print("Current BSSID: {} (recorded: {})".format(current_bssid, observed.get("ap_bssid")))
    print("Current IPv4: {} (recorded: {})".format(ipv4_cidr, observed.get("receiver_ipv4_cidr")))
    print("")

    failed = 0
    for check in checks:
        status = "PASS" if check["ok"] else "FAIL"
        if not check["ok"]:
            failed += 1
        print("[{:<4}] {:<20} expected={!r} actual={!r}".format(
            status, check["name"], check["expected"], check["actual"]
        ))

    for warning in warnings:
        print("[WARN] {}".format(warning))

    print("")
    if failed:
        print("Baseline check failed: {} required check(s) did not pass.".format(failed))
        return 1
    print("Baseline check passed. Verify traffic-time MCS and UDP before CSI capture.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
