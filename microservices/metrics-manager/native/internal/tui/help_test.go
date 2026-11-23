// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package tui

import (
	"reflect"
	"strings"
	"testing"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/metrics-manager/native/internal/source"
)

func TestHelpRestoresEveryTabAndIndependentScroll(t *testing.T) {
	for _, tab := range []Tab{OverviewTab, TrendsTab, DetailsTab} {
		m := acceleratorModel(t, 24)
		m.history.Update(m.dash, fixedNow)
		m.switchTab(tab)
		if tab == DetailsTab {
			m.selectDetail(len(m.detailItems()) - 1)
		}
		m.setOffset(m.maxOffset())
		offset, choice, top := m.offset, m.detailSelection, m.detailTop
		m, _ = update(t, m, key("h"))
		if !m.showHelp {
			t.Fatalf("tab %d: h did not open help", tab)
		}
		wantContains(t, m.View(), "Help - mm-tui")
		m, _ = update(t, m, tea.KeyMsg{Type: tea.KeyEnd})
		helpOffset := m.offset
		if helpOffset == 0 {
			t.Fatal("help did not scroll")
		}
		m, cmd := update(t, m, key("esc"))
		if isQuit(cmd) || m.showHelp || m.offset != offset ||
			m.detailSelection != choice || m.detailTop != top || m.activeTab != tab {
			t.Fatalf("tab %d was not restored after help", tab)
		}
		m, _ = update(t, m, key("h"))
		if m.offset != helpOffset {
			t.Fatal("help lost its independent scroll position")
		}
		m, _ = update(t, m, key("h"))
		if m.showHelp || m.offset != offset {
			t.Fatal("h did not return to the previous view")
		}
	}
}

func TestHelpReturnsToAlertsAndAllowsDirectNavigation(t *testing.T) {
	m := acceleratorModel(t, 24)
	populateAlerts(&m, 30)
	m, _ = update(t, m, key("a"))
	m, _ = update(t, m, tea.KeyMsg{Type: tea.KeyEnd})
	offset := m.offset
	for _, closeKey := range []string{"esc", "h", "a"} {
		m, _ = update(t, m, key("h"))
		m, _ = update(t, m, tea.KeyMsg{Type: tea.KeyPgDown})
		var cmd tea.Cmd
		m, cmd = update(t, m, key(closeKey))
		if isQuit(cmd) || m.showHelp || m.activeTab != AlertsTab || m.offset != offset {
			t.Fatalf("%s did not return from help to alerts", closeKey)
		}
	}
	for _, tabKey := range []string{"1", "2", "3", "tab", "shift+tab"} {
		m, _ = update(t, m, key("h"))
		m, _ = update(t, m, key(tabKey))
		if m.showHelp {
			t.Fatalf("%s did not dismiss overlays", tabKey)
		}
	}
	m, _ = update(t, m, key("h"))
	m, _ = update(t, m, key("a"))
	if m.showHelp || m.activeTab != AlertsTab {
		t.Fatal("a from help did not open alerts")
	}
}

func TestHelpDisablesMouseAndReservesHInDetails(t *testing.T) {
	m := detailsModel(t, 140, 35)
	m.selectDetail(2)
	choice := m.detailSelection
	m, cmd := update(t, m, key("h"))
	if !m.showHelp || m.detailSelection != choice || m.detailsMouseEnabled() ||
		cmd == nil || reflect.TypeOf(cmd()) != reflect.TypeOf(tea.DisableMouse()) {
		t.Fatal("h did not open help and disable Details mouse capture")
	}
	m, _ = update(t, m, tea.MouseMsg{Button: tea.MouseButtonWheelDown, Action: tea.MouseActionPress})
	if m.detailSelection != choice {
		t.Fatal("mouse changed the metric while help was open")
	}
	m, cmd = update(t, m, key("esc"))
	if !m.detailsMouseEnabled() || cmd == nil ||
		reflect.TypeOf(cmd()) != reflect.TypeOf(tea.EnableMouseCellMotion()) {
		t.Fatal("closing help did not restore Details mouse capture")
	}
	m, _ = update(t, m, tea.KeyMsg{Type: tea.KeyLeft})
	if m.detailSelection == choice {
		t.Fatal("left arrow no longer selects the preceding metric")
	}
}

func TestHelpKeepsCollectionActiveAndQuitAvailable(t *testing.T) {
	m := detailsModel(t, 100, 24)
	m, _ = update(t, m, key("h"))
	m, _ = update(t, m, tea.KeyMsg{Type: tea.KeyEnd})
	offset := m.offset
	at := fixedNow.Add(time.Second)
	m, cmd := update(t, m, snapshotMsg(source.Snapshot{
		At: at, Samples: parseFixture(t, hostExposition+acceleratorExposition),
	}))
	if !m.showHelp || m.offset != offset || m.updatedAt != at || cmd == nil {
		t.Fatal("help interrupted snapshot processing or lost scroll position")
	}
	if points := m.history.series["cpu.total"].Points; points[len(points)-1].At != at {
		t.Fatal("history stopped recording while help was open")
	}
	m.now = func() time.Time { return fixedNow.Add(6 * time.Minute) }
	m, cmd = update(t, m, clockMsg{})
	if !m.showHelp || len(m.history.series) != 0 || cmd == nil {
		t.Fatal("help interrupted history expiration")
	}
	for _, quit := range []tea.KeyMsg{key("q"), {Type: tea.KeyCtrlC}} {
		_, cmd := update(t, m, quit)
		if !isQuit(cmd) {
			t.Fatal("quit shortcut was intercepted by help")
		}
	}
}

func TestHelpWrapsReferenceWithoutLosingTextAndFitsTerminal(t *testing.T) {
	compact := func(text string) string { return strings.Join(strings.Fields(text), "") }
	for _, width := range []int{20, 40, 80, 140} {
		m := testModel(nil)
		m.showHelp = true
		body := strings.Join(m.bodyLines(width), "\n")
		if compact(body) != compact(m.helpBody(1000)) {
			t.Fatalf("help text was truncated at width %d", width)
		}

		for _, height := range []int{1, 2, 5, 8, 24, 50} {
			m, _ = update(t, m, tea.WindowSizeMsg{Width: width, Height: height})
			m.setOffset(m.maxOffset())
			view := m.View()
			if len(strings.Split(view, "\n")) > height {
				t.Fatalf("%dx%d: help exceeded terminal height", width, height)
			}
			for _, line := range strings.Split(view, "\n") {
				if lipgloss.Width(line) > width {
					t.Fatalf("%dx%d: help exceeded terminal width", width, height)
				}
			}
		}
	}
	m := testModel(nil)
	if !strings.Contains(compact(m.helpBody(140)), compact(CommandLineHelp())) {
		t.Fatal("in-TUI help omitted part of the shared startup reference")
	}
}

func TestHelpExplainsProcessCPUAndThreads(t *testing.T) {
	m := testModel(nil)
	body := m.helpBody(1000)
	for _, explanation := range []string{
		"16 Threads on 14 logical CPUs is normal",
		"A thread runs on one logical CPU at a time",
		"not necessarily physical cores (SMT)",
		"total = per-core / monitored logical CPU count",
		"1400% is 100% total",
		"1500% per-core means about 15 logical CPUs busy on average",
		"On a fixed 14-CPU host, sustained 1500% is unexpected",
		"Colors and alerts always use total host CPU thresholds",
	} {
		wantContains(t, body, explanation)
	}
}
