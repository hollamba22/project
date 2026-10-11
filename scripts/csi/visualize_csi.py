#!/usr/bin/env python3
"""Create simple CSI amplitude visualizations without external packages."""

import argparse
import json
import math
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from csi_parser import iter_csi_records, summarize_file, write_packet_csv  # noqa: E402


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def esc(text):
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def collect_amplitude_series(csi_file, limit=None):
    packet_means = []
    subcarrier_means = []
    pair_sums = {}
    pair_counts = {}
    metadata = {
        "record_count": 0,
        "Nrx": None,
        "Ntx": None,
        "rate_hex": None,
    }

    for record in iter_csi_records(csi_file, limit=limit):
        metadata["record_count"] += 1
        metadata["Nrx"] = record["Nrx"]
        metadata["Ntx"] = record["Ntx"]
        metadata["rate_hex"] = record["rate_hex"]

        packet_sum = 0.0
        packet_count = 0
        per_subcarrier = []

        for sub_idx, sub in enumerate(record["csi"]):
            sub_sum = 0.0
            sub_count = 0
            for rx_idx, rx_values in enumerate(sub):
                for tx_idx, value in enumerate(rx_values):
                    amp = abs(value)
                    sub_sum += amp
                    sub_count += 1
                    packet_sum += amp
                    packet_count += 1
                    key = (rx_idx + 1, tx_idx + 1)
                    pair_sums[key] = pair_sums.get(key, 0.0) + amp
                    pair_counts[key] = pair_counts.get(key, 0) + 1
            per_subcarrier.append(sub_sum / float(sub_count or 1))

        packet_means.append(packet_sum / float(packet_count or 1))
        subcarrier_means.append(per_subcarrier)

    pair_means = {
        key: pair_sums[key] / float(pair_counts[key])
        for key in sorted(pair_sums)
    }
    return {
        "packet_means": packet_means,
        "subcarrier_means": subcarrier_means,
        "pair_means": pair_means,
        "metadata": metadata,
    }


def downsample(values, max_points):
    if len(values) <= max_points:
        return values
    bucket_size = int(math.ceil(len(values) / float(max_points)))
    result = []
    for start in range(0, len(values), bucket_size):
        chunk = values[start:start + bucket_size]
        result.append(sum(chunk) / float(len(chunk)))
    return result


def downsample_matrix_rows(matrix, max_cols):
    if len(matrix) <= max_cols:
        return matrix
    bucket_size = int(math.ceil(len(matrix) / float(max_cols)))
    result = []
    for start in range(0, len(matrix), bucket_size):
        chunk = matrix[start:start + bucket_size]
        cols = len(chunk[0])
        averaged = []
        for col in range(cols):
            averaged.append(sum(row[col] for row in chunk) / float(len(chunk)))
        result.append(averaged)
    return result


def percentile(values, p):
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = int(round((len(ordered) - 1) * p))
    idx = max(0, min(len(ordered) - 1, idx))
    return ordered[idx]


def color_scale(value, vmin, vmax):
    if vmax <= vmin:
        t = 0.5
    else:
        t = (value - vmin) / float(vmax - vmin)
    t = max(0.0, min(1.0, t))

    # Four-point palette: navy -> blue -> yellow -> red.
    stops = [
        (0.0, (25, 35, 95)),
        (0.35, (49, 130, 189)),
        (0.70, (255, 221, 87)),
        (1.0, (203, 52, 52)),
    ]
    for i in range(len(stops) - 1):
        left_t, left_c = stops[i]
        right_t, right_c = stops[i + 1]
        if left_t <= t <= right_t:
            local = (t - left_t) / float(right_t - left_t)
            rgb = tuple(
                int(left_c[j] + (right_c[j] - left_c[j]) * local)
                for j in range(3)
            )
            return "#{:02x}{:02x}{:02x}".format(*rgb)
    return "#{:02x}{:02x}{:02x}".format(*stops[-1][1])


def write_line_svg(values, path, title, y_label="mean amplitude", max_points=1200):
    values = downsample(values, max_points)
    width, height = 1100, 420
    left, right, top, bottom = 70, 25, 45, 55
    plot_w = width - left - right
    plot_h = height - top - bottom

    if values:
        vmin, vmax = min(values), max(values)
    else:
        vmin, vmax = 0.0, 1.0
    if vmax <= vmin:
        vmax = vmin + 1.0

    points = []
    denom = max(1, len(values) - 1)
    for i, value in enumerate(values):
        x = left + (i / float(denom)) * plot_w
        y = top + (1.0 - ((value - vmin) / float(vmax - vmin))) * plot_h
        points.append("{:.2f},{:.2f}".format(x, y))

    with open(path, "w", encoding="utf-8") as f:
        f.write('<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">\n'.format(w=width, h=height))
        f.write('<rect width="100%" height="100%" fill="white"/>\n')
        f.write('<text x="{x}" y="25" font-size="18" font-family="sans-serif" font-weight="700">{title}</text>\n'.format(x=left, title=esc(title)))
        f.write('<line x1="{l}" y1="{b}" x2="{r}" y2="{b}" stroke="#333"/>\n'.format(l=left, r=left + plot_w, b=top + plot_h))
        f.write('<line x1="{l}" y1="{t}" x2="{l}" y2="{b}" stroke="#333"/>\n'.format(l=left, t=top, b=top + plot_h))
        for tick in range(5):
            ratio = tick / 4.0
            y = top + (1.0 - ratio) * plot_h
            value = vmin + ratio * (vmax - vmin)
            f.write('<line x1="{l}" y1="{y:.2f}" x2="{r}" y2="{y:.2f}" stroke="#e0e0e0"/>\n'.format(l=left, r=left + plot_w, y=y))
            f.write('<text x="8" y="{y:.2f}" font-size="11" font-family="monospace">{value:.1f}</text>\n'.format(y=y + 4, value=value))
        if points:
            f.write('<polyline fill="none" stroke="#1f77b4" stroke-width="1.4" points="{}"/>\n'.format(" ".join(points)))
        f.write('<text x="{x}" y="{y}" text-anchor="middle" font-size="12" font-family="sans-serif">packet index (downsampled if needed)</text>\n'.format(x=left + plot_w / 2, y=height - 15))
        f.write('<text x="15" y="{y}" transform="rotate(-90 15,{y})" text-anchor="middle" font-size="12" font-family="sans-serif">{label}</text>\n'.format(y=top + plot_h / 2, label=esc(y_label)))
        f.write('</svg>\n')


def write_heatmap_svg(matrix, path, title, max_cols=900):
    matrix = downsample_matrix_rows(matrix, max_cols)
    rows = 30
    cols = len(matrix)
    cell_w = 1.0 if cols == 0 else max(1.0, 900.0 / cols)
    cell_h = 12
    left, top = 85, 50
    width = int(left + max(900, cols * cell_w) + 35)
    height = int(top + rows * cell_h + 70)

    flat = [value for row in matrix for value in row]
    vmin = percentile(flat, 0.05)
    vmax = percentile(flat, 0.95)

    with open(path, "w", encoding="utf-8") as f:
        f.write('<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">\n'.format(w=width, h=height))
        f.write('<rect width="100%" height="100%" fill="white"/>\n')
        f.write('<text x="{x}" y="25" font-size="18" font-family="sans-serif" font-weight="700">{title}</text>\n'.format(x=left, title=esc(title)))
        f.write('<text x="{x}" y="{y}" font-size="12" font-family="sans-serif">subcarrier</text>\n'.format(x=8, y=top + rows * cell_h / 2))
        for sub in range(rows):
            y = top + sub * cell_h
            if sub % 5 == 0:
                f.write('<text x="{x}" y="{y}" font-size="10" font-family="monospace">{label}</text>\n'.format(x=left - 28, y=y + 9, label=sub + 1))
            for col, row in enumerate(matrix):
                value = row[sub]
                color = color_scale(value, vmin, vmax)
                x = left + col * cell_w
                f.write('<rect x="{x:.2f}" y="{y:.2f}" width="{cw:.2f}" height="{ch}" fill="{color}"/>\n'.format(x=x, y=y, cw=cell_w + 0.2, ch=cell_h, color=color))
        f.write('<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="none" stroke="#333"/>\n'.format(x=left, y=top, w=max(900, cols * cell_w), h=rows * cell_h))
        f.write('<text x="{x}" y="{y}" text-anchor="middle" font-size="12" font-family="sans-serif">packet index (downsampled if needed)</text>\n'.format(x=left + max(900, cols * cell_w) / 2, y=height - 18))
        f.write('<text x="{x}" y="{y}" font-size="11" font-family="monospace">color range: p05={vmin:.1f}, p95={vmax:.1f}</text>\n'.format(x=left, y=height - 42, vmin=vmin, vmax=vmax))
        f.write('</svg>\n')


def write_bar_svg(pair_means, path, title):
    items = sorted(pair_means.items())
    width, height = 760, 420
    left, right, top, bottom = 70, 30, 45, 80
    plot_w = width - left - right
    plot_h = height - top - bottom
    max_value = max([value for _key, value in items] or [1.0])
    bar_gap = 10
    bar_w = (plot_w - bar_gap * max(0, len(items) - 1)) / float(max(1, len(items)))

    with open(path, "w", encoding="utf-8") as f:
        f.write('<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">\n'.format(w=width, h=height))
        f.write('<rect width="100%" height="100%" fill="white"/>\n')
        f.write('<text x="{x}" y="25" font-size="18" font-family="sans-serif" font-weight="700">{title}</text>\n'.format(x=left, title=esc(title)))
        f.write('<line x1="{l}" y1="{b}" x2="{r}" y2="{b}" stroke="#333"/>\n'.format(l=left, r=left + plot_w, b=top + plot_h))
        f.write('<line x1="{l}" y1="{t}" x2="{l}" y2="{b}" stroke="#333"/>\n'.format(l=left, t=top, b=top + plot_h))
        for idx, ((rx, tx), value) in enumerate(items):
            x = left + idx * (bar_w + bar_gap)
            bar_h = (value / max_value) * plot_h
            y = top + plot_h - bar_h
            label = "R{}T{}".format(rx, tx)
            f.write('<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" fill="#4c78a8"/>\n'.format(x=x, y=y, w=bar_w, h=bar_h))
            f.write('<text x="{x:.2f}" y="{y}" text-anchor="middle" font-size="11" font-family="monospace">{label}</text>\n'.format(x=x + bar_w / 2, y=height - 55, label=label))
            f.write('<text x="{x:.2f}" y="{y:.2f}" text-anchor="middle" font-size="10" font-family="monospace">{value:.1f}</text>\n'.format(x=x + bar_w / 2, y=y - 4, value=value))
        f.write('<text x="{x}" y="{y}" text-anchor="middle" font-size="12" font-family="sans-serif">antenna pair</text>\n'.format(x=left + plot_w / 2, y=height - 18))
        f.write('</svg>\n')


def write_index_html(outdir, csi_file, summary):
    html_path = os.path.join(outdir, "index.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write("<!doctype html><html><head><meta charset='utf-8'>")
        f.write("<title>CSI visualization</title>")
        f.write("<style>body{font-family:sans-serif;max-width:1100px;margin:24px auto;line-height:1.45}code,pre{background:#f4f4f4;padding:2px 4px}img{max-width:100%;border:1px solid #ddd;margin:12px 0}</style>")
        f.write("</head><body>")
        f.write("<h1>CSI visualization</h1>")
        f.write("<p><b>CSI file:</b> <code>{}</code></p>".format(esc(csi_file)))
        f.write("<pre>{}</pre>".format(esc(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))))
        for name in ["amplitude_over_time.svg", "subcarrier_heatmap.svg", "antenna_pair_mean.svg"]:
            f.write("<h2>{}</h2><img src='{}'>".format(esc(name), esc(name)))
        f.write("</body></html>")
    return html_path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Visualize Intel 5300 CSI amplitude")
    parser.add_argument("csi_file", help="path to csi.dat")
    parser.add_argument("--outdir", help="output directory")
    parser.add_argument("--limit", type=int, default=None, help="max CSI records to parse")
    parser.add_argument("--max-heatmap-cols", type=int, default=900)
    args = parser.parse_args(argv)

    session_name = os.path.basename(os.path.dirname(os.path.abspath(args.csi_file))) or "session"
    outdir = args.outdir or os.path.join("outputs", "csi_visualizations", session_name)
    ensure_dir(outdir)

    summary = summarize_file(args.csi_file, limit=args.limit)
    series = collect_amplitude_series(args.csi_file, limit=args.limit)

    summary_path = os.path.join(outdir, "summary.json")
    packet_csv_path = os.path.join(outdir, "packet_amplitude_summary.csv")
    line_svg_path = os.path.join(outdir, "amplitude_over_time.svg")
    heatmap_svg_path = os.path.join(outdir, "subcarrier_heatmap.svg")
    pair_svg_path = os.path.join(outdir, "antenna_pair_mean.svg")

    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    write_packet_csv(args.csi_file, packet_csv_path, limit=args.limit)
    write_line_svg(
        series["packet_means"],
        line_svg_path,
        "CSI mean amplitude over time - {}".format(session_name),
    )
    write_heatmap_svg(
        series["subcarrier_means"],
        heatmap_svg_path,
        "CSI subcarrier amplitude heatmap - {}".format(session_name),
        max_cols=args.max_heatmap_cols,
    )
    write_bar_svg(
        series["pair_means"],
        pair_svg_path,
        "CSI mean amplitude by antenna pair - {}".format(session_name),
    )
    html_path = write_index_html(outdir, args.csi_file, summary)

    print("Wrote {}".format(summary_path))
    print("Wrote {}".format(packet_csv_path))
    print("Wrote {}".format(line_svg_path))
    print("Wrote {}".format(heatmap_svg_path))
    print("Wrote {}".format(pair_svg_path))
    print("Wrote {}".format(html_path))
    return 0 if summary["record_count"] else 2


if __name__ == "__main__":
    sys.exit(main())
