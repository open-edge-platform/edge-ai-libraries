// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// Package rapl reports power derived from the top-level Intel RAPL energy zones.
package rapl

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/metrics-manager/native/internal/lineproto"
)

const Measurement = "rapl_power"

type zone struct {
	name, energyPath string
	maxRange         uint64
	previous         uint64
	sampled          time.Time
	primed           bool
}

// Collector samples the package and platform (psys) zones, excluding subzones
// already covered by intel_powerstat. It is not safe for concurrent use.
type Collector struct {
	hostname string
	zones    []zone
	now      func() time.Time
}

// NewCollector discovers readable top-level zones and primes their counters.
// Inaccessible zones are reported but do not prevent other zones from working.
func NewCollector(sysfsRoot, hostname string) (*Collector, error) {
	paths, err := filepath.Glob(filepath.Join(sysfsRoot, "class/powercap/intel-rapl:*"))
	if err != nil {
		return nil, fmt.Errorf("discovering RAPL zones: %w", err)
	}
	sort.Strings(paths)

	c := &Collector{hostname: hostname, now: time.Now}
	var failures []error
	for _, path := range paths {
		id, ok := strings.CutPrefix(filepath.Base(path), "intel-rapl:")
		if !ok || id == "" || strings.Contains(id, ":") {
			continue
		}
		if _, err := strconv.ParseUint(id, 10, 32); err != nil {
			continue
		}
		name, err := os.ReadFile(filepath.Join(path, "name"))
		if err != nil {
			failures = append(failures, fmt.Errorf("%s name: %w", path, err))
			continue
		}
		domain := strings.TrimSpace(string(name))
		if domain == "" {
			domain = filepath.Base(path)
		}
		energyPath := filepath.Join(path, "energy_uj")
		energy, err := readEnergy(energyPath)
		if err != nil {
			failures = append(failures, err)
			continue
		}
		maxRange, err := readEnergy(filepath.Join(path, "max_energy_range_uj"))
		if err != nil {
			// A missing range prevents wrap recovery but not normal deltas.
			failures = append(failures, err)
		}
		c.zones = append(c.zones, zone{
			name: domain, energyPath: energyPath, maxRange: maxRange,
			previous: energy, sampled: c.now(), primed: true,
		})
	}
	if len(c.zones) == 0 {
		if len(failures) > 0 {
			return nil, fmt.Errorf("no readable RAPL zones: %w", errors.Join(failures...))
		}
		return nil, fmt.Errorf("no top-level Intel RAPL zones under %s", sysfsRoot)
	}
	if len(failures) > 0 {
		fmt.Fprintln(os.Stderr, "mm-plugin-rapl: skipping unavailable RAPL attributes:", errors.Join(failures...))
	}
	return c, nil
}

func readEnergy(path string) (uint64, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return 0, fmt.Errorf("reading %s: %w", path, err)
	}
	value, err := strconv.ParseUint(strings.TrimSpace(string(raw)), 10, 64)
	if err != nil {
		return 0, fmt.Errorf("parsing %s: %w", path, err)
	}
	return value, nil
}

// Collect computes power from actual elapsed time and returns one point per
// readable domain. A failed read invalidates only that zone's baseline; its
// next successful read primes it again rather than producing a false spike.
func (c *Collector) Collect() ([]lineproto.Point, error) {
	var points []lineproto.Point
	var failures []error
	for i := range c.zones {
		z := &c.zones[i]
		energy, err := readEnergy(z.energyPath)
		now := c.now()
		if err != nil {
			z.primed = false
			failures = append(failures, err)
			continue
		}
		previous, sampled, primed := z.previous, z.sampled, z.primed
		z.previous, z.sampled, z.primed = energy, now, true
		if !primed || !now.After(sampled) {
			continue
		}
		var delta uint64
		if energy >= previous {
			delta = energy - previous
		} else if z.maxRange > 0 && previous <= z.maxRange && energy <= z.maxRange {
			delta = z.maxRange - previous + energy
		} else {
			failures = append(failures, fmt.Errorf("%s: energy counter decreased without a usable wrap range", z.name))
			continue
		}
		power := float64(delta) / now.Sub(sampled).Seconds() / 1e6
		points = append(points, lineproto.Point{
			Measurement: Measurement,
			Tags: []lineproto.Tag{
				{Key: "host", Value: c.hostname},
				{Key: "domain", Value: z.name},
			},
			Fields:    []lineproto.Field{lineproto.FixedFloatField("power_w", power, 3)},
			Timestamp: now,
		})
	}
	return points, errors.Join(failures...)
}
