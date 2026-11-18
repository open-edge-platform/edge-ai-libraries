// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package tui

import (
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
	"github.com/charmbracelet/x/ansi"
)

func viewportEdges(t *testing.T, m Model) (string, string) {
	t.Helper()
	view := strings.Split(m.View(), "\n")
	if len(view) != m.height {
		t.Fatalf("viewport height = %d, want %d", len(view), m.height)
	}
	for _, line := range view {
		if lipgloss.Width(line) > m.width {
			t.Fatalf("viewport exceeds width %d: %q", m.width, line)
		}
	}
	chrome := len(m.chromeLines(m.width))
	body, offset := clip(m.bodyLines(m.width), m.visibleRows(), m.offset)
	for i, line := range body {
		if view[chrome+i] != line {
			t.Fatalf("indicator replaced content at offset %d, row %d", offset, i)
		}
	}
	return ansi.Strip(view[chrome-1]), ansi.Strip(view[len(view)-2-m.bottomBarRows()])
}

func TestScrollIndicatorsTrackEveryScrollableViewWithoutTakingBodyRows(t *testing.T) {
	for _, tc := range []struct {
		tab     Tab
		help    bool
		content string
	}{
		{OverviewTab, false, "metrics"},
		{TrendsTab, false, "charts"},
		{AlertsTab, false, "alert details"},
		{DetailsTab, true, "help"},
	} {
		for _, width := range []int{20, 40, 100, 210} {
			for _, bottomBar := range []bool{false, true} {
				m := acceleratorModel(t, 24)
				m.width, m.config.Alerts.BottomBar = width, bottomBar
				if tc.tab == AlertsTab {
					populateAlerts(&m, 5)
				}
				m.switchTab(tc.tab)
				m.showHelp = tc.help
				last := m.maxOffset()
				if last < 2 {
					t.Fatalf("fixture has no middle position: tab %d width %d", tc.tab, width)
				}
				rows := m.visibleRows()
				for _, offset := range []int{0, 1, last} {
					m.setOffset(offset)
					top, bottom := viewportEdges(t, m)
					if strings.Contains(top, "above") != (offset > 0) ||
						strings.Contains(bottom, "below") != (offset < last) {
						t.Fatalf("tab %d width %d offset %d/%d: top=%q bottom=%q",
							tc.tab, width, offset, last, top, bottom)
					}
					if offset < last && width >= 40 {
						wantContains(t, bottom, "more "+tc.content+" below")
					}
					if offset > 0 && width >= 40 {
						wantContains(t, top, "more "+tc.content+" above")
					}
					if width >= 100 {
						if offset < last {
							wantContains(t, bottom, "Down/PgDn")
						}
						if offset > 0 {
							wantContains(t, top, "Up/PgUp")
						}
					}
					if m.visibleRows() != rows {
						t.Fatal("scroll position changed the content budget")
					}
				}
			}
		}
	}
}

func TestScrollIndicatorsFollowNavigationResizeAndContentChanges(t *testing.T) {
	m := acceleratorModel(t, 24)
	m.switchTab(TrendsTab)
	m, _ = update(t, m, tea.KeyMsg{Type: tea.KeyPgDown})
	top, _ := viewportEdges(t, m)
	wantContains(t, top, "more charts above")
	m, _ = update(t, m, tea.KeyMsg{Type: tea.KeyHome})
	m, _ = update(t, m, tea.MouseMsg{Button: tea.MouseButtonWheelDown, Action: tea.MouseActionPress})
	if m.offset != 1 {
		t.Fatal("mouse wheel did not scroll past the top indicator")
	}
	top, _ = viewportEdges(t, m)
	wantContains(t, top, "more charts above")
	m, _ = update(t, m, tea.KeyMsg{Type: tea.KeyEnd})
	_, bottom := viewportEdges(t, m)
	if strings.Contains(bottom, "below") {
		t.Fatal("last page still claims more charts below")
	}

	m, _ = update(t, m, tea.WindowSizeMsg{Width: 140, Height: 300})
	top, bottom = viewportEdges(t, m)
	if m.offset != 0 || strings.Contains(top+bottom, "more ") {
		t.Fatal("enlarging the terminal retained unnecessary scroll indicators")
	}
	m, _ = update(t, m, tea.WindowSizeMsg{Width: 100, Height: 24})
	m, _ = update(t, m, tea.KeyMsg{Type: tea.KeyEnd})
	m.history = NewHistory(m.chartsConfig)
	top, bottom = viewportEdges(t, m)
	if strings.Contains(top+bottom, "more ") {
		t.Fatal("shrinking content left indicators at an obsolete scroll position")
	}
	m.height = 0
	if strings.Contains(m.View(), "more charts") {
		t.Fatal("unbounded output should not advertise hidden charts")
	}
}

func TestDetailsKeepsItsOwnMetricNavigationIndicators(t *testing.T) {
	m := detailsModel(t, 140, 30)
	top, bottom := viewportEdges(t, m)
	if strings.Contains(top+bottom, "more ") {
		t.Fatal("Details received duplicate viewport indicators")
	}
	wantContains(t, m.View(), "more metrics below")
}
