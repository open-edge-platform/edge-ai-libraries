// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package tui

import (
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

func (m Model) tabLabels() []string {
	if m.renderWidth() < 55 {
		return []string{"1 O", "2 T", "3 D", "4 A"}
	}
	return []string{"1 Overview", "2 Trends", "3 Details", "4 Alerts"}
}

func (m Model) mouseEnabled() bool {
	return m.config.Mouse && !m.showHelp
}

func (m *Model) handleMouse(msg tea.MouseMsg) {
	if !m.mouseEnabled() || msg.Action != tea.MouseActionPress {
		return
	}
	tabY := 1
	if m.platformLine() != "" {
		tabY++
	}
	if msg.Button == tea.MouseButtonLeft && msg.Y == tabY && msg.X >= 0 && msg.X < m.renderWidth() {
		x := 0
		for i, label := range m.tabLabels() {
			width := lipgloss.Width(label)
			if Tab(i) == m.activeTab {
				width += 2
			}
			if msg.X >= x && msg.X < x+width {
				m.switchTab(Tab(i))
				return
			}
			x += width + 3
		}
		return
	}
	if m.activeTab == DetailsTab {
		m.detailMouse(msg)
	} else {
		switch msg.Button {
		case tea.MouseButtonWheelUp:
			m.setOffset(m.offset - 1)
		case tea.MouseButtonWheelDown:
			m.setOffset(m.offset + 1)
		}
	}
}
