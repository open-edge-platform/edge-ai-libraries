// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package tui

import (
	"context"
	"errors"
	"testing"
	"time"

	tea "github.com/charmbracelet/bubbletea"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/metrics-manager/native/internal/source"
)

// fixedNow pins the clock so staleness assertions do not depend on how long
// the test took to run.
var fixedNow = time.Date(2026, 7, 20, 12, 0, 0, 0, time.UTC)

func testModel(ch <-chan source.Snapshot) Model {
	m := NewModel(ch)
	m.now = func() time.Time { return fixedNow }

	return m
}

// update applies one message and returns the resulting model.
func update(t *testing.T, m Model, msg tea.Msg) (Model, tea.Cmd) {
	t.Helper()

	next, cmd := m.Update(msg)
	got, ok := next.(Model)
	if !ok {
		t.Fatalf("Update returned %T, want Model", next)
	}

	return got, cmd
}

// isQuit reports whether cmd is the quit command.
func isQuit(cmd tea.Cmd) bool {
	if cmd == nil {
		return false
	}
	_, ok := cmd().(tea.QuitMsg)

	return ok
}

// key builds the key message whose String() is name. Update switches on that
// string form, so the tests drive it the same way the runtime does.
func key(name string) tea.KeyMsg {
	switch name {
	case "esc":
		return tea.KeyMsg(tea.Key{Type: tea.KeyEsc})
	case "ctrl+c":
		return tea.KeyMsg(tea.Key{Type: tea.KeyCtrlC})
	default:
		return tea.KeyMsg(tea.Key{Type: tea.KeyRunes, Runes: []rune(name)})
	}
}

func TestUpdateQuitKeys(t *testing.T) {
	for _, name := range []string{"q", "esc", "ctrl+c"} {
		t.Run(name, func(t *testing.T) {
			msg := key(name)
			if msg.String() != name {
				t.Fatalf("test built %q, want %q", msg.String(), name)
			}

			if _, cmd := testModel(nil).Update(msg); !isQuit(cmd) {
				t.Errorf("key %q did not quit", name)
			}
		})
	}
}

func TestUpdateIgnoresOtherKeys(t *testing.T) {
	_, cmd := testModel(nil).Update(key("x"))

	if isQuit(cmd) {
		t.Error("an unrelated key quit the program")
	}
}

func TestUpdateSwitchesTabs(t *testing.T) {
	m := testModel(nil)
	m, _ = update(t, m, tea.KeyMsg{Type: tea.KeyTab})
	if m.activeTab != TrendsTab {
		t.Errorf("activeTab = %v, want TrendsTab", m.activeTab)
	}
	m, _ = update(t, m, key("1"))
	if m.activeTab != OverviewTab {
		t.Errorf("activeTab = %v, want OverviewTab", m.activeTab)
	}
	m, _ = update(t, m, key("2"))
	if m.activeTab != TrendsTab {
		t.Errorf("activeTab = %v after key 2, want TrendsTab", m.activeTab)
	}
}

func TestUpdateKeepsIndependentTabOffsets(t *testing.T) {
	m := acceleratorModel(t, 24)
	m, _ = update(t, m, tea.KeyMsg{Type: tea.KeyEnd})
	overviewOffset := m.offset
	if overviewOffset == 0 {
		t.Fatal("overview did not scroll")
	}

	m, _ = update(t, m, key("2"))
	if m.offset != 0 {
		t.Errorf("new trends tab offset = %d, want 0", m.offset)
	}
	m, _ = update(t, m, key("1"))
	if m.offset != overviewOffset {
		t.Errorf("restored overview offset = %d, want %d", m.offset, overviewOffset)
	}
}

func TestUpdateWindowSize(t *testing.T) {
	m, _ := update(t, testModel(nil), tea.WindowSizeMsg{Width: 120, Height: 40})

	if m.width != 120 || m.height != 40 {
		t.Errorf("size = %dx%d, want 120x40", m.width, m.height)
	}
}

func TestUpdateSnapshotStoresDashboard(t *testing.T) {
	ch := make(chan source.Snapshot, 1)
	at := fixedNow.Add(-time.Second)

	m, cmd := update(t, testModel(ch), snapshotMsg(source.Snapshot{
		At:      at,
		Samples: parseFixture(t, hostExposition),
	}))

	if m.err != nil {
		t.Errorf("err = %v, want nil", m.err)
	}
	if !m.updatedAt.Equal(at) {
		t.Errorf("updatedAt = %v, want %v", m.updatedAt, at)
	}
	if m.dash.Host != "itest" {
		t.Errorf("host = %q, want itest", m.dash.Host)
	}
	// The loop must re-arm, or the dashboard would freeze after one
	// refresh.
	if cmd == nil {
		t.Error("Update returned no command, want the next wait")
	}
}

func TestUpdateFailedSnapshotKeepsLastNumbers(t *testing.T) {
	// A brief loss of contact should leave the last known numbers on
	// screen marked stale, not blank the display.
	at := fixedNow.Add(-time.Second)
	m, _ := update(t, testModel(nil), snapshotMsg(source.Snapshot{
		At:      at,
		Samples: parseFixture(t, hostExposition),
	}))

	m, cmd := update(t, m, snapshotMsg(source.Snapshot{
		At:  fixedNow,
		Err: errors.New("connection refused"),
	}))

	if m.err == nil {
		t.Fatal("err = nil, want the failure to be recorded")
	}
	if m.dash.Host != "itest" {
		t.Errorf("host = %q, want the previous snapshot to be kept", m.dash.Host)
	}
	if !m.updatedAt.Equal(at) {
		t.Errorf("updatedAt = %v, want it to stay at the last success %v", m.updatedAt, at)
	}
	if cmd == nil {
		t.Error("Update returned no command, want it to keep polling after a failure")
	}
}

func TestUpdateRecoveryClearsError(t *testing.T) {
	m, _ := update(t, testModel(nil), snapshotMsg(source.Snapshot{
		At:  fixedNow,
		Err: errors.New("connection refused"),
	}))
	m, _ = update(t, m, snapshotMsg(source.Snapshot{
		At:      fixedNow,
		Samples: parseFixture(t, hostExposition),
	}))

	if m.err != nil {
		t.Errorf("err = %v, want nil once contact is restored", m.err)
	}
}

func TestUpdateStreamClosedQuits(t *testing.T) {
	// The channel only closes when the poller's context was cancelled, so
	// there is nothing left to display.
	_, cmd := testModel(nil).Update(streamClosedMsg{})

	if !isQuit(cmd) {
		t.Error("a closed stream did not quit")
	}
}

func TestInitWaitsForSnapshot(t *testing.T) {
	ch := make(chan source.Snapshot, 1)
	ch <- source.Snapshot{At: fixedNow}

	cmd := testModel(ch).Init()
	if cmd == nil {
		t.Fatal("Init returned no command")
	}
	batch, ok := cmd().(tea.BatchMsg)
	if !ok || len(batch) != 3 {
		t.Fatalf("Init did not schedule a snapshot and independent clock: %T", batch)
	}
	if _, ok := batch[0]().(snapshotMsg); !ok {
		t.Error("Init did not deliver the queued snapshot")
	}
}

func TestWaitForSnapshotReportsClosedChannel(t *testing.T) {
	ch := make(chan source.Snapshot)
	close(ch)

	if _, ok := waitForSnapshot(ch)().(streamClosedMsg); !ok {
		t.Error("a closed channel did not produce streamClosedMsg")
	}
}

func TestSendDropsStaleSnapshot(t *testing.T) {
	// The display only ever wants the newest snapshot; blocking instead
	// would stall the poller behind a slow terminal.
	ch := make(chan source.Snapshot, 1)

	send(ch, source.Snapshot{At: fixedNow.Add(-2 * time.Second)})
	send(ch, source.Snapshot{At: fixedNow.Add(-time.Second)})
	send(ch, source.Snapshot{At: fixedNow})

	got := <-ch
	if !got.At.Equal(fixedNow) {
		t.Errorf("At = %v, want the newest snapshot %v", got.At, fixedNow)
	}
	select {
	case extra := <-ch:
		t.Errorf("channel still held %v, want only the newest", extra.At)
	default:
	}
}

func TestShutdownErr(t *testing.T) {
	cancelled, cancel := context.WithCancel(context.Background())
	cancel()

	other := errors.New("terminal is unusable")

	tests := []struct {
		name    string
		err     error
		parent  context.Context
		wantErr error
	}{
		{
			// A signal stops the program by cancelling the context,
			// so exiting non-zero here would have systemd record
			// every ordinary stop as a failure.
			name:   "killed after a signal is a clean stop",
			err:    tea.ErrProgramKilled,
			parent: cancelled,
		},
		{
			// Without cancellation the same error means Bubble Tea
			// died on its own, which is a real failure.
			name:    "killed without cancellation is reported",
			err:     tea.ErrProgramKilled,
			parent:  context.Background(),
			wantErr: tea.ErrProgramKilled,
		},
		{
			name:    "unrelated failure survives cancellation",
			err:     other,
			parent:  cancelled,
			wantErr: other,
		},
		{
			name:   "success stays successful",
			parent: cancelled,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := shutdownErr(tt.err, tt.parent); !errors.Is(got, tt.wantErr) {
				t.Errorf("shutdownErr(%v) = %v, want %v", tt.err, got, tt.wantErr)
			}
		})
	}
}
