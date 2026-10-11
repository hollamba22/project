#!/usr/bin/env python3
"""Parser for Intel 5300 CSI Tool .dat files.

This parser intentionally uses only the Python standard library so it can run on
the receiver PC without installing numpy/matplotlib.
"""

import argparse
import json
import math
import os
import struct
import sys
from collections import Counter


CSI_CODE = 0xBB
NUM_SUBCARRIERS = 30


class CSIParseError(Exception):
    pass


def _u16_le(buf, offset):
    return struct.unpack_from("<H", buf, offset)[0]


def _u32_le(buf, offset):
    return struct.unpack_from("<I", buf, offset)[0]


def _i8(value):
    value &= 0xFF
    return value - 256 if value >= 128 else value


def _byte_to_signed(value):
    value &= 0xFF
    return value - 256 if value >= 128 else value


def dbinv(value_db):
    """Convert a power value in dB to a linear ratio."""
    return 10.0 ** (float(value_db) / 10.0)


def get_total_rss_dbm(record):
    """Match the Intel CSI Tool get_total_rss.m calculation."""
    rssi_mag = 0.0
    for key in ("rssi_a", "rssi_b", "rssi_c"):
        value = float(record.get(key, 0) or 0)
        if value != 0:
            rssi_mag += dbinv(value)
    if rssi_mag <= 0:
        return None
    return 10.0 * math.log10(rssi_mag) - 44.0 - float(record.get("agc", 0) or 0)


def get_scaled_csi(record):
    """Return CSI scaled to sqrt(SNR), following get_scaled_csi.m."""
    csi = record["csi"]
    csi_power = 0.0
    for subcarrier in csi:
        for rx_values in subcarrier:
            for value in rx_values:
                csi_power += (value.real * value.real) + (value.imag * value.imag)

    total_rss_dbm = get_total_rss_dbm(record)
    if csi_power <= 0 or total_rss_dbm is None:
        raise CSIParseError("cannot scale CSI with zero CSI/RSSI power")

    rssi_power = dbinv(total_rss_dbm)
    scale = rssi_power / (csi_power / float(NUM_SUBCARRIERS))
    noise_db = -92 if int(record.get("noise", -127)) == -127 else int(record["noise"])
    thermal_noise_power = dbinv(noise_db)
    quant_error_power = scale * int(record["Nrx"]) * int(record["Ntx"])
    total_noise_power = thermal_noise_power + quant_error_power
    if total_noise_power <= 0:
        raise CSIParseError("cannot scale CSI with zero noise power")

    multiplier = math.sqrt(scale / total_noise_power)
    if int(record["Ntx"]) == 2:
        multiplier *= math.sqrt(2.0)
    elif int(record["Ntx"]) == 3:
        multiplier *= math.sqrt(dbinv(4.5))

    return [
        [
            [value * multiplier for value in tx_values]
            for tx_values in subcarrier
        ]
        for subcarrier in csi
    ]


def apply_rx_permutation(csi, perm, nrx):
    """Reorder decoded RX rows into physical antenna order."""
    active_perm = list(perm[:nrx])
    valid = sorted(active_perm) == list(range(1, nrx + 1))
    if nrx <= 1 or not valid:
        return csi, valid

    corrected = []
    for subcarrier in csi:
        physical_rows = [None for _ in range(nrx)]
        for raw_rx, physical_rx in enumerate(active_perm):
            physical_rows[physical_rx - 1] = list(subcarrier[raw_rx])
        corrected.append(physical_rows)
    return corrected, True


class TimestampUnwrapper(object):
    """Unwrap the NIC's 32-bit microsecond timestamp."""

    def __init__(self):
        self.last_raw = None
        self.offset = 0

    def update(self, raw_value):
        raw_value = int(raw_value)
        if self.last_raw is not None and raw_value < self.last_raw:
            if self.last_raw - raw_value > (1 << 31):
                self.offset += 1 << 32
        self.last_raw = raw_value
        return raw_value + self.offset


def iter_csi_records(path, limit=None, strict=False):
    """Yield parsed CSI records from a log_to_file .dat file.

    Output record fields:
      - csi: shape [30 subcarrier][Nrx][Ntx], complex values
      - rssi_a/rssi_b/rssi_c, noise, agc, rate, perm, etc.
    """
    count = 0
    with open(path, "rb") as f:
        offset = 0
        while True:
            length_bytes = f.read(2)
            if not length_bytes:
                break
            if len(length_bytes) != 2:
                if strict:
                    raise CSIParseError("truncated length field at byte {}".format(offset))
                break

            field_len = struct.unpack(">H", length_bytes)[0]
            offset += 2
            if field_len == 0:
                msg = "record with length=0 at byte {}".format(offset - 2)
                if strict:
                    raise CSIParseError(msg)
                break
            if field_len > 4096:
                msg = "record length {} exceeds 4096 at byte {}".format(field_len, offset - 2)
                if strict:
                    raise CSIParseError(msg)
                break

            payload = f.read(field_len)
            if len(payload) != field_len:
                if strict:
                    raise CSIParseError("truncated record at byte {}".format(offset))
                break
            offset += field_len

            code = payload[0]
            if code != CSI_CODE:
                continue

            try:
                record = parse_bfee_payload(payload[1:])
            except CSIParseError:
                if strict:
                    raise
                continue

            record["record_index"] = count
            record["entry_size"] = field_len
            record["code"] = code
            count += 1
            yield record
            if limit is not None and count >= limit:
                break


def parse_bfee_payload(buf):
    """Parse the body after the 0xBB code byte."""
    if len(buf) < 20:
        raise CSIParseError("beamforming payload is too short: {}".format(len(buf)))

    timestamp_low = _u32_le(buf, 0)
    bfee_count = _u16_le(buf, 4)
    nrx = buf[8]
    ntx = buf[9]
    rssi_a = buf[10]
    rssi_b = buf[11]
    rssi_c = buf[12]
    noise = _i8(buf[13])
    agc = buf[14]
    antenna_sel = buf[15]
    csi_len = _u16_le(buf, 16)
    rate = _u16_le(buf, 18)

    if nrx <= 0 or ntx <= 0 or nrx > 3 or ntx > 3:
        raise CSIParseError("invalid antenna dimensions Nrx={} Ntx={}".format(nrx, ntx))

    calc_len = (NUM_SUBCARRIERS * (nrx * ntx * 8 * 2 + 3) + 7) // 8
    if csi_len != calc_len:
        raise CSIParseError(
            "wrong CSI matrix size: len={} expected={} Nrx={} Ntx={}".format(
                csi_len, calc_len, nrx, ntx
            )
        )

    csi_payload = buf[20:20 + csi_len]
    if len(csi_payload) < csi_len:
        raise CSIParseError("truncated CSI matrix payload")

    csi = []
    index = 0
    for _subcarrier in range(NUM_SUBCARRIERS):
        index += 3
        remainder = index % 8
        subcarrier_values = [[0j for _ in range(ntx)] for _ in range(nrx)]
        for j in range(nrx * ntx):
            byte_index = index // 8
            if byte_index + 2 >= len(csi_payload):
                raise CSIParseError("CSI payload ended while decoding matrix")

            real_raw = (
                (csi_payload[byte_index] >> remainder)
                | (csi_payload[byte_index + 1] << (8 - remainder))
            )
            imag_raw = (
                (csi_payload[byte_index + 1] >> remainder)
                | (csi_payload[byte_index + 2] << (8 - remainder))
            )
            real = _byte_to_signed(real_raw)
            imag = _byte_to_signed(imag_raw)

            # MATLAB read_bfee stores values with Ntx as the fastest-changing
            # dimension. Expose a clearer Python shape: [subcarrier][rx][tx].
            tx = j % ntx
            rx = j // ntx
            subcarrier_values[rx][tx] = complex(real, imag)
            index += 16
        csi.append(subcarrier_values)

    perm = [
        (antenna_sel & 0x3) + 1,
        ((antenna_sel >> 2) & 0x3) + 1,
        ((antenna_sel >> 4) & 0x3) + 1,
    ]

    csi, permutation_valid = apply_rx_permutation(csi, perm, nrx)

    return {
        "timestamp_low": timestamp_low,
        "bfee_count": bfee_count,
        "Nrx": nrx,
        "Ntx": ntx,
        "rssi_a": rssi_a,
        "rssi_b": rssi_b,
        "rssi_c": rssi_c,
        "noise": noise,
        "agc": agc,
        "perm": perm,
        "permutation_valid": permutation_valid,
        "csi_rx_order": "physical" if permutation_valid else "raw",
        "rate": rate,
        "rate_hex": "0x{:04x}".format(rate),
        "csi_len": csi_len,
        "csi": csi,
    }


def record_amplitude_stats(record):
    values = []
    for sub in record["csi"]:
        for rx_values in sub:
            for value in rx_values:
                values.append(abs(value))
    if not values:
        return {"mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0}
    mean = sum(values) / len(values)
    var = sum((x - mean) ** 2 for x in values) / len(values)
    return {
        "mean": mean,
        "std": math.sqrt(var),
        "min": min(values),
        "max": max(values),
    }


def summarize_file(path, limit=None):
    rates = Counter()
    dims = Counter()
    record_count = 0
    first = None
    last = None
    amp_mean_sum = 0.0
    amp_std_sum = 0.0
    amp_min = None
    amp_max = None
    rssi_sums = {"rssi_a": 0, "rssi_b": 0, "rssi_c": 0}
    noise_values = Counter()
    agc_values = Counter()
    permutations = Counter()
    invalid_permutation_count = 0
    unwrapper = TimestampUnwrapper()
    first_timestamp = None
    last_timestamp = None
    previous_timestamp = None
    gaps_gt_50ms = 0
    gaps_gt_100ms = 0
    max_gap_us = 0

    for record in iter_csi_records(path, limit=limit):
        if first is None:
            first = slim_record(record)
        last = slim_record(record)
        record_count += 1
        rates[record["rate_hex"]] += 1
        dims["{}x{}".format(record["Nrx"], record["Ntx"])] += 1
        noise_values[str(record["noise"])] += 1
        agc_values[str(record["agc"])] += 1
        permutations["-".join(str(value) for value in record["perm"][:record["Nrx"]])] += 1
        if not record["permutation_valid"]:
            invalid_permutation_count += 1

        timestamp = unwrapper.update(record["timestamp_low"])
        if first_timestamp is None:
            first_timestamp = timestamp
        if previous_timestamp is not None:
            gap_us = max(0, timestamp - previous_timestamp)
            max_gap_us = max(max_gap_us, gap_us)
            if gap_us > 50000:
                gaps_gt_50ms += 1
            if gap_us > 100000:
                gaps_gt_100ms += 1
        previous_timestamp = timestamp
        last_timestamp = timestamp
        for key in rssi_sums:
            rssi_sums[key] += record[key]

        stats = record_amplitude_stats(record)
        amp_mean_sum += stats["mean"]
        amp_std_sum += stats["std"]
        amp_min = stats["min"] if amp_min is None else min(amp_min, stats["min"])
        amp_max = stats["max"] if amp_max is None else max(amp_max, stats["max"])

    file_bytes = os.path.getsize(path)
    summary = {
        "path": path,
        "file_bytes": file_bytes,
        "record_count": record_count,
        "rates": dict(rates),
        "antenna_dimensions": dict(dims),
        "first_record": first,
        "last_record": last,
        "rssi_average": {},
        "noise_values": dict(noise_values),
        "agc_values": dict(agc_values),
        "permutations": dict(permutations),
        "invalid_permutation_count": invalid_permutation_count,
        "timestamp": {
            "duration_sec": (
                (last_timestamp - first_timestamp) / 1000000.0
                if first_timestamp is not None and last_timestamp is not None else None
            ),
            "gaps_gt_50ms": gaps_gt_50ms,
            "gaps_gt_100ms": gaps_gt_100ms,
            "max_gap_ms": max_gap_us / 1000.0,
        },
        "amplitude": {
            "mean_of_packet_means": None,
            "mean_of_packet_stds": None,
            "min": amp_min,
            "max": amp_max,
        },
    }
    if record_count:
        summary["rssi_average"] = {
            key: value / float(record_count) for key, value in rssi_sums.items()
        }
        summary["amplitude"]["mean_of_packet_means"] = amp_mean_sum / float(record_count)
        summary["amplitude"]["mean_of_packet_stds"] = amp_std_sum / float(record_count)
    return summary


def slim_record(record):
    keys = [
        "record_index", "entry_size", "code", "timestamp_low", "bfee_count",
        "Nrx", "Ntx", "rssi_a", "rssi_b", "rssi_c", "noise", "agc",
        "perm", "permutation_valid", "csi_rx_order", "rate_hex", "csi_len",
    ]
    return {key: record[key] for key in keys}


def write_packet_csv(path, out_csv, limit=None):
    with open(out_csv, "w") as out:
        out.write(
            "packet_index,timestamp_low,bfee_count,Nrx,Ntx,rate_hex,"
            "rssi_a,rssi_b,rssi_c,noise,agc,amp_mean,amp_std,amp_min,amp_max\n"
        )
        for idx, record in enumerate(iter_csi_records(path, limit=limit)):
            stats = record_amplitude_stats(record)
            out.write(
                "{idx},{timestamp_low},{bfee_count},{Nrx},{Ntx},{rate_hex},"
                "{rssi_a},{rssi_b},{rssi_c},{noise},{agc},"
                "{mean:.6f},{std:.6f},{min:.6f},{max:.6f}\n".format(
                    idx=idx,
                    timestamp_low=record["timestamp_low"],
                    bfee_count=record["bfee_count"],
                    Nrx=record["Nrx"],
                    Ntx=record["Ntx"],
                    rate_hex=record["rate_hex"],
                    rssi_a=record["rssi_a"],
                    rssi_b=record["rssi_b"],
                    rssi_c=record["rssi_c"],
                    noise=record["noise"],
                    agc=record["agc"],
                    mean=stats["mean"],
                    std=stats["std"],
                    min=stats["min"],
                    max=stats["max"],
                )
            )


def main(argv=None):
    parser = argparse.ArgumentParser(description="Parse Intel 5300 CSI Tool .dat files")
    parser.add_argument("csi_file", help="path to csi.dat")
    parser.add_argument("--limit", type=int, default=None, help="max CSI records to parse")
    parser.add_argument("--summary-json", help="write summary JSON to this path")
    parser.add_argument("--packet-csv", help="write per-packet amplitude summary CSV")
    parser.add_argument("--pretty", action="store_true", help="pretty-print summary JSON")
    args = parser.parse_args(argv)

    summary = summarize_file(args.csi_file, limit=args.limit)
    json_text = json.dumps(
        summary,
        ensure_ascii=False,
        indent=2 if args.pretty else None,
        sort_keys=True,
    )
    if args.summary_json:
        parent = os.path.dirname(args.summary_json)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(args.summary_json, "w", encoding="utf-8") as f:
            f.write(json_text)
            f.write("\n")
    else:
        print(json_text)

    if args.packet_csv:
        parent = os.path.dirname(args.packet_csv)
        if parent:
            os.makedirs(parent, exist_ok=True)
        write_packet_csv(args.csi_file, args.packet_csv, limit=args.limit)

    if summary["record_count"] == 0:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
