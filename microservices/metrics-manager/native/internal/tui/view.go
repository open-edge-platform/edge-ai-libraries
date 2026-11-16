// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package tui

import (
	"fmt"
	"math"
	"strings"
	"time"

	"github.com/charmbracelet/lipgloss"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/metrics-manager/native/internal/source"
)

// defaultWidth is used until the terminal reports its size.
const defaultWidth = 80

const (
	// panelMinWidth leaves enough room for the widest hardware tables. Wider
	// terminals gain columns only when every panel can remain readable.
	panelMinWidth = 68
	panelGap      = 3
)

// staleAfter is how old the displayed numbers may get before the freshness
// indicator is highlighted. It is a multiple of the poll interval so a single
// missed refresh does not raise a false alarm, while a service that quietly
// stopped updating does not go unnoticed.
func (m Model) staleAfter() time.Duration {
	interval := max(m.refreshInterval(), source.DefaultInterval)
	const longest = time.Duration(1<<63 - 1)
	if interval > longest/5 {
		return longest
	}
	return interval * 5
}

func (m Model) refreshInterval() time.Duration {
	if m.pollInterval <= 0 {
		return source.DefaultInterval
	}
	return m.pollInterval
}

// Styles are adaptive so the dashboard stays readable on both light and dark
// terminals rather than assuming a dark background.
var (
	titleStyle     = lipgloss.NewStyle().Bold(true)
	headingStyle   = lipgloss.NewStyle().Bold(true).Foreground(lipgloss.AdaptiveColor{Light: "27", Dark: "39"})
	borderStyle    = lipgloss.NewStyle().Foreground(lipgloss.AdaptiveColor{Light: "27", Dark: "39"})
	activeTabStyle = lipgloss.NewStyle().Bold(true).Reverse(true).
			Foreground(lipgloss.AdaptiveColor{Light: "27", Dark: "39"})
	labelStyle    = lipgloss.NewStyle().Faint(true)
	ruleStyle     = lipgloss.NewStyle().Faint(true)
	staleStyle    = lipgloss.NewStyle().Foreground(lipgloss.AdaptiveColor{Light: "130", Dark: "214"})
	errorStyle    = lipgloss.NewStyle().Foreground(lipgloss.AdaptiveColor{Light: "160", Dark: "203"})
	footerStyle   = lipgloss.NewStyle().Faint(true)
	okStyle       = lipgloss.NewStyle().Foreground(lipgloss.AdaptiveColor{Light: "28", Dark: "42"})
	carefulStyle  = lipgloss.NewStyle().Foreground(lipgloss.AdaptiveColor{Light: "27", Dark: "45"})
	warningStyle  = lipgloss.NewStyle().Foreground(lipgloss.AdaptiveColor{Light: "130", Dark: "214"})
	criticalStyle = lipgloss.NewStyle().
			Bold(true).
			Foreground(lipgloss.AdaptiveColor{Light: "160", Dark: "203"})
)

// View renders the dashboard.
//
// The body is clipped to the window and scrolled rather than left to overflow,
// because a terminal shorter than the content would otherwise drop the GPU and
// NPU panels off the bottom without saying so.
func (m Model) View() string {
	width := m.renderWidth()
	chrome := m.chromeLines(width)
	if m.height > 0 && m.height <= len(chrome)+2 {
		return strings.Join(chrome[:min(len(chrome), m.height)], "\n")
	}
	lines := m.bodyLines(width)
	rows := m.visibleRows()
	visible, offset := clip(lines, rows, m.offset)
	bottom := m.bottomAlertLines(width)
	separator := ruleStyle.Render(strings.Repeat("─", width))
	if m.showHelp || m.activeTab != DetailsTab {
		if offset > 0 {
			chrome[len(chrome)-1] = m.scrollIndicator(width, true)
		}
		if offset+len(visible) < len(lines) {
			if len(bottom) > 0 {
				bottom[0] = m.scrollIndicator(width, false)
			} else {
				separator = m.scrollIndicator(width, false)
			}
		}
	}
	out := append(chrome, visible...)
	if m.height > 0 {
		for len(out) < m.height-2-m.bottomBarRows() {
			out = append(out, "")
		}
	}
	out = append(out, bottom...)
	out = append(out, separator)
	hint := footerHint(len(lines), rows, offset)
	if m.showHelp {
		hint = strings.Replace(hint, "h help · a alerts", "h/esc back · a alerts", 1)
	} else if m.activeTab == AlertsTab {
		hint = strings.Replace(hint, "a alerts", "a/esc back", 1)
	} else if m.activeTab == DetailsTab {
		hint = "h help · a alerts · q quit · arrows select · 1/2/3/4 tabs"
	} else if m.activeTab == OverviewTab {
		hint += " · s sort · r reverse · c CPU mode · Left/Right columns"
	}
	out = append(out, fitWidth(footerStyle.Render(hint), width))
	return strings.Join(out, "\n")
}

func (m Model) scrollIndicator(width int, above bool) string {
	content := "metrics"
	switch {
	case m.showHelp:
		content = "help"
	case m.activeTab == TrendsTab:
		content = "charts"
	case m.activeTab == AlertsTab:
		content = "alert details"
	}
	direction, keys := "below", "Down/PgDn"
	if above {
		direction, keys = "above", "Up/PgUp"
	}
	label := "more " + content + " " + direction
	if len(label)+3 > width {
		label = "more " + direction
	}
	if len(label)+len(keys)+6 <= width {
		label += " | " + keys
	}
	return headingStyle.Render(fitWidth("─ "+label+" "+
		strings.Repeat("─", max(0, width-len(label)-3)), width))
}

// renderWidth is the width to lay out at. Once Bubble Tea reports the terminal
// size, the dashboard honours it instead of rendering hidden columns beyond
// the right edge.
func (m Model) renderWidth() int {
	if m.width <= 0 {
		return defaultWidth
	}

	return m.width
}

// visibleRows is how many body lines fit above the footer, or 0 when the
// window size is unknown and everything should simply be rendered.
func (m Model) visibleRows() int {
	if m.height <= 0 {
		return 0
	}
	return max(0, m.height-len(m.chromeLines(m.renderWidth()))-2-m.bottomBarRows())
}

func (m Model) chromeLines(width int) []string {
	lines := []string{m.header(width)}
	if platform := m.platformLine(); platform != "" {
		lines = append(lines, platform)
	}
	status := headingStyle.Render(fmt.Sprintf("interval: %s", m.refreshInterval()))
	if !m.config.Alerts.BottomBar {
		status += " | " + m.alertSummary(max(0, width-lipgloss.Width(status)-3))
	}
	lines = append(lines, m.tabLine(), status,
		ruleStyle.Render(strings.Repeat("─", width)))
	for i := range lines {
		lines[i] = fitWidth(lines[i], width)
	}
	return lines
}

// bodyLines contains only scrollable content; status and navigation stay fixed.
func (m Model) bodyLines(width int) []string {
	var content string
	if m.showHelp {
		content = m.helpBody(width)
	} else if m.activeTab == AlertsTab {
		content = m.alertDetails(width)
	} else if m.activeTab == TrendsTab {
		content = m.trendsGrid(width)
	} else if m.activeTab == DetailsTab {
		content = m.detailsBody(width)
	} else {
		content = m.panelGrid(width)
	}

	lines := strings.Split(strings.TrimRight(content, "\n"), "\n")
	for i := range lines {
		lines[i] = fitWidth(strings.TrimRight(lines[i], " "), width)
	}

	return lines
}

func (m Model) panelGrid(width int) string {
	widths := m.overviewColumnWidths(width)
	columns := m.overviewPrimaryColumns(width)
	var auxiliary []func(Model) string
	for _, network := range m.dash.Network {
		auxiliary = append(auxiliary, func(m Model) string { return m.networkSection(network) })
	}
	if m.dash.NetworkLimited {
		auxiliary = append(auxiliary, func(Model) string {
			return "Network\nInterface limit reached; adjust network.interfaces or network.maxInterfaces."
		})
	}
	for _, storage := range m.dash.Storage {
		auxiliary = append(auxiliary, func(m Model) string { return m.storageSection(storage) })
	}
	if m.dash.StorageLimited {
		auxiliary = append(auxiliary, func(Model) string {
			return "Storage\nResource limit reached; adjust storage.mountPoints/devices or storage.maxFilesystems/maxDevices."
		})
	}
	for _, panel := range m.dash.Optional {
		auxiliary = append(auxiliary, func(m Model) string { return m.optionalSection(panel) })
	}
	for _, render := range auxiliary {
		shortest := 0
		for i := 1; i < len(columns); i++ {
			if lipgloss.Height(columns[i]) < lipgloss.Height(columns[shortest]) {
				shortest = i
			}
		}
		column := m
		column.panelContentWidth = max(1, widths[shortest]-2)
		if columns[shortest] != "" {
			columns[shortest] += "\n\n"
		}
		columns[shortest] += framePanel(render(column), widths[shortest])
	}
	for i := range columns {
		columns[i] = lipgloss.NewStyle().Width(widths[i]).Render(columns[i])
	}
	return lipgloss.JoinHorizontal(lipgloss.Top, joinWithGap(columns, panelGap)...)
}

// Reserve more space for the six-column CPU process table than for hardware.
// Layout depends on terminal width, not changing process names or readings.
func (m Model) overviewColumnWidths(width int) []int {
	const processPanelMinWidth = 82
	columns := 1
	if width >= panelMinWidth+panelGap+processPanelMinWidth {
		columns = 2
	}
	if len(m.dash.GPUs) > 0 && width >= 2*panelMinWidth+2*panelGap+processPanelMinWidth {
		columns = 3
	}
	if columns == 1 {
		return []int{width}
	}
	extra := width - (columns-1)*(panelMinWidth+panelGap) - processPanelMinWidth
	widths := make([]int, columns)
	for i := range widths {
		widths[i] = panelMinWidth + extra/columns
	}
	widths[columns-1] = processPanelMinWidth + extra/columns + extra%columns
	return widths
}

func (m Model) overviewPrimaryColumns(width int) []string {
	widths := m.overviewColumnWidths(width)
	stacks := make([][]func(Model) string, len(widths))
	stacks[0] = append(stacks[0], Model.cpuSection)
	if len(m.dash.Processes) > 0 {
		last := len(stacks) - 1
		stacks[last] = append(stacks[last], Model.processSection)
	}
	stacks[0] = append(stacks[0], Model.memorySection)
	gpuColumn := 0
	if len(stacks) == 3 {
		gpuColumn = 1
	}
	for _, gpu := range m.dash.GPUs {
		stacks[gpuColumn] = append(stacks[gpuColumn], func(m Model) string { return m.gpuSection(gpu) })
	}
	if m.dash.NPU.Present {
		npuColumn := 0
		if len(stacks) == 2 {
			npuColumn = 1
		}
		stacks[npuColumn] = append(stacks[npuColumn], Model.npuSection)
	}
	rendered := make([]string, len(stacks))
	for i, stack := range stacks {
		column := m
		column.panelContentWidth = max(1, widths[i]-2)
		panels := make([]string, 0, len(stack))
		for _, render := range stack {
			panels = append(panels, framePanel(render(column), widths[i]))
		}
		rendered[i] = strings.Join(panels, "\n\n")
	}
	return rendered
}

func (m Model) panelWidth() int {
	if m.panelContentWidth > 0 {
		return m.panelContentWidth
	}
	width := m.renderWidth()
	columns := max(1, min(3, (width+panelGap)/(panelMinWidth+panelGap)))
	return max(1, (width-panelGap*(columns-1))/columns-2)
}

func packPanels(panels []string, width, minWidth, maxColumns int) string {
	columns := (width + panelGap) / (minWidth + panelGap)
	if columns < 1 {
		columns = 1
	}
	if columns > maxColumns {
		columns = maxColumns
	}
	if columns == 1 {
		for i := range panels {
			panels[i] = strings.TrimRight(panels[i], "\n")
		}

		return strings.Join(panels, "\n")
	}

	columnWidth := (width - panelGap*(columns-1)) / columns
	rows := make([]string, 0, (len(panels)+columns-1)/columns)
	for start := 0; start < len(panels); start += columns {
		end := start + columns
		if end > len(panels) {
			end = len(panels)
		}

		row := make([]string, 0, end-start)
		for _, content := range panels[start:end] {
			content = strings.TrimRight(content, "\n")
			row = append(row, lipgloss.NewStyle().
				Width(columnWidth).
				MaxWidth(columnWidth).
				Render(content))
		}

		rows = append(rows, lipgloss.JoinHorizontal(
			lipgloss.Top,
			joinWithGap(row, panelGap)...,
		))
	}

	return strings.Join(rows, "\n\n")
}

// joinWithGap inserts fixed-width separators between columns.
func joinWithGap(columns []string, gap int) []string {
	if len(columns) < 2 {
		return columns
	}

	out := make([]string, 0, len(columns)*2-1)
	for i, column := range columns {
		if i > 0 {
			out = append(out, strings.Repeat(" ", gap))
		}
		out = append(out, column)
	}

	return out
}

// fitWidth keeps every rendered line inside the terminal. Lip Gloss accounts
// for escape sequences and wide runes, unlike slicing the rendered string.
func fitWidth(line string, width int) string {
	if width <= 0 || lipgloss.Width(line) <= width {
		return line
	}

	return lipgloss.NewStyle().MaxWidth(width).Render(line)
}

// clip selects the visible window of lines and reports the offset actually
// used, which may be lower than requested if the content shrank.
func clip(lines []string, rows, offset int) ([]string, int) {
	if rows <= 0 || len(lines) <= rows {
		return lines, 0
	}

	if max := len(lines) - rows; offset > max {
		offset = max
	}
	if offset < 0 {
		offset = 0
	}

	return lines[offset : offset+rows], offset
}

func footerHint(total, rows, offset int) string {
	if rows <= 0 || total <= rows {
		return "h help · a alerts · q quit · 1/2/3/4 tab switch"
	}

	return fmt.Sprintf("h help · a alerts · q quit · lines %d-%d of %d · ↑↓ PgUp/PgDn g/G scroll",
		offset+1, offset+rows, total)
}

func (m Model) tabLine() string {
	tabs := m.tabLabels()
	for i, tab := range tabs {
		if Tab(i) == m.activeTab {
			tabs[i] = activeTabStyle.Render("[" + tab + "]")
		} else {
			tabs[i] = labelStyle.Render(tab)
		}
	}
	return strings.Join(tabs, "   ")
}

// platformLine names the machine under the title, and is omitted entirely on a
// host that publishes nothing about itself rather than showing a row of
// placeholders.
func (m Model) platformLine() string {
	platform := m.dash.Platform
	if platform.Model == "" {
		return ""
	}

	// Everything here arrives from the endpoint, so it is bounded and
	// escaped like any other remote string.
	line := sanitize(platform.Model, 64)
	if platform.LogicalCPUs.OK {
		line += fmt.Sprintf("   %d threads", int(platform.LogicalCPUs.Value))
	}
	if platform.Kernel != "" {
		line += "   kernel " + sanitize(platform.Kernel, 32)
	}

	return labelStyle.Render(line)
}

// header renders the title line and the freshness indicator.
func (m Model) header(width int) string {
	title := "metrics-manager"
	if host := m.dash.Host; host != "" {
		// The host label comes from the endpoint, so it is treated as
		// untrusted text like any other remote string.
		title += " · " + sanitize(host, 40)
	}
	left := titleStyle.Render(title)

	right := m.status(width)
	if lipgloss.Width(left)+1+lipgloss.Width(right) > width {
		if lipgloss.Width(left) <= width {
			return left
		}

		return fitWidth(left, width)
	}

	// Push the status to the right margin, accounting for the fact that
	// styled strings carry escape sequences that do not occupy columns.
	gap := width - lipgloss.Width(left) - lipgloss.Width(right)
	if gap < 1 {
		gap = 1
	}

	return left + strings.Repeat(" ", gap) + right
}

// status describes how current the displayed numbers are.
func (m Model) status(width int) string {
	// Leave room for the title; a long error is truncated rather than
	// wrapped, which would break the single-line header.
	budget := width / 2

	if m.err != nil {
		text := "no contact: " + m.err.Error()
		if !m.updatedAt.IsZero() {
			text += " · last " + formatAge(m.now().Sub(m.updatedAt))
		}

		return errorStyle.Render(sanitize(text, budget))
	}

	if m.updatedAt.IsZero() {
		return labelStyle.Render("connecting…")
	}

	age := m.now().Sub(m.updatedAt)
	text := "updated " + formatAge(age)

	// Past a few refresh intervals the numbers are old enough that the
	// operator should be told, even though nothing has failed outright.
	if age > m.staleAfter() {
		return staleStyle.Render(text)
	}

	return labelStyle.Render(text)
}

func (m Model) cpuSection() string {
	var b strings.Builder

	b.WriteString(headingStyle.Render("CPU"))
	b.WriteString("\n")

	cpu := m.dash.CPU
	total := totalCPUUsage(cpu)
	b.WriteString(field("usage", fmt.Sprintf("total %s   user %s   system %s   idle %s",
		m.thresholdPercent("cpu.totalPercent", total),
		formatPercent(cpu.UsageUser),
		formatPercent(cpu.UsageSystem),
		formatPercent(cpu.UsageIdle))))
	b.WriteString(field("frequency", formatFrequencyKHz(cpu.FrequencyKHz)))
	b.WriteString(field("package temp", m.thresholdTemperature("cpu.temperatureC", cpu.PackageTempC)))
	b.WriteString(field("package power", powerAgainstLimit(cpu.PackagePowerW, cpu.TDPW)))
	b.WriteString(field("freq limits", frequencyLimits(cpu)))

	if len(cpu.CStates) > 0 {
		b.WriteString(field("idle states", cStateSummary(cpu.CStates)))
	}

	if len(cpu.Classes) > 0 {
		b.WriteString("\n")
		b.WriteString(m.coreClassTable(cpu.Classes, m.panelWidth()))
	}

	return b.String()
}

// powerAgainstLimit shows draw next to the thermal design power, because a
// wattage means little without the budget it is being spent from.
func powerAgainstLimit(power, tdp Reading) string {
	if !tdp.OK {
		return formatWatts(power)
	}

	return fmt.Sprintf("%s of %s TDP", formatWatts(power), formatWatts(tdp))
}

// frequencyLimits reports the base clock and the single-core turbo ceilings.
//
// On a hybrid part the two ceilings belong to the two core kinds, so they are
// labelled with the class names used in the table below rather than with
// powerstat's "primary" and "secondary".
func frequencyLimits(cpu CPU) string {
	parts := []string{"base " + formatFrequencyMHz(cpu.BaseFreqMHz)}

	if cpu.TurboPrimaryMHz.OK {
		parts = append(parts, "turbo P "+formatFrequencyMHz(cpu.TurboPrimaryMHz))
	}
	if cpu.TurboSecondaryMHz.OK {
		parts = append(parts, "turbo E "+formatFrequencyMHz(cpu.TurboSecondaryMHz))
	}
	if cpu.UncoreMHz.OK {
		parts = append(parts, "uncore "+formatFrequencyMHz(cpu.UncoreMHz))
	}

	return strings.Join(parts, "   ")
}

// cStateSummary renders idle-state residency on one line.
func cStateSummary(states []CState) string {
	parts := make([]string, 0, len(states))
	for _, state := range states {
		parts = append(parts, strings.ToUpper(state.Name)+" "+formatPercent(state.Residency))
	}

	return strings.Join(parts, "   ")
}

func (m Model) coreClassTable(classes []CoreClass, width int) string {
	columns := []column{
		{"class", 6, true}, {"cores", 5, false}, {"frequency", 10, false},
		{"total", 7, false}, {"user", 7, false}, {"system", 7, false},
		{"idle", 7, false}, {"source", 10, true},
	}
	var rows [][]string
	for _, class := range classes {
		rows = append(rows, []string{
			sanitize(class.Name, 8),
			formatCount(class.Cores),
			formatFrequencyKHz(class.FrequencyKHz),
			m.thresholdPercent("cpu.classPercent", totalCPUUsage(CPU{UsageIdle: class.UsageIdle})),
			formatPercent(class.UsageUser),
			formatPercent(class.UsageSystem),
			formatPercent(class.UsageIdle),
			sanitize(class.Source, 16),
		})
	}
	return responsiveTable(columns, rows, width)
}

func (m Model) memorySection() string {
	var b strings.Builder

	b.WriteString(headingStyle.Render("Memory"))
	b.WriteString("\n")

	mem := m.dash.Memory
	used := m.thresholdPercent("memory.usedPercent", mem.UsedPercent)
	if mem.UsedBytes.OK && mem.TotalBytes.OK {
		used += fmt.Sprintf("   (%s of %s)", formatBytes(mem.UsedBytes), formatBytes(mem.TotalBytes))
	}

	b.WriteString(field("used", used))
	b.WriteString(field("available", formatPercent(mem.AvailablePercent)))

	valid := func(r Reading) bool {
		return r.OK && !math.IsNaN(r.Value) && !math.IsInf(r.Value, 0)
	}
	if valid(mem.ReadGBps) || valid(mem.WriteGBps) || valid(mem.TotalGBps) {
		value := func(r Reading) string {
			if !valid(r) {
				return "-"
			}
			return formatBandwidthGBps(r)
		}
		b.WriteString(responsiveTable([]column{
			{title: "metric", width: 18, left: true},
			{title: "read", width: 14},
			{title: "write", width: 14},
			{title: "total", width: 14},
		}, [][]string{{
			"DRAM bandwidth", value(mem.ReadGBps), value(mem.WriteGBps), value(mem.TotalGBps),
		}}, m.panelWidth()))
	}

	return b.String()
}

// fieldLabelWidth aligns the value column across every section.
const fieldLabelWidth = 14

func (m Model) gpuSection(g GPU) string {
	var b strings.Builder

	heading := "GPU"
	if g.ID != "" {
		// The id is a label from the endpoint, so it is sanitised like
		// any other remote string.
		heading += " " + sanitize(g.ID, 8)
	}
	// Naming the driver is what makes an unavailable counter explicable
	// rather than looking like a fault.
	if g.Driver != "" {
		heading += " · " + sanitize(g.Driver, 12)
	}
	b.WriteString(headingStyle.Render(heading))
	b.WriteString("\n")

	b.WriteString(field("power", fmt.Sprintf("graphics %s   package %s",
		formatWatts(g.PowerW), formatWatts(g.PackagePowerW))))
	b.WriteString(field("temperature", m.thresholdTemperature("gpu.temperatureC", g.TempC)))
	b.WriteString(field("shared mem", memoryPair(g.SharedUsedBytes, g.SharedTotalBytes)))

	// An integrated GPU reports a zero VRAM total rather than omitting the
	// field, and a "0 B of 0 B" row says nothing worth a line.
	if g.VRAMTotalBytes.OK && g.VRAMTotalBytes.Value > 0 {
		b.WriteString(field("vram", m.thresholdValue("gpu.vramPercent",
			usedPercent(g.VRAMUsedBytes, g.VRAMTotalBytes), func(Reading) string {
				return memoryPair(g.VRAMUsedBytes, g.VRAMTotalBytes)
			})))
	}

	if len(g.Engines) > 0 {
		b.WriteString("\n")
		b.WriteString(m.engineTable(g.Engines))
	}
	if len(g.Tiles) > 0 {
		b.WriteString("\n")
		b.WriteString(tileTable(g.Tiles, m.panelWidth()))
	}
	if len(g.Processes) > 0 {
		b.WriteString("\n" + headingStyle.Render("Processes") + "\n")
		b.WriteString(labelStyle.Render(m.processSortLabel()) + "\n")
		b.WriteString(m.gpuProcessTable(m.sortedGPUProcesses(g.Processes), m.panelWidth()))
	}
	return b.String()
}

// gpuProcessColumns fixes the layout of the per-process table.
var gpuProcessColumns = []column{
	{title: "pid", width: 8, left: true},
	{title: "process", width: 18, left: true},
	{title: "usage", width: 9},
	{title: "memory", width: 12},
}

func (m Model) gpuProcessTable(processes []GPUProcess, width int) string {
	return m.scrollingProcessTable(gpuProcessColumns, m.gpuProcessRows(processes), width)
}

func (m Model) gpuProcessRows(processes []GPUProcess) [][]string {
	rows := make([][]string, 0, len(processes))
	for _, p := range processes {
		rows = append(rows, []string{
			// Both come from the kernel by way of qmassa, so they are
			// bounded and escaped like every other external string.
			sanitize(p.PID, 8),
			sanitize(p.Command, 18),
			m.thresholdPercent("gpu.processPercent", p.UsagePct),
			formatBytes(p.MemoryBytes),
		})
	}

	return rows
}

// npuFrequency shows the current clock against the driver's ceiling, because
// an idle NPU reports zero and that reads very differently next to the number
// it could reach.
func npuFrequency(npu NPU) string {
	current := formatFrequencyHz(npu.FrequencyHz)
	if !npu.MaxFrequencyMHz.OK {
		return current
	}

	return current + " of " + formatFrequencyMHz(npu.MaxFrequencyMHz)
}

// processColumns fixes the layout of the process table.
var processColumns = []column{
	{title: "pid", width: 8, left: true},
	{title: "process", width: 20, left: true},
	{title: "threads", width: 8},
	{title: "user", width: 16, left: true},
	{title: "memory", width: 12},
	{title: "cpu", width: 9},
}

func (m Model) processSection() string {
	var b strings.Builder

	b.WriteString(headingStyle.Render("Processes"))
	b.WriteString("\n")

	b.WriteString(labelStyle.Render(m.processSortLabel()) + "\n")
	b.WriteString(labelStyle.Render(m.processCPULabel()) + "\n")
	processes := m.sortedProcesses()
	if len(processes) == 0 && m.processSourceMissing() {
		b.WriteString("No current process samples.\n")
	}
	b.WriteString(m.scrollingProcessTable(processColumns, m.processRows(processes), m.processViewportWidth()))
	return b.String()
}

func (m Model) processRows(processes []Process) [][]string {
	rows := make([][]string, 0, len(processes))
	for _, p := range processes {
		rows = append(rows, []string{
			// A process names itself, so both of these are attacker
			// controlled and are bounded and escaped like every other
			// external string that reaches the terminal.
			sanitize(p.PID, 8),
			sanitize(p.Command, 20),
			formatProcessThreads(p.Threads),
			formatProcessUser(p.User),
			formatBytes(p.MemoryBytes),
			m.processCPUPercent(p.CPUPercent),
		})
	}

	return rows
}

// memoryPair renders "used of total", still saying what it can when only one
// of the two is reported.
func memoryPair(used, total Reading) string {
	if total.OK {
		return fmt.Sprintf("%s of %s", formatBytes(used), formatBytes(total))
	}

	return formatBytes(used)
}

var engineColumns = []column{
	// Wide enough for the longest name either driver uses,
	// "video-enhance", so the table never truncates an engine.
	{"engine", 16, true},
	{"usage", 9, false},
}

func (m Model) engineTable(engines []GPUEngine) string {
	rows := make([][]string, 0, len(engines))
	for _, e := range engines {
		rows = append(rows, []string{
			sanitize(e.Name, engineColumns[0].width),
			m.thresholdPercent("gpu.utilizationPercent", e.Usage),
		})
	}

	return responsiveTable(engineColumns, rows, m.panelWidth())
}

var tileColumns = []column{
	{"tile", 6, true},
	{"actual", 9, false},
	{"requested", 11, false},
	{"min", 10, false},
	{"max", 10, false},
	{"throttle", 12, true},
}

func tileTable(tiles []GPUTile, width int) string {
	rows := make([][]string, 0, len(tiles))
	for _, t := range tiles {
		rows = append(rows, []string{
			sanitize(t.Name, tileColumns[0].width),
			formatFrequencyMHz(t.ActualMHz),
			formatFrequencyMHz(t.RequestedMHz),
			formatFrequencyMHz(t.MinMHz),
			formatFrequencyMHz(t.MaxMHz),
			throttleText(t),
		})
	}

	return responsiveTable(tileColumns, rows, width)
}

// throttleText summarises a tile's throttle state.
//
// "no throttle series at all" and "nothing is throttling" are deliberately not
// collapsed: reporting the first as the second would be reassurance the data
// does not support.
func throttleText(t GPUTile) string {
	switch {
	case !t.ThrottleReported:
		return absent
	case len(t.ThrottleReasons) > 0:
		return strings.Join(t.ThrottleReasons, ",")
	case t.Throttled.OK && t.Throttled.Value != 0:
		// The summary flag is set while every named reason is clear, so
		// the cause is unknown rather than absent.
		return "yes"
	default:
		return "none"
	}
}

func (m Model) npuSection() string {
	var b strings.Builder

	b.WriteString(headingStyle.Render("NPU"))
	b.WriteString("\n")

	npu := m.dash.NPU
	b.WriteString(field("utilization", m.thresholdPercent("npu.utilizationPercent", npu.Utilization)))
	b.WriteString(field("frequency", npuFrequency(npu)))
	b.WriteString(field("power", formatWatts(npu.PowerW)))
	b.WriteString(field("temperature", m.thresholdTemperature("npu.temperatureC", npu.TempC)))
	b.WriteString(field("bandwidth", formatBandwidth(npu.BandwidthMBps)))
	b.WriteString(field("memory", formatMebibytes(npu.MemoryMiB)))
	b.WriteString(field("tile config", formatCount(npu.TileConfig)))
	if npu.PowerState.OK {
		b.WriteString(field("power state", npuPowerState(npu.PowerState)))
	}

	return b.String()
}

func npuPowerState(state Reading) string {
	switch state.Value {
	case 0:
		return "D0"
	case 1:
		return "D1"
	case 2:
		return "D2"
	case 3:
		return "D3hot"
	case 4:
		return "D3cold"
	default:
		return "unknown"
	}
}

// column describes one table column. Padding is applied to the plain text
// before any styling, because escape sequences would otherwise be counted as
// columns.
type column struct {
	title string
	width int

	// left aligns the cell to the left, which suits names and words;
	// measurements read better right-aligned under each other.
	left bool
}

func table(columns []column, rows [][]string) string {
	var b strings.Builder

	b.WriteString(labelStyle.Render(tableRow(columns, titles(columns))))
	b.WriteString("\n")

	for _, cells := range rows {
		b.WriteString(tableRow(columns, cells))
		b.WriteString("\n")
	}

	return b.String()
}

func responsiveTable(columns []column, rows [][]string, width int) string {
	expanded := table(columns, rows)
	if lipgloss.Width(expanded) <= width {
		return expanded
	}
	return compactTable(columns, rows)
}

func compactTable(columns []column, rows [][]string) string {
	var b strings.Builder
	for _, cells := range rows {
		for i, value := range cells {
			b.WriteString("  " + labelStyle.Render(columns[i].title+": ") + value + "\n")
		}
		b.WriteString("\n")
	}
	return b.String()
}

func titles(columns []column) []string {
	out := make([]string, 0, len(columns))
	for _, c := range columns {
		out = append(out, c.title)
	}

	return out
}

func tableRow(columns []column, cells []string) string {
	var b strings.Builder

	b.WriteString("  ")
	for i, c := range columns {
		if i >= len(cells) {
			break
		}
		padding := strings.Repeat(" ", max(0, c.width-lipgloss.Width(cells[i])))
		if c.left {
			// A right-aligned cell can fill its width exactly, so a
			// left-aligned column following one needs a separator of
			// its own or the two run together.
			if i > 0 {
				b.WriteString("  ")
			}
			b.WriteString(cells[i] + padding)
			continue
		}
		b.WriteString(padding + cells[i])
	}

	return strings.TrimRight(b.String(), " ")
}

// field renders one labelled value line.
func field(label, value string) string {
	padded := fmt.Sprintf("  %-*s", fieldLabelWidth, label)

	return labelStyle.Render(padded) + value + "\n"
}

func (m Model) thresholdPercent(metric string, value Reading) string {
	return m.thresholdValue(metric, value, formatPercent)
}

func (m Model) thresholdTemperature(metric string, value Reading) string {
	return m.thresholdValue(metric, value, formatTemperature)
}

func (m Model) thresholdValue(metric string, value Reading, format func(Reading) string) string {
	text := format(value)
	metric = thresholdMetric(metric)
	threshold, enabled := m.config.Thresholds[metric]
	if !enabled || !value.OK || math.IsNaN(value.Value) || math.IsInf(value.Value, 0) {
		return text
	}

	return severityStyle(classify(value.Value, threshold)).Render(text)
}

func severityStyle(severity Severity) lipgloss.Style {
	switch severity {
	case SeverityCareful:
		return carefulStyle
	case SeverityWarning:
		return warningStyle
	case SeverityCritical:
		return criticalStyle
	default:
		return okStyle
	}
}
