#!/usr/bin/env python3
"""Create a meta.json file for one CSI capture session."""

import argparse
import copy
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CSI_SCRIPT_DIR = os.path.join(PROJECT_ROOT, "scripts", "csi")
if CSI_SCRIPT_DIR not in sys.path:
    sys.path.insert(0, CSI_SCRIPT_DIR)

from csi_parser import summarize_file  # noqa: E402


KST = timezone(timedelta(hours=9))


def run_text(command):
    try:
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            universal_newlines=True,
            timeout=3,
            check=False,
        )
    except Exception:
        return ""
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def load_template(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=False)
        f.write("\n")


def parse_session_time(session_id):
    match = re.fullmatch(r"session_(\d{8})_(\d{6})", session_id)
    if not match:
        return None
    date_part, time_part = match.groups()
    try:
        return datetime.strptime(date_part + time_part, "%Y%m%d%H%M%S").replace(tzinfo=KST)
    except ValueError:
        return None


def bool_arg(value):
    if isinstance(value, bool):
        return value
    lowered = value.lower()
    if lowered in {"1", "true", "yes", "y"}:
        return True
    if lowered in {"0", "false", "no", "n"}:
        return False
    raise argparse.ArgumentTypeError("expected true/false, got {}".format(value))


def wifi_channel_from_freq(freq_mhz):
    if freq_mhz is None:
        return None
    if 2412 <= freq_mhz <= 2472:
        return int((freq_mhz - 2407) / 5)
    if freq_mhz == 2484:
        return 14
    if 5000 <= freq_mhz <= 5900:
        return int((freq_mhz - 5000) / 5)
    return None


def parse_iw_link(text):
    info = {
        "ap_bssid": "",
        "ap_ssid": "",
        "ap_frequency_mhz": None,
        "signal_dbm": None,
        "rx_bitrate_observed": "",
        "tx_bitrate_observed": "",
    }
    first = re.search(r"Connected to ([0-9a-f:]{17})", text, re.IGNORECASE)
    if first:
        info["ap_bssid"] = first.group(1).lower()
    ssid = re.search(r"^\s*SSID:\s*(.+)$", text, re.MULTILINE)
    if ssid:
        info["ap_ssid"] = ssid.group(1).strip()
    freq = re.search(r"^\s*freq:\s*(\d+)", text, re.MULTILINE)
    if freq:
        info["ap_frequency_mhz"] = int(freq.group(1))
    signal = re.search(r"^\s*signal:\s*(-?\d+)\s*dBm", text, re.MULTILINE)
    if signal:
        info["signal_dbm"] = int(signal.group(1))
    tx_rate = re.search(r"^\s*tx bitrate:\s*(.+)$", text, re.MULTILINE)
    if tx_rate:
        info["tx_bitrate_observed"] = tx_rate.group(1).strip()
    return info


def parse_station_dump(text):
    info = {
        "rx_bitrate_observed": "",
        "tx_bitrate_observed": "",
        "signal_dbm": None,
    }
    rx = re.search(r"^\s*rx bitrate:\s*(.+)$", text, re.MULTILINE)
    if rx:
        info["rx_bitrate_observed"] = rx.group(1).strip()
    tx = re.search(r"^\s*tx bitrate:\s*(.+)$", text, re.MULTILINE)
    if tx:
        info["tx_bitrate_observed"] = tx.group(1).strip()
    signal = re.search(r"^\s*signal:\s*(-?\d+)\s*dBm", text, re.MULTILINE)
    if signal:
        info["signal_dbm"] = int(signal.group(1))
    return info


def parse_ip_addr(text):
    ip_match = re.search(r"\binet\s+([0-9.]+/\d+)", text)
    mac_match = re.search(r"\blink/ether\s+([0-9a-f:]{17})", text, re.IGNORECASE)
    return {
        "ip": ip_match.group(1) if ip_match else "",
        "mac": mac_match.group(1).lower() if mac_match else "",
    }


def collect_receiver_state(interface):
    state = {
        "hostname": run_text(["hostname"]),
        "kernel": run_text(["uname", "-r"]),
        "connector_log": None,
        "ip": "",
        "mac": "",
        "rx_bitrate_observed": "",
        "signal_dbm": None,
        "network": {},
    }
    connector_path = "/sys/module/iwlwifi/parameters/connector_log"
    try:
        with open(connector_path, "r", encoding="utf-8") as f:
            raw = f.read().strip()
            state["connector_log"] = int(raw)
    except Exception:
        state["connector_log"] = None

    ip_info = parse_ip_addr(run_text(["ip", "addr", "show", interface]))
    state.update(ip_info)

    iw_info = parse_iw_link(run_text(["iw", "dev", interface, "link"]))
    station_info = parse_station_dump(run_text(["iw", "dev", interface, "station", "dump"]))
    state["rx_bitrate_observed"] = station_info["rx_bitrate_observed"] or iw_info["tx_bitrate_observed"]
    state["signal_dbm"] = station_info["signal_dbm"] if station_info["signal_dbm"] is not None else iw_info["signal_dbm"]
    state["network"] = iw_info
    return state


def infer_quality_and_role(file_bytes, record_count, requested_quality, requested_role):
    if requested_quality != "auto":
        quality_status = requested_quality
    elif file_bytes <= 0:
        quality_status = "failed"
    elif record_count > 0:
        quality_status = "valid_csi"
    else:
        quality_status = "needs_review"

    if requested_role != "auto":
        dataset_role = requested_role
    elif quality_status == "failed":
        dataset_role = "failure_history"
    else:
        dataset_role = "verification_only"

    return quality_status, dataset_role


def default_use_for_training(dataset_role, explicit_value):
    if explicit_value is not None:
        return explicit_value
    return dataset_role in {"training_candidate", "test_candidate"}


def host_ip_only(value):
    if not value:
        return ""
    return str(value).split("/", 1)[0]


def create_meta(args):
    session_dir = os.path.abspath(args.session_dir)
    session_id = os.path.basename(session_dir.rstrip(os.sep))
    csi_path = os.path.join(session_dir, args.csi_file)
    meta_path = os.path.join(session_dir, "meta.json")

    if os.path.exists(meta_path) and not args.overwrite:
        raise SystemExit("{} already exists. Use --overwrite to replace it.".format(meta_path))

    template = load_template(args.template)
    meta = copy.deepcopy(template)

    file_bytes = os.path.getsize(csi_path) if os.path.exists(csi_path) else 0
    summary = None
    record_count = 0
    if file_bytes > 0:
        try:
            summary = summarize_file(csi_path)
            record_count = int(summary.get("record_count") or 0)
        except Exception:
            summary = None
            record_count = 0

    quality_status, dataset_role = infer_quality_and_role(
        file_bytes, record_count, args.quality_status, args.dataset_role
    )
    use_for_final_training = default_use_for_training(dataset_role, args.use_for_final_training)

    now = datetime.now(KST)
    session_start = parse_session_time(session_id)
    if session_start is None:
        session_start = now
    session_end = session_start + timedelta(seconds=args.duration_sec)

    receiver_state = collect_receiver_state(args.interface) if not args.no_system_probe else {
        "hostname": "",
        "kernel": "",
        "connector_log": None,
        "ip": "",
        "mac": "",
        "rx_bitrate_observed": "",
        "signal_dbm": None,
        "network": {},
    }
    network_state = receiver_state.get("network", {})
    freq_mhz = args.ap_frequency_mhz
    if freq_mhz is None:
        freq_mhz = network_state.get("ap_frequency_mhz")
    channel = args.ap_channel
    if channel is None:
        channel = wifi_channel_from_freq(freq_mhz)

    rx_ip = args.rx_ip or receiver_state.get("ip", "")

    meta["session_id"] = session_id
    meta["created_at"] = now.isoformat(timespec="seconds")
    meta["quality_status"] = quality_status
    meta["dataset_role"] = dataset_role
    meta["use_for_final_training"] = use_for_final_training

    meta["label"]["num_people"] = args.num_people
    meta["label"]["label_status"] = args.label_status
    meta["label"]["activity"] = args.activity
    meta["label"]["people_description"] = args.people_description
    meta["label"]["notes"] = args.label_notes

    meta["capture"]["duration_sec"] = args.duration_sec
    meta["capture"]["planned_duration_sec"] = args.planned_duration_sec
    meta["capture"]["start_time_local"] = session_start.strftime("%Y-%m-%d %H:%M:%S")
    meta["capture"]["end_time_local"] = session_end.strftime("%Y-%m-%d %H:%M:%S")
    meta["capture"]["csi_file"] = args.csi_file
    meta["capture"]["csi_file_bytes"] = file_bytes
    meta["capture"]["csi_record_count"] = record_count
    meta["capture"]["video_file"] = args.video_file

    meta["environment"]["room"] = args.room
    meta["environment"]["setup_id"] = args.setup_id
    meta["environment"]["empty_reference_session_id"] = args.empty_reference_session_id
    meta["environment"]["room_shape"] = args.room_shape
    meta["environment"]["room_has_wifi_rack"] = args.room_has_wifi_rack
    meta["environment"]["nearby_aps"] = args.nearby_aps
    meta["environment"]["environment_note"] = args.environment_note
    meta["environment"]["door_state"] = args.door_state
    meta["environment"]["large_objects_moved"] = args.large_objects_moved
    meta["environment"]["notes"] = args.environment_notes

    meta["layout"]["tx_position"] = args.tx_position
    meta["layout"]["rx_position"] = args.rx_position
    meta["layout"]["hotspot_position"] = args.hotspot_position
    meta["layout"]["tx_rx_distance_m"] = args.tx_rx_distance_m
    meta["layout"]["tx_height_m"] = args.tx_height_m
    meta["layout"]["rx_height_m"] = args.rx_height_m
    meta["layout"]["hotspot_height_m"] = args.hotspot_height_m
    meta["layout"]["antenna_holder"] = args.antenna_holder
    meta["layout"]["antenna_direction_fixed"] = args.antenna_direction_fixed
    meta["layout"]["antenna_notes"] = args.antenna_notes

    meta["receiver"]["hostname"] = args.rx_hostname or receiver_state.get("hostname") or "RXPC"
    meta["receiver"]["interface"] = args.interface
    meta["receiver"]["mac"] = args.rx_mac or receiver_state.get("mac", "")
    meta["receiver"]["ip"] = rx_ip
    meta["receiver"]["kernel"] = args.rx_kernel or receiver_state.get("kernel", "")
    meta["receiver"]["connector_log"] = receiver_state.get("connector_log")
    if args.connector_log is not None:
        meta["receiver"]["connector_log"] = args.connector_log
    meta["receiver"]["rx_bitrate_observed"] = args.rx_bitrate_observed or receiver_state.get("rx_bitrate_observed", "")
    meta["receiver"]["signal_dbm"] = args.signal_dbm if args.signal_dbm is not None else receiver_state.get("signal_dbm")

    meta["sender"]["hostname"] = args.sender_hostname
    meta["sender"]["interface"] = args.sender_interface
    meta["sender"]["mac"] = args.sender_mac
    meta["sender"]["ip"] = args.sender_ip
    meta["sender"]["kernel"] = args.sender_kernel
    meta["sender"]["ping_to_receiver_before_capture"] = args.ping_to_receiver_before_capture
    target = host_ip_only(rx_ip) or "<RX_IP>"
    default_sender_command = (
        "python3 scripts/sender/safe_sender.py --target {} "
        "--mode udp --duration {} --rate {} --size {}"
    ).format(target, args.duration_sec, args.sender_rate, args.sender_size)
    meta["sender"]["sender_command"] = args.sender_command or default_sender_command

    meta["network"]["ap_type"] = args.ap_type
    meta["network"]["ap_ssid"] = args.ap_ssid or network_state.get("ap_ssid", "")
    meta["network"]["ap_bssid"] = args.ap_bssid or network_state.get("ap_bssid", "")
    meta["network"]["ap_channel"] = channel
    meta["network"]["ap_frequency_mhz"] = freq_mhz
    meta["network"]["ap_band"] = args.ap_band
    meta["network"]["ap_security"] = args.ap_security
    meta["network"]["network_cidr"] = args.network_cidr

    valid_csi = record_count > 0
    meta["validation"]["file_size_checked"] = os.path.exists(csi_path)
    meta["validation"]["parse_log_checked"] = valid_csi
    meta["validation"]["parse_log_code"] = "0xBB" if valid_csi else ""
    meta["validation"]["record_count_checked"] = valid_csi
    meta["validation"]["valid_csi"] = valid_csi
    meta["validation"]["review_reason"] = args.review_reason

    if summary:
        meta.setdefault("parser_summary", {})
        meta["parser_summary"] = {
            "antenna_dimensions": summary.get("antenna_dimensions", {}),
            "rates": summary.get("rates", {}),
            "rssi_average": summary.get("rssi_average", {}),
            "amplitude": summary.get("amplitude", {}),
        }

    meta["comments"] = args.comments
    write_json(meta_path, meta)

    print("Wrote {}".format(os.path.relpath(meta_path, PROJECT_ROOT)))
    print("quality_status={}, dataset_role={}, records={}, bytes={}".format(
        quality_status, dataset_role, record_count, file_bytes
    ))


def build_parser():
    parser = argparse.ArgumentParser(description="Create meta.json for a CSI session")
    parser.add_argument("session_dir", help="session directory, e.g. data/raw/session_YYYYMMDD_HHMMSS")
    parser.add_argument("--template", default=os.path.join(PROJECT_ROOT, "templates", "session_meta_template.json"))
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--csi-file", default="csi.dat")
    parser.add_argument("--no-system-probe", action="store_true", help="do not run hostname/uname/ip/iw probes")

    parser.add_argument("--quality-status", default="auto", choices=["auto", "failed", "valid_csi", "needs_review"])
    parser.add_argument("--dataset-role", default="auto", choices=[
        "auto", "failure_history", "verification_only", "training_candidate", "test_candidate", "excluded"
    ])
    parser.add_argument("--use-for-final-training", type=bool_arg, default=None)

    parser.add_argument("--num-people", type=int, default=None)
    parser.add_argument("--label-status", default="unknown")
    parser.add_argument("--activity", default="unknown")
    parser.add_argument("--people-description", default="")
    parser.add_argument("--label-notes", default="")

    parser.add_argument("--duration-sec", type=float, default=60)
    parser.add_argument("--planned-duration-sec", type=float, default=60)
    parser.add_argument("--video-file", default=None)

    parser.add_argument("--room", default="unknown")
    parser.add_argument("--setup-id", default="unknown")
    parser.add_argument("--empty-reference-session-id", default=None)
    parser.add_argument("--room-shape", default="rectangle")
    parser.add_argument("--room-has-wifi-rack", type=bool_arg, default=False)
    parser.add_argument("--nearby-aps", default="unknown")
    parser.add_argument("--environment-note", default="")
    parser.add_argument("--door-state", default="unknown")
    parser.add_argument("--large-objects-moved", type=bool_arg, default=False)
    parser.add_argument("--environment-notes", default="")

    parser.add_argument("--tx-position", default="unknown")
    parser.add_argument("--rx-position", default="unknown")
    parser.add_argument("--hotspot-position", default="unknown")
    parser.add_argument("--tx-rx-distance-m", type=float, default=None)
    parser.add_argument("--tx-height-m", type=float, default=None)
    parser.add_argument("--rx-height-m", type=float, default=None)
    parser.add_argument("--hotspot-height-m", type=float, default=None)
    parser.add_argument("--antenna-holder", default="not_used_pre_holder")
    parser.add_argument("--antenna-direction-fixed", type=bool_arg, default=True)
    parser.add_argument("--antenna-notes", default="")

    parser.add_argument("--interface", default="wlp4s0")
    parser.add_argument("--rx-hostname", default="")
    parser.add_argument("--rx-mac", default="")
    parser.add_argument("--rx-ip", default="")
    parser.add_argument("--rx-kernel", default="")
    parser.add_argument("--connector-log", type=int, default=None)
    parser.add_argument("--rx-bitrate-observed", default="")
    parser.add_argument("--signal-dbm", type=int, default=None)

    parser.add_argument("--sender-hostname", default="")
    parser.add_argument("--sender-interface", default="wlp4s0")
    parser.add_argument("--sender-mac", default="")
    parser.add_argument("--sender-ip", default="")
    parser.add_argument("--sender-kernel", default="")
    parser.add_argument("--ping-to-receiver-before-capture", default="unknown")
    parser.add_argument("--sender-command", default="")
    parser.add_argument("--sender-rate", type=int, default=100)
    parser.add_argument("--sender-size", type=int, default=512)

    parser.add_argument("--ap-type", default="phone_hotspot")
    parser.add_argument("--ap-ssid", default="")
    parser.add_argument("--ap-bssid", default="")
    parser.add_argument("--ap-channel", type=int, default=None)
    parser.add_argument("--ap-frequency-mhz", type=int, default=None)
    parser.add_argument("--ap-band", default="2.4GHz")
    parser.add_argument("--ap-security", default="")
    parser.add_argument("--network-cidr", default="")

    parser.add_argument("--review-reason", default="")
    parser.add_argument("--comments", default="")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    create_meta(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
