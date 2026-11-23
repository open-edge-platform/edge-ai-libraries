// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package tui

import "github.com/charmbracelet/lipgloss"

func (m Model) helpBody(width int) string {
	content := "Help - mm-tui\n\n" +
		"Navigation\n" +
		"  h: open/close help and return to the previous view.\n" +
		"  Esc: close help; otherwise close alerts or quit from a tab.\n" +
		"  q / Ctrl+C: quit, including from help or alerts.\n" +
		"  a: open/close alerts; from help, go to alerts.\n" +
		"  1 / 2 / 3 / 4: Overview / Trends / Details / Alerts.\n" +
		"  Tab / Shift+Tab or click a tab: change tab.\n\n" +
		"Processes - Overview (CPU and GPU lists)\n" +
		"  CPU processes start at the top right in multi-column layouts; one process per row.\n" +
		"  GPU processes stay inside their GPU's frame, immediately below its hardware metrics.\n" +
		"  Left / Right: scroll process columns together when a table is wider than its panel.\n" +
		"  CPU columns: PID, Process, Threads, User, Memory (RSS), CPU.\n" +
		"  Threads counts OS threads, not busy CPUs or Go goroutines; no health threshold.\n" +
		"  16 Threads on 14 logical CPUs is normal: threads may sleep or wait for CPU time.\n" +
		"  A thread runs on one logical CPU at a time and may migrate between CPUs.\n" +
		"  Logical CPUs are OS scheduling units, not necessarily physical cores (SMT).\n" +
		"  User is the real UID's name on the monitored host, or the numeric UID if unresolved.\n" +
		"  Older collectors may omit Threads/User; missing values are not zero.\n" +
		"  s: cycle sort key: usage, memory, PID.\n" +
		"  r: reverse sort direction. Current sorting is shown above each list.\n" +
		"  c: toggle process CPU per-core / total; does not affect GPU usage.\n" +
		"  total (default): 100% = the monitored host's total logical CPU capacity.\n" +
		"  per-core: diagnostic view; 100% = one logical CPU, values can exceed 100%.\n" +
		"  CPU is CPU time across all process threads divided by elapsed time, not thread count.\n" +
		"  total = per-core / monitored logical CPU count.\n" +
		"  On 14 logical CPUs: 100% per-core is about 7.1% total; 1400% is 100% total.\n" +
		"  1500% per-core means about 15 logical CPUs busy on average, e.g. 93.8% of 16 CPUs.\n" +
		"  On a fixed 14-CPU host, sustained 1500% is unexpected: check counts and sampling.\n" +
		"  Missing/invalid CPU count: total is n/a, never guessed from the TUI machine.\n" +
		"  Colors and alerts always use total host CPU thresholds, even in per-core view.\n" +
		"  Missing/invalid CPU count disables process CPU colors and alert evaluation.\n" +
		"  Set processes.cpuMode in the dashboard config to persist the startup mode.\n" +
		"  Sorting only covers processes published by the collectors.\n\n" +
		"Scrolling - Overview, Trends, alerts and help\n" +
		"  Up / Down or k / j: scroll one line.\n" +
		"  PgUp / PgDn: previous / next page. Space: next page.\n" +
		"  Home / End or g / G: first / last line.\n\n" +
		"  Highlighted viewport edges say more metrics/charts/alert details above or below.\n" +
		"  Indicators disappear at that edge when no more content is hidden.\n\n" +
		"Details - select the metric plotted above the list\n" +
		"  Arrow keys: select immediately. j / k / l: down / up / right.\n" +
		"  Use Left Arrow to move left; h opens help in every view.\n" +
		"  Enter: confirm the selected metric.\n" +
		"  PgUp / PgDn: previous / next page of metrics. Space: next page.\n" +
		"  Home / End or g / G: first / last metric.\n" +
		"  Click: select a metric. Mouse wheel: move up / down.\n" +
		"  Mouse capture enables tab clicks and scrolling; help releases it.\n" +
		"  Set mouse=false in the dashboard config to disable all capture.\n" +
		"  details.mouse=false disables only metric click/wheel selection.\n" +
		"  CPU, Memory, GPUs, NPU, Network and Storage resources have separate sections.\n\n" +
		"Reading the display\n" +
		"  Overview: current readings. Trends: multiple history charts.\n" +
		"  Overview: 3 columns on wide windows, 2 on medium, 1 on narrow windows.\n" +
		"  Wide: CPU/Memory/NPU left, GPUs with clients middle, CPU processes right.\n" +
		"  Medium: CPU/Memory/GPUs left, CPU processes then NPU right.\n" +
		"  Network/Storage fill the shortest columns below their main panels, never above them.\n" +
		"  All columns scroll together; CPU processes are not pinned to the screen.\n" +
		"  Details: one selected chart; both use 5 minutes by default.\n" +
		"  Filled plots preserve blank gaps where measurements are missing.\n" +
		"  Time buckets are anchored: closed columns move together, not regrouped per poll.\n" +
		"  Auto scales expand in steps; halving the range needs 30s before shrinking.\n" +
		"  Plots fade from dark blue at the baseline to light blue at the top of the axis.\n" +
		"  Plots use a subtle linear blue gradient, without cyan stops or accelerated brightening.\n" +
		"  Only two blue shades? Check TERM/COLORTERM; 16-color terminals cannot show the full gradient.\n" +
		"  Shades depend on height, not health or trend direction; values keep threshold colors.\n" +
		"  Nonnegative metrics default to a zero baseline, including all-zero samples.\n" +
		"  graphMode=\"braille\" (default) uses 2x4 dots per cell; requires font support.\n" +
		"  Use graphMode=\"solid\" for background spaces if dotted glyphs render poorly.\n" +
		"  Existing explicit graphMode settings are preserved; choose braille to switch.\n" +
		"  interval shows the configured TUI interval, not the collector cadence.\n" +
		"  Set -interval at startup to change it (for example -interval 1s).\n" +
		"  The fixed bottom alert preview can be disabled with alerts.bottomBar=false.\n" +
		"  Alert colors indicate configured diagnostic thresholds,\n" +
		"  not universal hardware safety limits. Press a for events.\n" +
		"  Frequency, power and bandwidth stay neutral without a configured limit.\n" +
		"  recovered: readings confirm the alert ended.\n" +
		"  no longer observed: observations stopped, not confirmed recovery.\n" +
		"  Alert evidence: activation value, peak since activation and confirmed recovery.\n" +
		"  A low last-observed value may be from the recovery-confirmation period.\n" +
		"  Process CPU alert evidence: 100% means total host CPU, regardless of display mode.\n" +
		"  Process CPU alerts need distinct timestamps within processes.maxSampleAge (default 3s).\n" +
		"  [4/a] Open alerts shows events and per-process data-quality diagnostics.\n" +
		"  Process CPU alerts: limited (CPU! on narrow screens) means incomplete evaluation,\n" +
		"  not stopped collection. The process table remains available.\n" +
		"  Cached CPU process samples older than processes.maxSampleAge are excluded before ranking.\n" +
		"  Set this duration above the collector interval plus delivery delay; range 1s to 5m.\n" +
		"  Their retention alone is informational; loss of all current CPU process data is flagged.\n" +
		"  Native CPU/GPU collection defaults to 1s; the CPU 3s age limit is not a refresh interval.\n" +
		"  GPU clients have no equivalent age cutoff; cached entries may remain for about 60s.\n" +
		"  Collection and history continue while help is open.\n\n" +
		"Network - optional Telegraf net input\n" +
		"  RX/TX rates need two distinct, timestamped counter measurements.\n" +
		"  Cached samples do not advance Network charts or alert streaks.\n" +
		"  Unknown link speed means no utilization percentage or utilization alert.\n" +
		"  network.interfaces filters exact names; network.speedMbps supplies known limits.\n" +
		"  Errors/drops use events/s, not lifetime totals; rate colors share alert thresholds.\n" +
		"  -once shows totals but cannot calculate a rate from one snapshot.\n" +
		"  See the native package guide to enable the optional input.\n\n" +
		"Storage - optional Telegraf disk and diskio inputs\n" +
		"  Filesystems show space and inode usage; Storage I/O shows block-device activity.\n" +
		"  Read/write MiB/s and IOPS need two timestamped counter samples, not two polls.\n" +
		"  Await is average completed-I/O time (including queueing), not model-load latency.\n" +
		"  No completed I/O means await is unavailable, not a measured zero.\n" +
		"  Busy time is NOT percent of maximum SSD/NVMe performance; no default I/O alerts.\n" +
		"  Space/inode thresholds default to 70/80/90%; small files can exhaust inodes.\n" +
		"  Trends default to space used and read/write transfer, five minutes in Braille.\n" +
		"  Details adds free GiB, inodes, IOPS, await, busy time and queue measurements.\n" +
		"  storage.mountPoints/devices filter exact names; maxFilesystems/maxDevices default to 4.\n" +
		"  storage.maxSampleAge defaults to 10s; stale/invalid samples cannot confirm alerts.\n" +
		"  Storage! means limited alert coverage; press a for reasons, not an all-clear.\n" +
		"  Filesystems and device layers are separate; never sum partitions and their disks.\n" +
		"  Collection is opt-in; the native guide explains permissions and protected mounts.\n\n" +
		"Startup reference - defaults, not the current session settings\n\n" +
		CommandLineHelp()
	return lipgloss.NewStyle().Width(width).Render(content)
}

func (m *Model) toggleHelp() {
	if m.showHelp {
		m.helpOffset = m.offset
		m.showHelp = false
		m.offset = m.scrollTo(m.tabOffsets[m.activeTab])
	} else {
		m.setOffset(m.offset)
		m.showHelp = true
		m.offset = m.scrollTo(m.helpOffset)
	}
}
