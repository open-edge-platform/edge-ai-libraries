// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// Command mm-plugin-membw emits system memory bandwidth as InfluxDB Line
// Protocol on stdout.
//
// The counters live in the integrated memory controller and are read through
// perf, which needs CAP_PERFMON on a machine with the usual
// perf_event_paranoid setting. That is why the bare-metal package runs this as
// its own service rather than as an execd child of the unprivileged Telegraf.
//
// This is whole-system DRAM throughput, not per-device GPU bandwidth. Neither
// Intel GPU driver publishes a byte counter per device: i915 exposes engine
// occupancy, frequencies and resident memory sizes, and xe defines five events
// in total, none of them counting transfers.
//
// Running it directly is a supported way to inspect a machine:
//
//	sudo mm-plugin-membw -once
package main

import (
	"bufio"
	"flag"
	"fmt"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/metrics-manager/native/internal/membw"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/metrics-manager/native/internal/sink"
)

// version is overridden at build time with -ldflags "-X main.version=...".
var version = "dev"

// idleWakeup is how long to sleep between wake-ups once the plugin has decided
// there is nothing to read. Telegraf restarts an execd child that exits, so a
// machine without these counters would otherwise restart it forever.
const idleWakeup = time.Hour

func main() {
	interval := flag.Duration("interval", time.Second,
		"how often to emit a sample; must be greater than zero")
	once := flag.Bool("once", false,
		"emit a single sample and exit, for debugging and parity checks")
	devices := flag.String("devices", membwGlobDefault,
		"glob matching the memory controller PMUs in sysfs")
	hostname := flag.String("hostname", "",
		"value of the host tag; defaults to $METRICS_MANAGER_HOSTNAME, then the kernel hostname")
	destination := flag.String("out", "stdout", sink.Usage)
	showVersion := flag.Bool("version", false, "print the version and exit")
	flag.Parse()

	if *showVersion {
		fmt.Println("mm-plugin-membw", version)
		return
	}

	if err := run(*interval, *once, *devices, resolveHostname(*hostname), *destination); err != nil {
		fmt.Fprintln(os.Stderr, "mm-plugin-membw:", err)
		os.Exit(1)
	}
}

// membwGlobDefault matches the free-running counters of every memory
// controller.
const membwGlobDefault = "/sys/bus/event_source/devices/uncore_imc*"

// resolveHostname mirrors how the other plugins pick the host tag.
func resolveHostname(override string) string {
	if override != "" {
		return override
	}
	if fromEnv := os.Getenv("METRICS_MANAGER_HOSTNAME"); fromEnv != "" {
		return fromEnv
	}
	if kernel, err := os.Hostname(); err == nil {
		return kernel
	}

	return "unknown"
}

func run(interval time.Duration, once bool, devices, hostname, destination string) error {
	if interval <= 0 {
		return fmt.Errorf("-interval must be greater than zero, got %s", interval)
	}

	destinationWriter, err := sink.Open(destination)
	if err != nil {
		return err
	}
	defer destinationWriter.Close()

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt, syscall.SIGTERM)
	defer signal.Stop(stop)

	collector, err := membw.NewCollector(devices, hostname)
	if err != nil {
		// -once is a diagnostic run, so say why rather than parking.
		if once {
			return err
		}

		return idle(stop, err)
	}
	defer collector.Close()

	out := bufio.NewWriter(destinationWriter)

	if once {
		// Throughput is a delta, so the counters opened above need an
		// interval to be measured against.
		select {
		case <-time.After(interval):
		case <-stop:
			return nil
		}

		return emit(collector, out)
	}

	ticker := time.NewTicker(interval)
	defer ticker.Stop()

	for {
		select {
		case <-stop:
			return nil
		case <-ticker.C:
			if err := emit(collector, out); err != nil {
				fmt.Fprintln(os.Stderr, "mm-plugin-membw: dropping sample:", err)
				out.Reset(destinationWriter)
			}
		}
	}
}

// idle parks the process after reporting why, and returns when told to stop.
func idle(stop <-chan os.Signal, reason error) error {
	fmt.Fprintln(os.Stderr, "mm-plugin-membw: no memory bandwidth counters available, idling:", reason)

	ticker := time.NewTicker(idleWakeup)
	defer ticker.Stop()

	for {
		select {
		case <-stop:
			return nil
		case <-ticker.C:
		}
	}
}

// emit collects one sample and writes it out.
func emit(collector *membw.Collector, out *bufio.Writer) error {
	points, err := collector.Collect()
	if err != nil {
		return err
	}

	buf := make([]byte, 0, 256)
	for _, point := range points {
		rendered, err := point.Append(buf[:0])
		if err != nil {
			return err
		}
		if _, err := out.Write(rendered); err != nil {
			return err
		}
	}

	return out.Flush()
}
