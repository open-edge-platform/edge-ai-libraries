#!/usr/bin/env python3
"""
Generate an HTML benchmark report with bar charts from a VIPPET benchmark JSON result.

Usage:
    python3 scripts/generate_report.py results/latest/*.json
    python3 scripts/generate_report.py results/bench_20260701_015223/bench_20260701_015223.json
    python3 scripts/generate_report.py results/bench_A.json results/bench_B.json  # compare runs
"""

import sys
import json
import argparse
from pathlib import Path
from collections import defaultdict


VARIANT_COLORS = {
    "cpu": {"bg": "rgba(5, 80, 174, 0.75)",  "border": "rgba(5, 80, 174, 1)"},
    "gpu": {"bg": "rgba(26, 127, 55, 0.75)",  "border": "rgba(26, 127, 55, 1)"},
    "npu": {"bg": "rgba(130, 80, 223, 0.75)",  "border": "rgba(130, 80, 223, 1)"},
}
DEFAULT_COLOR = {"bg": "rgba(120, 120, 130, 0.8)", "border": "rgba(120, 120, 130, 1)"}

KPI_COLORS = {
    "GPU Render %": {"bg": "rgba(26, 127, 55, 0.7)",  "border": "rgba(26, 127, 55, 1)"},
    "GPU Video %":  {"bg": "rgba(5, 80, 174, 0.7)",  "border": "rgba(5, 80, 174, 1)"},
    "NPU %":        {"bg": "rgba(130, 80, 223, 0.7)",  "border": "rgba(130, 80, 223, 1)"},
    "CPU %":        {"bg": "rgba(249, 115, 22, 0.7)",  "border": "rgba(249, 115, 22, 1)"},
    "Memory %":     {"bg": "rgba(176, 136, 0, 0.7)", "border": "rgba(176, 136, 0, 1)"},
    "GPU Power (W)":  {"bg": "rgba(26, 127, 55, 0.7)",  "border": "rgba(26, 127, 55, 1)"},
    "Pkg Power (W)":  {"bg": "rgba(5, 80, 174, 0.7)",   "border": "rgba(5, 80, 174, 1)"},
    "NPU Power (W)":  {"bg": "rgba(130, 80, 223, 0.7)", "border": "rgba(130, 80, 223, 1)"},
}


def variant_color(variant_id):
    return VARIANT_COLORS.get(variant_id.lower(), DEFAULT_COLOR)


def safe(val, decimals=1):
    if val is None:
        return None
    try:
        return round(float(val), decimals)
    except (TypeError, ValueError):
        return None


def load_results(paths):
    runs = []
    for p in paths:
        with open(p) as f:
            runs.append(json.load(f))
    return runs


def build_fps_charts(test_cases):
    """
    Build Chart.js datasets for FPS charts.
    Returns a dict: pipeline_name -> {
        "streams_x": sorted list of stream counts,
        "datasets": [{"variant_id", "variant_name", "data": [fps or null per stream]}]
    }
    """
    # Collect all data keyed by (pipeline_name, variant_id, streams)
    data = defaultdict(lambda: defaultdict(dict))
    variant_order = {}  # pipeline -> ordered variant ids

    for tc in test_cases:
        if tc["status"] != "success":
            continue
        p = tc["pipeline_name"]
        v = tc["variant_id"]
        s = tc["streams"]
        fps = safe(tc.get("result", {}).get("total_fps"), 2)
        data[p][v][s] = fps
        if p not in variant_order:
            variant_order[p] = {}
        variant_order[p][v] = tc["variant_name"]

    charts = {}
    for pipeline, variants in data.items():
        all_streams = sorted({s for vdata in variants.values() for s in vdata})
        datasets = []
        for vid, vname in sorted(variant_order[pipeline].items()):
            vdata = variants.get(vid, {})
            fps_values = [vdata.get(s) for s in all_streams]
            c = variant_color(vid)
            datasets.append({
                "label": vname,
                "variant_id": vid,
                "data": fps_values,
                "backgroundColor": c["bg"],
                "borderColor": c["border"],
                "borderWidth": 1.5,
                "borderRadius": 4,
            })
        charts[pipeline] = {"streams_x": [str(s) for s in all_streams], "datasets": datasets}

    return charts


def build_kpi_chart(test_cases, pipeline_name):
    """
    Build grouped bar charts for HW KPIs for a single pipeline.
    Returns separate chart data grouped by unit (%) so Y axes are consistent.
    X axis: variants. Multiple datasets for each KPI metric of the same unit.
    Returns dict with "utilization" chart (all % metrics on one chart).
    """
    # Only % utilization metrics — same unit, comparable on one Y axis
    kpi_keys = [
        ("gpu_render_util_pct_avg", "GPU Render %"),
        ("gpu_video_util_pct_avg",  "GPU Video %"),
        ("npu_utilization_avg",     "NPU %"),
        ("cpu_util_pct_avg",        "CPU %"),
        ("mem_used_percent_avg",    "Memory %"),
    ]

    # Collect per variant (pick streams=1 or first available)
    variant_data = {}
    for tc in test_cases:
        if tc["pipeline_name"] != pipeline_name or tc["status"] != "success":
            continue
        vid = tc["variant_id"]
        vname = tc["variant_name"]
        streams = tc["streams"]
        if vid not in variant_data or streams < variant_data[vid]["streams"]:
            variant_data[vid] = {
                "name": vname,
                "streams": streams,
                "hw": tc.get("hw_metrics") or {},
            }

    if not variant_data:
        return None

    labels = [v["name"] for v in sorted(variant_data.values(), key=lambda x: x["name"])]
    vid_order = [k for k in sorted(variant_data.keys())]

    datasets = []
    for key, label in kpi_keys:
        values = [safe(variant_data[vid]["hw"].get(key)) for vid in vid_order]
        if all(v is None or v == 0 for v in values):
            continue
        c = KPI_COLORS.get(label, DEFAULT_COLOR)
        datasets.append({
            "label": label,
            "data": values,
            "backgroundColor": c["bg"],
            "borderColor": c["border"],
            "borderWidth": 1.5,
            "borderRadius": 4,
        })

    if not datasets:
        return None

    return {"labels": labels, "datasets": datasets}


def build_power_chart(test_cases, pipeline_name):
    """
    Build grouped bar chart for power metrics (watts) for a single pipeline.
    X axis: variants. Datasets: GPU Power, Package Power, NPU Power.
    """
    power_keys = [
        ("gpu_power_w_avg",  "GPU Power (W)"),
        ("pkg_power_w_avg",  "Pkg Power (W)"),
        ("npu_power_avg",    "NPU Power (W)"),
    ]

    variant_data = {}
    for tc in test_cases:
        if tc["pipeline_name"] != pipeline_name or tc["status"] != "success":
            continue
        vid = tc["variant_id"]
        vname = tc["variant_name"]
        streams = tc["streams"]
        if vid not in variant_data or streams < variant_data[vid]["streams"]:
            variant_data[vid] = {
                "name": vname,
                "streams": streams,
                "hw": tc.get("hw_metrics") or {},
            }

    if not variant_data:
        return None

    labels = [v["name"] for v in sorted(variant_data.values(), key=lambda x: x["name"])]
    vid_order = [k for k in sorted(variant_data.keys())]

    datasets = []
    for key, label in power_keys:
        values = [safe(variant_data[vid]["hw"].get(key), 3) for vid in vid_order]
        if all(v is None or v == 0 for v in values):
            continue
        c = KPI_COLORS.get(label, DEFAULT_COLOR)
        datasets.append({
            "label": label,
            "data": values,
            "backgroundColor": c["bg"],
            "borderColor": c["border"],
            "borderWidth": 1.5,
            "borderRadius": 4,
        })

    if not datasets:
        return None

    return {"labels": labels, "datasets": datasets}


def build_summary_rows(test_cases):
    rows = []
    for tc in test_cases:
        hw = tc.get("hw_metrics") or {}
        rows.append({
            "pipeline": tc["pipeline_name"],
            "variant": tc["variant_name"],
            "streams": tc["streams"],
            "status": tc["status"],
            "total_fps": safe(tc.get("result", {}).get("total_fps"), 2) if tc["status"] == "success" else None,
            "per_stream_fps": safe(tc.get("result", {}).get("per_stream_fps"), 2) if tc["status"] == "success" else None,
            "duration_s": safe(tc.get("duration_seconds"), 1),
            "gpu_util": safe(hw.get("gpu_util_combined_avg"), 1),
            "gpu_freq": safe(hw.get("gpu_freq_mhz_avg"), 0),
            "gpu_power": safe(hw.get("gpu_power_w_avg"), 2),
            "pkg_power": safe(hw.get("pkg_power_w_avg"), 2),
            "npu_util": safe(hw.get("npu_utilization_avg"), 1),
            "npu_power": safe(hw.get("npu_power_avg"), 2),
            "cpu_util": safe(hw.get("cpu_util_pct_avg"), 1),
            "cpu_temp": safe(hw.get("cpu_temperature_avg"), 1),
            "error": tc.get("error"),
        })
    return rows


def fmt(val, suffix="", fallback="—"):
    if val is None:
        return fallback
    return f"{val}{suffix}"


def _build_sysinfo_cards(system_info):
    """Build HTML for system details cards from system_info dict."""
    if not system_info:
        return ""

    # Build System section — merge memory capacity if stored separately (old format)
    system = dict(system_info.get("system", {}))
    mem_section = system_info.get("memory", {})
    if "Memory" not in system and mem_section.get("Capacity"):
        system["Memory"] = mem_section["Capacity"]

    if not system or not any(v for v in system.values()):
        return ""

    rows = ""
    for k, v in system.items():
        val = v if v else "—"
        rows += f'<div class="si-row"><dt>{k}</dt><dd>{val}</dd></div>\n'

    return f"""
        <div class="sysinfo-card">
          <h3>System</h3>
          <dl>{rows}</dl>
        </div>"""


def generate_html(runs):
    # Merge all test cases; annotate with run id if multiple runs
    multi = len(runs) > 1
    all_cases = []
    for run in runs:
        for tc in run["test_cases"]:
            tc = dict(tc)
            tc["_run_id"] = run["benchmark_id"]
            all_cases.append(tc)

    pipelines = list(dict.fromkeys(tc["pipeline_name"] for tc in all_cases))
    fps_charts = build_fps_charts(all_cases)
    summary_rows = build_summary_rows(all_cases)

    run_meta = []
    system_info = {}
    vippet_version = ""
    for run in runs:
        hw = run.get("hardware", {})
        hw_str = ", ".join(
            f"{k}: {', '.join(v)}" for k, v in hw.items()
        )
        run_meta.append({
            "id": run["benchmark_id"],
            "timestamp": run["timestamp"][:19].replace("T", " "),
            "duration": f"{run['duration_seconds']:.1f}s",
            "hardware": hw_str,
            "summary": run["summary"],
        })
        if not system_info:
            system_info = run.get("system_info", {})
        if not vippet_version:
            vippet_version = (run.get("system_info", {}).get("software", {}).get("VIPPET", ""))

    # Build pipeline section HTML + chart data
    pipeline_sections_html = []
    chart_data_js = {}

    for pipeline in pipelines:
        pipeline_id = pipeline.lower().replace(" ", "-")

        # FPS chart
        fps = fps_charts.get(pipeline)
        fps_chart_id = f"fps_{pipeline_id}"
        chart_data_js[fps_chart_id] = fps

        # KPI chart
        kpi = build_kpi_chart(all_cases, pipeline)
        kpi_chart_id = f"kpi_{pipeline_id}"
        chart_data_js[kpi_chart_id] = kpi

        # Power chart
        pwr = build_power_chart(all_cases, pipeline)
        pwr_chart_id = f"pwr_{pipeline_id}"
        chart_data_js[pwr_chart_id] = pwr

        # Per-stream table
        cases_for_pipeline = [r for r in summary_rows if r["pipeline"] == pipeline]
        n_pass = sum(1 for r in cases_for_pipeline if r["status"] == "success")
        n_total = len(cases_for_pipeline)
        table_rows_html = []
        for r in cases_for_pipeline:
            vid = r["variant"].lower()
            status_badge = (
                '<span class="badge pass">Pass</span>' if r["status"] == "success"
                else '<span class="badge fail">Fail</span>'
            )
            row = f"""<tr>
                <td><span class="chip {vid}">{r['variant']}</span></td>
                <td class="r">{r['streams']}</td>
                <td>{status_badge}</td>
                <td class="r hi">{fmt(r['total_fps'])}</td>
                <td class="r">{fmt(r['per_stream_fps'])}</td>
                <td class="r">{fmt(r['duration_s'], 's')}</td>
                <td class="r">{fmt(r['gpu_util'], '%')}</td>
                <td class="r">{fmt(r['gpu_freq'], ' MHz')}</td>
                <td class="r">{fmt(r['gpu_power'], ' W')}</td>
                <td class="r">{fmt(r['pkg_power'], ' W')}</td>
                <td class="r">{fmt(r['npu_util'], '%')}</td>
                <td class="r">{fmt(r['npu_power'], ' W')}</td>
                <td class="r">{fmt(r['cpu_util'], '%')}</td>
                <td class="r">{fmt(r['cpu_temp'], '°C')}</td>
            </tr>"""
            table_rows_html.append(row)

        section = f"""
        <div class="section" id="{pipeline_id}">
          <div class="section-header">
            <h2>{pipeline}</h2>
            <span class="pill">{n_pass}/{n_total} passed</span>
          </div>
          <div class="chart-grid">
            <div class="chart-card">
              <div class="chart-title">Throughput — Total FPS</div>
              <canvas id="{fps_chart_id}"></canvas>
            </div>
            {"" if kpi is None else f'''
            <div class="chart-card">
              <div class="chart-title">Device Utilization % (1 stream)</div>
              <canvas id="{kpi_chart_id}"></canvas>
            </div>'''}
            {"" if pwr is None else f'''
            <div class="chart-card">
              <div class="chart-title">Power Consumption — Watts (1 stream)</div>
              <canvas id="{pwr_chart_id}"></canvas>
            </div>'''}
          </div>
          <div class="table-wrap">
            <table>
              <thead><tr>
                <th>Variant</th><th style="text-align:right">Streams</th><th>Status</th>
                <th style="text-align:right">Total FPS</th><th style="text-align:right">FPS / stream</th>
                <th style="text-align:right">Duration</th>
                <th style="text-align:right">GPU Util</th><th style="text-align:right">GPU Freq</th>
                <th style="text-align:right">GPU Power</th><th style="text-align:right">Pkg Power</th>
                <th style="text-align:right">NPU Util</th><th style="text-align:right">NPU Power</th>
                <th style="text-align:right">CPU Util</th><th style="text-align:right">CPU Temp</th>
              </tr></thead>
              <tbody>{''.join(table_rows_html)}</tbody>
            </table>
          </div>
        </div>"""
        pipeline_sections_html.append(section)

    # Summary cards
    total = sum(r["summary"]["total"] for r in run_meta)
    passed = sum(r["summary"]["success"] for r in run_meta)
    failed = sum(r["summary"]["failed"] for r in run_meta)
    skipped = sum(r["summary"].get("skipped", 0) for r in run_meta)

    meta_cards_html = ""
    for m in run_meta:
        meta_cards_html += f"""
        <div class="meta-card">
            <div class="meta-label">Run ID</div><div class="meta-val">{m['id']}</div>
            <div class="meta-label">Timestamp</div><div class="meta-val">{m['timestamp']}</div>
            <div class="meta-label">Duration</div><div class="meta-val">{m['duration']}</div>
            <div class="meta-label">Hardware</div><div class="meta-val">{m['hardware']}</div>
        </div>"""

    nav_links = " ".join(
        f'<a href="#{p.lower().replace(" ", "-")}">{p}</a>'
        for p in pipelines
    )

    chart_init_js = []
    for cid, cdata in chart_data_js.items():
        if cdata is None:
            continue
        is_kpi = cid.startswith("kpi_")
        is_pwr = cid.startswith("pwr_")
        is_variant_chart = is_kpi or is_pwr
        x_labels = json.dumps(cdata["labels"] if is_variant_chart else cdata["streams_x"])
        datasets_json = json.dumps(cdata["datasets"])
        x_title = "Variant" if is_variant_chart else "Streams"
        if is_kpi:
            y_title = "Utilization %"
        elif is_pwr:
            y_title = "Power (W)"
        else:
            y_title = "Total FPS"
        y_max = "max: 100," if is_kpi else ""
        chart_init_js.append(f"""
  new Chart(document.getElementById({json.dumps(cid)}), {{
    type: 'bar',
    data: {{ labels: {x_labels}, datasets: {datasets_json} }},
    options: {{
      responsive: true,
      maintainAspectRatio: true,
      animation: {{ duration: 600, easing: 'easeOutQuart' }},
      plugins: {{
        legend: {{
          position: 'top',
          labels: {{ color: '#4b5563', font: {{ size: 12, family: 'Inter, system-ui, sans-serif' }}, padding: 16, boxWidth: 14, boxHeight: 14 }}
        }},
        tooltip: {{
          mode: 'index', intersect: false,
          backgroundColor: '#1b1b1b', borderColor: '#d1d9e0', borderWidth: 1,
          titleColor: '#ffffff', bodyColor: '#d1d5db',
          padding: 12, cornerRadius: 6
        }}
      }},
      scales: {{
        x: {{
          title: {{ display: true, text: {json.dumps(x_title)}, color: '#6e7781', font: {{ size: 11 }} }},
          ticks: {{ color: '#4b5563', font: {{ size: 11 }} }},
          grid: {{ color: 'rgba(0,0,0,0.06)' }},
          border: {{ color: '#d1d9e0' }}
        }},
        y: {{
          title: {{ display: true, text: {json.dumps(y_title)}, color: '#6e7781', font: {{ size: 11 }} }},
          ticks: {{ color: '#4b5563', font: {{ size: 11 }} }},
          grid: {{ color: 'rgba(0,0,0,0.06)' }},
          border: {{ color: '#d1d9e0' }},
          beginAtZero: true,
          {y_max}
        }}
      }}
    }}
  }});""")

    timestamp = run_meta[0]["timestamp"] if run_meta else ""
    pass_rate = f"{round(100*passed/total)}%" if total else "—"

    processor_name = system_info.get("system", {}).get("Processor", "")
    summary_title = f"Performance Summary \u2014 {processor_name}" if processor_name else "Performance Summary"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>VIPPET Benchmark Report</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
html {{ background: #ffffff; }}

:root {{
  --bg:        #ffffff;
  --surface:   #fbfbfb;
  --surface2:  #f3f4f6;
  --surface3:  #ededed;
  --border:    #d1d9e0;
  --border2:   #e5e7eb;
  --text:      #1b1b1b;
  --text-2:    #4b5563;
  --text-3:    #6e7781;
  --ok:        #1a7f37;
  --ok-dim:    rgba(26,127,55,.1);
  --fail:      #cf222e;
  --fail-dim:  rgba(207,34,46,.1);
  --warn:      #b08800;
  --accent:    #0071c5;
  --accent-hi: #0550ae;
  --radius:    10px;
  --radius-sm: 6px;
}}

body {{
  background: var(--bg);
  color: var(--text);
  font-family: 'Inter', system-ui, -apple-system, sans-serif;
  font-size: 13px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}}

.topbar {{ box-shadow: 0 2px 4px rgba(0,0,0,.08); }}
.kpi-card, .chart-card, .table-wrap, .run-info {{ box-shadow: 0 2px 4px rgba(0,0,0,.08); }}

/* ── Header ── */
.topbar {{
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  padding: 0 40px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 56px;
  position: sticky;
  top: 0;
  z-index: 100;
}}
.topbar-left {{ display: flex; align-items: center; gap: 14px; }}
.intel-logo {{
  background: var(--accent);
  color: #ffffff;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: .5px;
  padding: 3px 9px;
  border-radius: 4px;
  text-transform: uppercase;
}}
.topbar-title {{ font-size: 15px; font-weight: 600; color: var(--text); }}
.topbar-sub {{ font-size: 12px; color: var(--text-2); margin-top: 1px; }}
.topbar-right {{ font-size: 12px; color: var(--text-3); }}

/* ── Sidebar nav ── */
.layout {{ display: flex; min-height: calc(100vh - 56px); }}
.sidebar {{
  width: 220px;
  flex-shrink: 0;
  background: var(--surface);
  border-right: 1px solid var(--border);
  padding: 20px 0;
  position: sticky;
  top: 56px;
  height: calc(100vh - 56px);
  overflow-y: auto;
}}
.sidebar-section {{ padding: 6px 16px 4px; font-size: 10px; font-weight: 600; color: var(--text-3); text-transform: uppercase; letter-spacing: .6px; }}
.sidebar a {{
  display: block;
  padding: 6px 20px;
  color: var(--text-2);
  text-decoration: none;
  font-size: 12.5px;
  border-left: 2px solid transparent;
  transition: all .15s;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}}
.sidebar a:hover {{ color: var(--text); background: var(--surface2); border-left-color: var(--accent); }}

/* ── Main content ── */
.main {{ flex: 1; min-width: 0; padding: 32px 40px; }}

/* ── Overview strip ── */
.overview {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 12px;
  margin-bottom: 32px;
}}
.kpi-card {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}}
.kpi-card .kval {{
  font-size: 28px;
  font-weight: 700;
  line-height: 1;
  letter-spacing: -.5px;
}}
.kpi-card .klbl {{
  font-size: 11px;
  color: var(--text-3);
  text-transform: uppercase;
  letter-spacing: .5px;
}}
.kpi-card.c-ok   .kval {{ color: var(--ok); }}
.kpi-card.c-fail .kval {{ color: var(--fail); }}
.kpi-card.c-acc  .kval {{ color: var(--accent-hi); }}

/* ── Run info ── */
.run-info {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px 20px;
  margin-bottom: 32px;
  box-shadow: 0 2px 4px rgba(0,0,0,.08);
}}
.run-info h3 {{
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: .5px;
  color: var(--text-3);
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border2);
}}
.run-info dl {{
  display: flex;
  flex-direction: column;
  gap: 6px;
}}
.run-info .si-row {{
  display: flex;
  justify-content: space-between;
  gap: 12px;
}}
.run-info dt {{
  font-size: 12px;
  color: var(--text-3);
  white-space: nowrap;
}}
.run-info dd {{
  font-size: 12px;
  font-weight: 500;
  color: var(--text);
  text-align: right;
  word-break: break-word;
}}

/* ── Section ── */
.section {{ margin-bottom: 52px; scroll-margin-top: 72px; }}
.section-header {{
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 20px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border2);
}}
.section-header h2 {{ font-size: 17px; font-weight: 600; }}
.section-header .pill {{
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 20px;
  background: var(--surface3);
  color: var(--text-2);
  font-weight: 500;
}}

/* ── Chart grid ── */
.chart-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));
  gap: 16px;
  margin-bottom: 16px;
}}
.chart-card {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px 20px 16px;
}}
.chart-card .chart-title {{
  font-size: 12px;
  font-weight: 600;
  color: var(--text-2);
  text-transform: uppercase;
  letter-spacing: .4px;
  margin-bottom: 16px;
}}
.chart-card canvas {{ max-height: 260px; }}

/* ── Table ── */
.table-wrap {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: auto;
}}
table {{ width: 100%; border-collapse: collapse; white-space: nowrap; }}
thead th {{
  background: var(--surface3);
  padding: 10px 14px;
  text-align: left;
  font-size: 10.5px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: .5px;
  color: var(--text-3);
  border-bottom: 1px solid var(--border);
}}
tbody td {{
  padding: 9px 14px;
  border-bottom: 1px solid var(--border2);
  font-size: 13px;
  color: var(--text);
}}
tbody tr:last-child td {{ border-bottom: none; }}
tbody tr:hover td {{ background: var(--surface2); }}
td.r {{ text-align: right; font-variant-numeric: tabular-nums; color: var(--text-2); }}
td.hi {{ color: var(--text); font-weight: 500; }}

/* ── Badges ── */
.badge {{
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 20px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: .2px;
}}
.badge::before {{ content: ''; width: 5px; height: 5px; border-radius: 50%; }}
.badge.pass {{ background: var(--ok-dim); color: var(--ok); }}
.badge.pass::before {{ background: var(--ok); }}
.badge.fail {{ background: var(--fail-dim); color: var(--fail); }}
.badge.fail::before {{ background: var(--fail); }}

/* ── Variant chips ── */
.chip {{
  display: inline-block;
  padding: 1px 7px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: .2px;
}}
.chip.cpu {{ background: rgba(0,113,197,.12); color: #0550ae; }}
.chip.gpu {{ background: rgba(26,127,55,.12); color: #1a7f37; }}
.chip.npu {{ background: rgba(176,136,0,.12);  color: #9a6700; }}

/* ── System details ── */
.sysinfo-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
  margin-bottom: 32px;
  align-items: start;
}}
.sysinfo-card {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px 20px;
  box-shadow: 0 2px 4px rgba(0,0,0,.08);
}}
.sysinfo-card h3 {{
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: .5px;
  color: var(--text-3);
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border2);
}}
.sysinfo-card dl {{
  display: flex;
  flex-direction: column;
  gap: 6px;
}}
.sysinfo-card .si-row {{
  display: flex;
  justify-content: space-between;
  gap: 12px;
}}
.sysinfo-card dt {{
  font-size: 12px;
  color: var(--text-3);
  white-space: nowrap;
}}
.sysinfo-card dd {{
  font-size: 12px;
  font-weight: 500;
  color: var(--text);
  text-align: right;
  word-break: break-word;
}}
</style>
</head>
<body>

<div class="topbar">
  <div class="topbar-left">
    <span class="intel-logo">Intel</span>
    <div>
      <div class="topbar-title">VIPPET Benchmark Report</div>
      <div class="topbar-sub">Visual Pipeline &amp; Platform Evaluation Tool</div>
    </div>
  </div>
  <div class="topbar-right">{timestamp}</div>
</div>

<div class="layout">

  <nav class="sidebar">
    <div class="sidebar-section">Overview</div>
    <a href="#overview">Summary</a>
    <div class="sidebar-section" style="margin-top:12px">Pipelines</div>
    {''.join(f'<a href="#{p.lower().replace(" ", "-")}">{p}</a>' for p in pipelines)}
  </nav>

  <main class="main">

    <div id="overview">

      <h1 style="font-size:20px; font-weight:700; margin-bottom:24px; color:var(--text);">{summary_title}</h1>

      <div class="overview">
        <div class="kpi-card">
          <span class="kval">{total}</span>
          <span class="klbl">Total Tests</span>
        </div>
        <div class="kpi-card c-ok">
          <span class="kval">{passed}</span>
          <span class="klbl">Passed</span>
        </div>
        <div class="kpi-card {'c-fail' if failed else ''}">
          <span class="kval">{failed}</span>
          <span class="klbl">Failed</span>
        </div>
        <div class="kpi-card">
          <span class="kval">{skipped}</span>
          <span class="klbl">Skipped</span>
        </div>
        <div class="kpi-card c-acc">
          <span class="kval">{len(pipelines)}</span>
          <span class="klbl">Pipelines</span>
        </div>
        <div class="kpi-card">
          <span class="kval">{pass_rate}</span>
          <span class="klbl">Pass Rate</span>
        </div>
      </div>

      <div class="sysinfo-grid">
        {_build_sysinfo_cards(system_info)}
        <div class="run-info">
          <h3>Benchmark</h3>
          <dl>
            {''.join(f'<div class="si-row"><dt>Run ID</dt><dd>{m["id"]}</dd></div><div class="si-row"><dt>Timestamp</dt><dd>{m["timestamp"]}</dd></div><div class="si-row"><dt>Duration</dt><dd>{m["duration"]}</dd></div>' for m in run_meta)}
            {f'<div class="si-row"><dt>VIPPET</dt><dd>{vippet_version}</dd></div>' if vippet_version else ''}
          </dl>
        </div>
      </div>

    </div>

    {''.join(pipeline_sections_html)}

  </main>
</div>

<script>
{''.join(chart_init_js)}
</script>
</body>
</html>"""

    return html


def main():
    parser = argparse.ArgumentParser(description="Generate HTML benchmark report from VIPPET JSON results")
    parser.add_argument("json_files", nargs="+", help="One or more benchmark JSON result files")
    parser.add_argument("-o", "--output", help="Output HTML file path (default: alongside first input as .html)")
    args = parser.parse_args()

    paths = [Path(p) for p in args.json_files]
    for p in paths:
        if not p.exists():
            print(f"Error: file not found: {p}", file=sys.stderr)
            sys.exit(1)

    runs = load_results(paths)
    html = generate_html(runs)

    if args.output:
        out = Path(args.output)
    else:
        out = paths[0].with_suffix(".html")

    out.write_text(html)
    print(f"Report saved: {out}")


if __name__ == "__main__":
    main()
