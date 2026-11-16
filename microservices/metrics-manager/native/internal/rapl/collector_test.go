// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package rapl

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func writeZoneFile(t *testing.T, root, zone, file, value string) {
	t.Helper()
	path := filepath.Join(root, "class/powercap", zone)
	if err := os.MkdirAll(path, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(path, file), []byte(value), 0o644); err != nil {
		t.Fatal(err)
	}
}

func makeZone(t *testing.T, root, id, name, energy, max string) {
	t.Helper()
	for file, value := range map[string]string{
		"name": name, "energy_uj": energy, "max_energy_range_uj": max,
	} {
		writeZoneFile(t, root, id, file, value)
	}
}

func TestCollectorTopLevelZonesPowerAndWrap(t *testing.T) {
	root := t.TempDir()
	makeZone(t, root, "intel-rapl:0", "package-0\n", "1000000\n", "10000000\n")
	makeZone(t, root, "intel-rapl:1", "psys\n", "9000000\n", "10000000\n")
	makeZone(t, root, "intel-rapl:0:0", "core\n", "2000000\n", "10000000\n")
	c, err := NewCollector(root, "test-host")
	if err != nil {
		t.Fatal(err)
	}
	if len(c.zones) != 2 {
		t.Fatalf("found %d zones, want package and psys", len(c.zones))
	}
	start := time.Unix(100, 0)
	for i := range c.zones {
		c.zones[i].sampled = start
	}
	c.now = func() time.Time { return start.Add(time.Second) }
	writeZoneFile(t, root, "intel-rapl:0", "energy_uj", "3500000")
	writeZoneFile(t, root, "intel-rapl:1", "energy_uj", "1000000")
	points, err := c.Collect()
	if err != nil {
		t.Fatal(err)
	}
	if len(points) != 2 {
		t.Fatalf("got %d points, want 2", len(points))
	}
	for i, want := range []string{
		"rapl_power,host=test-host,domain=package-0 power_w=2.500 101000000000\n",
		"rapl_power,host=test-host,domain=psys power_w=2.000 101000000000\n",
	} {
		got, err := points[i].Append(nil)
		if err != nil || string(got) != want {
			t.Errorf("point %d = %q, %v, want %q", i, got, err, want)
		}
	}
}

func TestCollectorSkipsUnreadableZoneAndReportsNoZones(t *testing.T) {
	root := t.TempDir()
	if _, err := NewCollector(root, "host"); err == nil {
		t.Fatal("expected error without zones")
	}
	writeZoneFile(t, root, "intel-rapl:0", "name", "psys")
	_, err := NewCollector(root, "host")
	if err == nil || !strings.Contains(err.Error(), "energy_uj") {
		t.Fatalf("missing counter error = %v", err)
	}
	makeZone(t, root, "intel-rapl:1", "package-0", "1000000", "10000000")
	c, err := NewCollector(root, "host")
	if err != nil || len(c.zones) != 1 {
		t.Fatalf("partially readable zones = %v, %v", c, err)
	}
}

func TestCollectorReadErrorReprimesAndDoesNotInventPower(t *testing.T) {
	root := t.TempDir()
	makeZone(t, root, "intel-rapl:0", "psys", "1000000", "10000000")
	c, err := NewCollector(root, "host")
	if err != nil {
		t.Fatal(err)
	}
	start := time.Unix(100, 0)
	c.zones[0].sampled = start
	elapsed := time.Second
	c.now = func() time.Time { return start.Add(elapsed) }
	writeZoneFile(t, root, "intel-rapl:0", "energy_uj", "broken")
	if points, err := c.Collect(); err == nil || len(points) != 0 {
		t.Fatalf("invalid energy yielded %v, %v", points, err)
	}
	elapsed = 2 * time.Second
	writeZoneFile(t, root, "intel-rapl:0", "energy_uj", "3000000")
	if points, err := c.Collect(); err != nil || len(points) != 0 {
		t.Fatalf("first valid reading after failure yielded %v, %v", points, err)
	}
	elapsed = 3 * time.Second
	writeZoneFile(t, root, "intel-rapl:0", "energy_uj", "4000000")
	points, err := c.Collect()
	if err != nil || len(points) != 1 {
		t.Fatalf("recovered reading yielded %v, %v", points, err)
	}
	got, err := points[0].Append(nil)
	if err != nil || !strings.Contains(string(got), "power_w=1.000") {
		t.Errorf("recovered point = %q, %v", got, err)
	}
}

func TestCollectorSkipsCounterDropWithoutRange(t *testing.T) {
	root := t.TempDir()
	writeZoneFile(t, root, "intel-rapl:0", "name", "psys")
	writeZoneFile(t, root, "intel-rapl:0", "energy_uj", "9000000")
	c, err := NewCollector(root, "host")
	if err != nil {
		t.Fatal(err)
	}
	start := time.Unix(100, 0)
	c.zones[0].sampled = start
	c.now = func() time.Time { return start.Add(time.Second) }
	writeZoneFile(t, root, "intel-rapl:0", "energy_uj", "1000000")
	if points, err := c.Collect(); err == nil || len(points) != 0 {
		t.Fatalf("counter drop yielded %v, %v", points, err)
	}
}
