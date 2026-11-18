// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// Package tui renders the metrics-manager telemetry as a terminal dashboard.
//
// It consumes the same Prometheus exposition that the service's own
// /metrics/stream polls, so the two views cannot report different numbers for
// the same host.
package tui

import (
	"context"
	"errors"
	"time"

	tea "github.com/charmbracelet/bubbletea"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/metrics-manager/native/internal/source"
)

// snapshotMsg delivers one poll result into the update loop.
type snapshotMsg source.Snapshot

type clockMsg struct{}

func clockTick() tea.Cmd {
	return tea.Tick(time.Second, func(time.Time) tea.Msg { return clockMsg{} })
}

type Tab int

const (
	OverviewTab Tab = iota
	TrendsTab
	DetailsTab
	AlertsTab
	tabCount
)

// Model is the dashboard state.
type Model struct {
	snapshots <-chan source.Snapshot

	// dash is the most recent successfully parsed snapshot. It is kept
	// across failures so a brief loss of contact leaves the last known
	// numbers on screen, marked stale, rather than blanking the display.
	dash Dashboard

	// updatedAt is when dash was collected, zero until the first success.
	updatedAt       time.Time
	processDataSeen bool
	storageDataSeen bool

	// err is the reason the most recent poll failed, or nil.
	err error

	config              DashboardConfig
	chartsConfig        ChartsConfig
	alerts              AlertTracker
	history             History
	network             networkTracker
	storage             storageTracker
	activeTab           Tab
	tabOffsets          [tabCount]int
	detailSelection     detailChoice
	detailTop           int
	alertReturnTab      Tab
	pollInterval        time.Duration
	showHelp            bool
	helpOffset          int
	processColumnOffset int
	panelContentWidth   int

	width  int
	height int

	// offset is the first body line shown, non-zero only when the content
	// is taller than the window.
	offset int

	// now is injected so the staleness readout can be tested without
	// depending on the wall clock.
	now func() time.Time
}

// NewModel returns a Model that renders snapshots as they arrive on ch.
func NewModel(ch <-chan source.Snapshot) Model {
	return NewModelWithConfig(ch, DefaultDashboardConfig())
}

func NewModelWithConfig(ch <-chan source.Snapshot, config DashboardConfig) Model {
	return NewModelWithConfigs(ch, config, DefaultChartsConfig())
}

func NewModelWithConfigs(
	ch <-chan source.Snapshot,
	config DashboardConfig,
	chartsConfig ChartsConfig,
) Model {
	return Model{
		snapshots:       ch,
		config:          config,
		chartsConfig:    chartsConfig,
		alerts:          NewAlertTracker(config.Alerts, config.Processes),
		history:         NewHistory(chartsConfig),
		detailSelection: detailChoice{metric: chartsConfig.Details.DefaultMetric},
		now:             time.Now,
		pollInterval:    source.DefaultInterval,
	}
}

// Init polls data and advances the time axis independently of network replies.
func (m Model) Init() tea.Cmd {
	commands := []tea.Cmd{waitForSnapshot(m.snapshots), clockTick()}
	if m.mouseEnabled() {
		commands = append(commands, tea.EnableMouseCellMotion)
	}
	return tea.Batch(commands...)
}

// Update folds one message into the model.
func (m Model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	mouseEnabled := m.mouseEnabled()
	switch msg := msg.(type) {
	case clockMsg:
		m.expireStorage(m.now())
		m.history.Prune(m.now())
		m.setOffset(m.offset)
		return m, clockTick()

	case tea.KeyMsg:
		if m.activeTab == DetailsTab && !m.showHelp && m.detailKey(msg.String()) {
			return m, nil
		}
		switch msg.String() {
		case "q", "ctrl+c":
			return m, tea.Quit
		case "esc":
			if m.showHelp {
				m.toggleHelp()
			} else if m.activeTab == AlertsTab {
				m.toggleAlerts()
			} else {
				return m, tea.Quit
			}
		case "a":
			m.toggleAlerts()
		case "h":
			m.toggleHelp()
		case "tab":
			m.switchTab((m.activeTab + 1) % tabCount)
		case "shift+tab":
			m.switchTab((m.activeTab + tabCount - 1) % tabCount)
		case "1":
			m.switchTab(OverviewTab)
		case "2":
			m.switchTab(TrendsTab)
		case "3":
			m.switchTab(DetailsTab)
		case "4":
			m.switchTab(AlertsTab)
		case "s":
			if m.activeTab == OverviewTab && !m.showHelp {
				m.cycleProcessSort()
			}
		case "r":
			if m.activeTab == OverviewTab && !m.showHelp {
				m.config.Processes.Descending = !m.config.Processes.Descending
			}
		case "c":
			if m.activeTab == OverviewTab && !m.showHelp {
				m.toggleProcessCPUMode()
			}
		case "left", "right":
			if m.activeTab == OverviewTab && !m.showHelp {
				delta := 8
				if msg.String() == "left" {
					delta = -delta
				}
				m.moveProcessColumns(delta)
			}
		case "up", "k":
			m.setOffset(m.offset - 1)
		case "down", "j":
			m.setOffset(m.offset + 1)
		case "pgup":
			m.setOffset(m.offset - m.visibleRows())
		case "pgdown", " ":
			m.setOffset(m.offset + m.visibleRows())
		case "home", "g":
			m.setOffset(0)
		case "end", "G":
			m.setOffset(m.maxOffset())
		}

	case tea.MouseMsg:
		m.handleMouse(msg)

	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height
		m.moveProcessColumns(0)
		// A window that just grew can leave the view scrolled past the
		// end, which would show a screen of blank lines.
		m.setOffset(m.offset)

	case snapshotMsg:
		m.err = msg.Err
		if msg.Err == nil {
			m.dash = BuildDashboard(msg.Samples)
			m.processDataSeen = m.processDataSeen || len(m.dash.Processes) > 0
			m.dash.Network, m.dash.NetworkLimited = m.network.update(msg.Samples, msg.At, m.config.Network)
			m.dash.Storage, m.dash.StorageLimited = m.storage.update(msg.Samples, msg.At, m.config.Storage)
			m.storageDataSeen = m.storageDataSeen || len(m.dash.Storage) > 0
			m.updatedAt = msg.At
			m.alerts.Update(m.dash, m.config.Thresholds, msg.At)
			m.history.Update(m.dash, msg.At)
			m.moveProcessColumns(0)
		} else {
			m.network = networkTracker{}
			m.storage = storageTracker{}
			m.expireStorage(msg.At)
			m.alerts.Interrupt()
			m.history.Update(Dashboard{}, msg.At)
		}
		m.setOffset(m.offset)
		// Re-arm immediately: the poller paces itself, so the update
		// loop should never be the thing that throttles refreshes.
		return m, waitForSnapshot(m.snapshots)

	case streamClosedMsg:
		// The poller stopped, which only happens when its context was
		// cancelled, so there is nothing further to display.
		return m, tea.Quit
	}

	if m.mouseEnabled() != mouseEnabled {
		if m.mouseEnabled() {
			return m, tea.EnableMouseCellMotion
		}
		return m, tea.DisableMouse
	}
	return m, nil
}

func (m *Model) switchTab(tab Tab) {
	if m.showHelp {
		m.toggleHelp()
	}
	if tab == m.activeTab {
		return
	}
	m.tabOffsets[m.activeTab] = m.offset
	if tab == AlertsTab {
		m.alertReturnTab = m.activeTab
	}
	m.activeTab = tab
	m.offset = m.scrollTo(m.tabOffsets[tab])
}

func (m *Model) setOffset(offset int) {
	m.offset = m.scrollTo(offset)
	if m.showHelp {
		m.helpOffset = m.offset
	} else {
		m.tabOffsets[m.activeTab] = m.offset
	}
}

func (m *Model) toggleAlerts() {
	if m.showHelp {
		m.toggleHelp()
		if m.activeTab == AlertsTab {
			return
		}
	}
	if m.activeTab == AlertsTab {
		m.switchTab(m.alertReturnTab)
	} else {
		m.switchTab(AlertsTab)
	}
}

// streamClosedMsg reports that the snapshot channel was closed.
type streamClosedMsg struct{}

// scrollTo clamps a requested scroll position to the content.
func (m Model) scrollTo(offset int) int {
	if offset < 0 {
		return 0
	}
	if max := m.maxOffset(); offset > max {
		return max
	}

	return offset
}

// maxOffset is the furthest the body can scroll, which is zero whenever it
// already fits on screen.
func (m Model) maxOffset() int {
	if m.activeTab == DetailsTab && !m.showHelp {
		return 0
	}
	rows := m.visibleRows()
	if rows <= 0 {
		return 0
	}

	if overflow := len(m.bodyLines(m.renderWidth())) - rows; overflow > 0 {
		return overflow
	}

	return 0
}

// waitForSnapshot blocks in a command goroutine until the next snapshot.
func waitForSnapshot(ch <-chan source.Snapshot) tea.Cmd {
	return func() tea.Msg {
		s, ok := <-ch
		if !ok {
			return streamClosedMsg{}
		}

		return snapshotMsg(s)
	}
}

// Run drives a Bubble Tea program that renders the endpoint until the operator
// quits or ctx is cancelled.
func Run(ctx context.Context, poller *source.Poller) error {
	return RunWithConfig(ctx, poller, DefaultDashboardConfig())
}

func RunWithConfig(ctx context.Context, poller *source.Poller, config DashboardConfig) error {
	return RunWithConfigs(ctx, poller, config, DefaultChartsConfig())
}

func RunWithConfigs(
	ctx context.Context,
	poller *source.Poller,
	config DashboardConfig,
	chartsConfig ChartsConfig,
) error {
	// The caller's context is kept so shutdownErr can tell an operator's
	// signal apart from the cancel below, which always fires.
	parent := ctx

	ctx, cancel := context.WithCancel(ctx)
	defer cancel()

	// A single slot is enough: the display only ever wants the newest
	// snapshot, and buffering more would only let it fall behind.
	ch := make(chan source.Snapshot, 1)

	polled := make(chan struct{})
	go func() {
		defer close(polled)
		defer close(ch)
		poller.Run(ctx, func(s source.Snapshot) { send(ch, s) })
	}()

	model := NewModelWithConfigs(ch, config, chartsConfig)
	if poller.Interval > 0 {
		model.pollInterval = poller.Interval
	}
	program := tea.NewProgram(
		model,
		tea.WithAltScreen(),
		// The CLI owns signals; competing handlers can deadlock during cancellation.
		tea.WithoutSignalHandler(),
	)
	finished := make(chan struct{})
	watched := make(chan struct{})
	go func() {
		defer close(watched)
		select {
		case <-ctx.Done():
			// Quit joins the input reader before restoring the terminal, unlike Kill.
			program.Quit()
		case <-finished:
		}
	}()
	_, err := program.Run()
	close(finished)

	// Stop the poller and wait for it, so the process does not exit while
	// a request is still in flight.
	cancel()
	<-watched
	<-polled

	return shutdownErr(err, parent)
}

// shutdownErr suppresses the error Bubble Tea reports when it was stopped by a
// cancelled context.
//
// A signal normally requests a graceful quit. If the program was also killed,
// the caller's cancelled context still distinguishes that stop from a failure.
func shutdownErr(err error, parent context.Context) error {
	if errors.Is(err, tea.ErrProgramKilled) && parent.Err() != nil {
		return nil
	}

	return err
}

// RenderOnce renders a single frame for one snapshot and returns it.
//
// It exists so the dashboard can be inspected without a terminal: a parity
// check against the REST output, or a quick look on a host where running an
// interactive program is inconvenient.
func RenderOnce(s source.Snapshot, width int) string {
	return RenderOnceWithConfig(s, width, DefaultDashboardConfig())
}

func RenderOnceWithConfig(s source.Snapshot, width int, config DashboardConfig) string {
	return RenderOnceWithConfigs(s, width, config, DefaultChartsConfig())
}

func RenderOnceWithConfigs(
	s source.Snapshot,
	width int,
	config DashboardConfig,
	chartsConfig ChartsConfig,
) string {
	m := NewModelWithConfigs(nil, config, chartsConfig)
	m.width = width

	next, _ := m.Update(snapshotMsg(s))

	return next.View()
}

// send delivers s to ch, discarding a snapshot that is still queued.
//
// Dropping is correct here: an unread snapshot is already out of date, and
// blocking instead would stall the poller behind a slow terminal.
func send(ch chan source.Snapshot, s source.Snapshot) {
	for {
		select {
		case ch <- s:
			return
		default:
			select {
			case <-ch:
			default:
			}
		}
	}
}
