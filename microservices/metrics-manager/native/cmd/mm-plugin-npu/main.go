// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// Command mm-plugin-npu emits Intel NPU telemetry as InfluxDB Line Protocol on
// stdout.
//
// It is designed to be run by Telegraf's execd input:
//
//	[[inputs.execd]]
//	  command = ["/usr/libexec/metrics-manager/mm-plugin-npu"]
//	  data_format = "influx"
//
// The same binary is used by the containerised Metrics Manager and by the
// bare-metal package. Running it directly is a supported way to inspect a
// machine:
//
//	mm-plugin-npu -once
//
// Reading PMT telemetry requires root: the kernel exposes
// /sys/class/intel_pmt/telem*/telem to the owner only. That is why the
// bare-metal package does not run this plugin under Telegraf, which is
// unprivileged there, but as its own root service writing to Telegraf's
// socket_listener input. See -out.
package main

import (
	"bufio"
	"flag"
	"fmt"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/metrics-manager/native/internal/npu"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/metrics-manager/native/internal/sink"
)

// version is overridden at build time with -ldflags "-X main.version=...".
var version = "dev"

// idleWakeup is how long to sleep between wake-ups once the plugin has decided
// there is no NPU to read.
//
// Telegraf restarts an execd child that exits, so a machine without an NPU
// would otherwise produce a restart every few seconds forever. Staying alive
// and idle keeps the log quiet and leaves the other inputs untouched.
const idleWakeup = time.Hour

func main() {
	interval := flag.Duration("interval", time.Second,
		"how often to emit a sample; must be greater than zero")
	once := flag.Bool("once", false,
		"emit a single sample and exit, for debugging and parity checks")
	sysfsRoot := flag.String("sysfs-root", "/sys", "mount point of sysfs")
	hostname := flag.String("hostname", "",
		"value of the host tag; defaults to $METRICS_MANAGER_HOSTNAME, then the kernel hostname")
	destination := flag.String("out", "stdout", sink.Usage)
	showVersion := flag.Bool("version", false, "print the version and exit")
	flag.Parse()

	if *showVersion {
		fmt.Println("mm-plugin-npu", version)
		return
	}

	if err := run(*interval, *once, *sysfsRoot, resolveHostname(*hostname), *destination); err != nil {
		fmt.Fprintln(os.Stderr, "mm-plugin-npu:", err)
		os.Exit(1)
	}
}

// resolveHostname mirrors how the Telegraf agent and the Python readers pick
// the host tag, so every metric from this service carries the same value.
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

func run(interval time.Duration, once bool, sysfsRoot, hostname, destination string) error {
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

	collector, err := npu.NewCollector(sysfsRoot, hostname)
	if err != nil {
		// -once is a diagnostic run, so report the reason and fail rather than
		// hanging on a machine the operator is inspecting by hand.
		if once {
			return err
		}
		return idle(stop, err)
	}

	fmt.Fprintf(os.Stderr, "mm-plugin-npu: %s NPU detected (utilisation: %t, memory usage: %t)\n",
		collector.Gen(), collector.BusyTimeSupported(), collector.MemoryUtilisationSupported())

	out := bufio.NewWriter(destinationWriter)

	if once {
		// The priming sample taken by NewCollector is only microseconds old,
		// so wait one interval for a meaningful delta.
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
				// Losing the reader is recoverable and expected: Telegraf owns
				// the socket and takes it away whenever it restarts. Exiting
				// would throw away the counter baseline that utilisation is
				// derived from, so report the sample as lost and carry on.
				//
				// Reset clears the error bufio.Writer latches on a failed
				// write, which would otherwise make every later sample fail
				// too. On stdout this branch is unreachable: a closed pipe
				// raises SIGPIPE and ends the process, which is what execd
				// expects.
				fmt.Fprintln(os.Stderr, "mm-plugin-npu: dropping sample:", err)
				out.Reset(destinationWriter)
			}
		}
	}
}

// idle parks the process after reporting why, and returns when told to stop.
func idle(stop <-chan os.Signal, reason error) error {
	fmt.Fprintln(os.Stderr, "mm-plugin-npu: no NPU telemetry available, idling:", reason)

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
//
// A point that cannot be rendered is reported on stderr and skipped: emitting
// a malformed line would make Telegraf discard the entire batch.
func emit(collector *npu.Collector, out *bufio.Writer) error {
	points, err := collector.Collect()
	if err != nil {
		// A transient read failure must not kill the plugin, or Telegraf would
		// restart it and lose the counters the deltas are built from.
		fmt.Fprintln(os.Stderr, "mm-plugin-npu: skipping sample:", err)
		return nil
	}

	buf := make([]byte, 0, 256)
	for _, point := range points {
		rendered, err := point.Append(buf[:0])
		if err != nil {
			fmt.Fprintln(os.Stderr, "mm-plugin-npu: skipping point:", err)
			continue
		}
		if _, err := out.Write(rendered); err != nil {
			return err
		}
	}

	return out.Flush()
}
