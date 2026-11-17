// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package tui

import (
	"fmt"
	"strings"
	"time"

	"github.com/charmbracelet/lipgloss"
)

func (m Model) alertSummary(width int) string {
	var counts [4]int
	for _, alert := range m.alerts.Visible() {
		counts[alert.Severity]++
	}
	var summary string
	if width < 70 {
		summary = fmt.Sprintf("Alerts C:%d W:%d", counts[SeverityCritical], counts[SeverityWarning])
		if m.config.Alerts.ShowCareful {
			summary += fmt.Sprintf(" I:%d", counts[SeverityCareful])
		}
	} else {
		summary = fmt.Sprintf("Alerts: %d critical | %d warning",
			counts[SeverityCritical], counts[SeverityWarning])
		if m.config.Alerts.ShowCareful {
			summary += fmt.Sprintf(" | %d careful", counts[SeverityCareful])
		}
	}
	hint := "[4/a] Open alerts"
	if width < 90 {
		hint = "[4/a] Alerts"
	}
	switch {
	case m.err != nil:
		return labelStyle.Render("Alerts: no contact | " + hint)
	case m.updatedAt.IsZero():
		return labelStyle.Render("Alerts: waiting for data | " + hint)
	case m.now().Sub(m.updatedAt) > m.staleAfter():
		return labelStyle.Render("Alerts: stale data | " + hint)
	}
	if m.processCoverageLimited() {
		if len(summary)+len(hint)+10 > width {
			summary = fmt.Sprintf("Alerts C:%d W:%d", counts[SeverityCritical], counts[SeverityWarning])
			if m.config.Alerts.ShowCareful {
				summary += fmt.Sprintf(" I:%d", counts[SeverityCareful])
			}
		}
		if len(summary)+len(hint)+10 > width {
			summary = "Alerts"
		}
		status := "CPU!"
		for _, candidate := range []string{"Process CPU alerts: limited", "CPU alerts limited", "CPU!"} {
			if len(summary)+len(candidate)+len(hint)+6 <= width {
				status = candidate
				break
			}
		}
		summary += " | " + status
	}
	if len(m.storageIssues()) > 0 {
		if len(summary)+len(hint)+14 > width {
			summary = fmt.Sprintf("Alerts C:%d W:%d", counts[SeverityCritical], counts[SeverityWarning])
			if m.processCoverageLimited() {
				summary += " | CPU!"
			}
		}
		summary += " | Storage!"
	}
	summary += " | " + hint
	switch {
	case counts[SeverityCritical] > 0:
		return criticalStyle.Render(summary)
	case counts[SeverityWarning] > 0:
		return warningStyle.Render(summary)
	}
	return labelStyle.Render(summary)
}

func (m Model) alertDetails(width int) string {
	var b strings.Builder
	b.WriteString(headingStyle.Render("Alerts") + "\n")
	b.WriteString("High utilization may be expected during inference; thresholds are diagnostic, not safety limits.\n\n")
	b.WriteString("History shows ended episodes, not current load. Process CPU alerts always use total host CPU capacity as 100%, regardless of the Overview CPU display mode.\n\n")
	if issues := m.storageIssues(); len(issues) > 0 {
		b.WriteString(headingStyle.Render("Storage alert coverage limited") + "\n")
		for _, issue := range issues {
			b.WriteString("  " + issue + "\n")
		}
		b.WriteString("Missing storage data cannot confirm recovery. Check timestamps, collection and storage.maxSampleAge.\n\n")
	}
	if m.err != nil || (!m.updatedAt.IsZero() && m.now().Sub(m.updatedAt) > m.staleAfter()) {
		b.WriteString("Data is stale: these are last known events, not confirmed current conditions.\n\n")
	}

	alerts := m.alerts.Visible()
	b.WriteString(headingStyle.Render(fmt.Sprintf("Active (%d)", len(alerts))) + "\n")
	if len(alerts) == 0 {
		b.WriteString("No active events recorded.\n")
	}
	for _, alert := range alerts {
		b.WriteString(renderAlert(alert, m.updatedAt, "active"))
	}
	if issues := m.processAlertIssues(); len(issues) > 0 {
		b.WriteString("\n" + headingStyle.Render(fmt.Sprintf("Process CPU alert coverage (%d/%d limited)",
			len(issues), len(processAlertCandidates(m.dash, m.alerts.processLimit, m.now(), m.alerts.processMaxAge)))) + "\n")
		b.WriteString("These samples cannot confirm CPU alerts; this does not block process collection or display.\n")
		for _, issue := range issues {
			b.WriteString(fmt.Sprintf("  %s (PID %s): %s\n", sanitize(issue.process.Command, 60),
				sanitize(issue.process.PID, 20), issue.reason))
			if !issue.process.CPUAt.IsZero() {
				b.WriteString(fmt.Sprintf("    source time %s | checked %s\n",
					issue.process.CPUAt.Format(time.RFC3339Nano), m.now().Format(time.RFC3339Nano)))
			}
		}
		b.WriteString("Check platform_logical_cpus, process_cpu_percent timestamps, export_timestamp=true, collector cadence and clock synchronization.\n")
	}
	if m.processSourceMissing() {
		b.WriteString("\n" + headingStyle.Render("Process CPU data unavailable") + "\n")
		b.WriteString("No current process samples remain from a previously observed source. Check the process collector and its delivery to Telegraf.\n")
	}
	if retained := len(m.dash.Processes) - len(currentProcesses(m.dash, m.now(), m.alerts.processMaxAge)); retained > 0 {
		b.WriteString("\n" + headingStyle.Render(fmt.Sprintf("Retained process samples (%d excluded)", retained)) + "\n")
		b.WriteString(fmt.Sprintf("Samples older than %s are excluded before ranking and alert evaluation (processes.maxSampleAge). Top-list rotation or an exited process can leave cached samples; this alone does not mean collection failed.\n", m.alerts.processMaxAge))
		shown := 0
		for _, process := range m.dash.Processes {
			if expiredProcessCPU(process.CPUAt, m.now(), m.alerts.processMaxAge) && shown < m.alerts.processLimit {
				b.WriteString(fmt.Sprintf("  %s (PID %s): last sample %s\n",
					sanitize(process.Command, 60), sanitize(process.PID, 20), process.CPUAt.Format(time.RFC3339Nano)))
				shown++
			}
		}
		if shown < retained {
			b.WriteString(fmt.Sprintf("Showing %d of %d retained entries.\n", shown, retained))
		}
	}
	b.WriteString("\n" + headingStyle.Render(fmt.Sprintf("Recent history (%d/%d)",
		len(m.alerts.events), m.config.Alerts.MaxHistory)) + "\n")
	if len(m.alerts.events) == 0 {
		b.WriteString("No ended events recorded in this session.\n")
	}
	for _, event := range m.alerts.events {
		b.WriteString(renderAlert(event.Alert, event.EndedAt, event.Outcome))
	}
	return lipgloss.NewStyle().Width(width).Render(b.String())
}

type processAlertIssue struct {
	process Process
	reason  string
}

func (m Model) processSourceMissing() bool {
	return (m.processDataSeen || len(m.dash.Processes) > 0) && len(currentProcesses(m.dash, m.now(), m.alerts.processMaxAge)) == 0
}

func (m Model) processCoverageLimited() bool {
	if _, monitored := m.config.Thresholds["process.cpuPercent"]; !monitored {
		return false
	}
	return m.processSourceMissing() || len(m.processAlertIssues()) > 0
}

func (m Model) processAlertIssues() []processAlertIssue {
	if _, monitored := m.config.Thresholds["process.cpuPercent"]; !monitored {
		return nil
	}
	var issues []processAlertIssue
	now := m.now()
	for _, process := range processAlertCandidates(m.dash, m.alerts.processLimit, now, m.alerts.processMaxAge) {
		reason := processTimestampIssue(process.CPUAt, now, m.alerts.processMaxAge)
		if !finiteReading(process.CPUPercent) {
			reason = "CPU measurement missing or non-finite"
		} else if reason == "" && !usableCPUCount(m.dash.Platform.LogicalCPUs) {
			reason = "total CPU unavailable: logical CPU count missing or invalid"
		} else if reason == "" {
			if state := m.alerts.states["process."+process.PID]; state != nil {
				if process.CPUAt.Before(state.observedAt) {
					reason = "out-of-order measurement timestamp"
				} else if process.CPUAt.Equal(state.observedAt) && processTotalCPU(process.CPUPercent, m.dash.Platform.LogicalCPUs).Value != state.observedValue {
					reason = "conflicting CPU values at one timestamp"
				}
			}
		}
		if reason != "" {
			issues = append(issues, processAlertIssue{process: process, reason: reason})
		}
	}
	return issues
}

func (m Model) bottomBarRows() int {
	if !m.config.Alerts.BottomBar || (m.height > 0 && m.height < len(m.chromeLines(m.renderWidth()))+6) {
		return 0
	}
	return 3
}

func (m Model) bottomAlertLines(width int) []string {
	if m.bottomBarRows() == 0 {
		return nil
	}
	detail := "No active events recorded."
	alerts := m.alerts.Visible()
	if len(alerts) > 0 {
		alert := alerts[0]
		unit := thresholdUnit(alert.Metric)
		status := ""
		if alert.Unavailable || m.err != nil || m.now().Sub(m.updatedAt) > m.staleAfter() {
			status = " [last observed]"
		}
		detail = severityStyle(alert.Severity).Render(fmt.Sprintf("%s %s %s %.1f%s%s",
			alert.Severity, sanitize(alert.Device, 60), sanitize(alert.Metric, 60), alert.Value, unit, status))
	}
	return []string{
		borderStyle.Render(strings.Repeat("─", width)),
		fitWidth(m.alertSummary(width), width), fitWidth(detail, width),
	}
}

func renderAlert(alert Alert, end time.Time, outcome string) string {
	label := alert.Metric
	if alert.Device != "" {
		label = alert.Device + " / " + label
	}
	unit := thresholdUnit(alert.Metric)
	valueLabel := "last observed"
	if outcome == "active" {
		valueLabel = "current"
		if alert.Unavailable {
			outcome = "waiting for data"
			valueLabel = "last observed"
		}
	}
	duration := max(time.Duration(0), end.Sub(alert.Since)).Truncate(time.Second)
	evidence := ""
	if alert.TriggerValue.OK {
		evidence += fmt.Sprintf("  activated at %.1f%s | activation threshold %.1f%s\n",
			alert.TriggerValue.Value, unit, alert.TriggerThreshold, unit)
	}
	if alert.PeakValue.OK {
		evidence += fmt.Sprintf("  peak since activation %.1f%s at %s\n",
			alert.PeakValue.Value, unit, alert.PeakAt.Format("2006-01-02 15:04:05"))
	}
	if alert.RecoveryValue.OK {
		evidence += fmt.Sprintf("  confirmed recovery at %.1f%s\n", alert.RecoveryValue.Value, unit)
	}
	if outcome == "active" && alert.Value < alert.Threshold {
		evidence += "  Value is below the event threshold; recovery is not yet confirmed.\n"
	}
	return severityStyle(alert.Severity).Render(
		fmt.Sprintf("%s %s [%s]", alert.Severity, sanitize(label, 180), outcome)) + "\n" +
		fmt.Sprintf("  %s %.1f%s | threshold %.1f%s\n", valueLabel, alert.Value, unit, alert.Threshold, unit) +
		evidence +
		fmt.Sprintf("  since %s | through %s | duration %s\n",
			alert.Since.Format("2006-01-02 15:04:05"), end.Format("15:04:05"), duration) +
		"  " + sanitize(alert.Message, 200) + "\n\n"
}
