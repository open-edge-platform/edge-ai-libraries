// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// Command mm-plugin-cpu emits CPU frequency and per-core-class utilisation as
// InfluxDB Line Protocol on stdout.
//
// It is designed to be run by Telegraf's execd input:
//
//	[[inputs.execd]]
//	  command = ["/usr/libexec/metrics-manager/mm-plugin-cpu"]
//	  data_format = "influx"
//
// The same binary is used by the containerised Metrics Manager and by the
// bare-metal package, so the two always report identical metrics. Running it
// directly in a terminal is a supported way to inspect a machine:
//
//	mm-plugin-cpu -once
//
// Only kernel files under /proc and /sys are read. No privileges beyond read
// access to those paths are required.
package main

import (
	"bufio"
	"flag"
	"fmt"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/metrics-manager/native/internal/cpu"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/metrics-manager/native/internal/sink"
)

// version is overridden at build time with -ldflags "-X main.version=...".
var version = "dev"

func main() {
	interval := flag.Duration("interval", time.Second,
		"how often to emit a sample; must be greater than zero")
	once := flag.Bool("once", false,
		"emit a single sample and exit, for debugging and parity checks")
	sysfsRoot := flag.String("sysfs-root", "/sys",
		"mount point of sysfs")
	procRoot := flag.String("proc-root", "/proc",
		"mount point of procfs")
	showVersion := flag.Bool("version", false, "print the version and exit")
	showTopology := flag.Bool("topology", false,
		"print the detected core classes and the evidence behind them, then exit")
	destination := flag.String("out", "stdout", sink.Usage)
	flag.Parse()

	if *showVersion {
		fmt.Println("mm-plugin-cpu", version)
		return
	}

	if *showTopology {
		description, err := cpu.Describe(*sysfsRoot)
		if err != nil {
			fmt.Fprintln(os.Stderr, "mm-plugin-cpu:", err)
			os.Exit(1)
		}
		fmt.Print(description)
		return
	}

	if err := run(*interval, *once, *sysfsRoot, *procRoot, *destination); err != nil {
		fmt.Fprintln(os.Stderr, "mm-plugin-cpu:", err)
		os.Exit(1)
	}
}

func run(interval time.Duration, once bool, sysfsRoot, procRoot, destination string) error {
	if interval <= 0 {
		return fmt.Errorf("-interval must be greater than zero, got %s", interval)
	}

	destinationWriter, err := sink.Open(destination)
	if err != nil {
		return err
	}
	defer destinationWriter.Close()

	collector, err := cpu.NewCollector(sysfsRoot, procRoot)
	if err != nil {
		return err
	}

	topology := collector.Topology()
	if !topology.Hybrid {
		fmt.Fprintln(os.Stderr, "mm-plugin-cpu: no hybrid core classes detected, reporting a single class")
	}

	// Telegraf forwards a plugin's stderr into its own log, so this line is how
	// an operator finds out whether the LP-E split was read from the kernel or
	// inferred. Run with -topology for the full evidence.
	for _, class := range topology.Classes {
		fmt.Fprintf(os.Stderr, "mm-plugin-cpu: class %s: %d CPUs (source: %s)\n",
			class.Class, len(class.CPUs), class.Source)
	}
	fmt.Fprintln(os.Stderr, "mm-plugin-cpu: LP-E cores:", topology.LowPowerNote)

	// Telegraf sends SIGTERM when it shuts the plugin down, and SIGINT arrives
	// when the binary is run interactively. Both must flush and exit cleanly
	// rather than truncating a half-written line.
	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt, syscall.SIGTERM)
	defer signal.Stop(stop)

	out := bufio.NewWriter(destinationWriter)

	if once {
		// The priming sample taken by NewCollector is only microseconds old,
		// so wait one interval to report a meaningful utilisation delta.
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
				// Losing the reader is recoverable when writing to a socket,
				// which Telegraf takes away whenever it restarts. Exiting
				// would throw away the counter baseline that utilisation is
				// derived from, so report the sample as lost and carry on.
				//
				// Reset clears the error bufio.Writer latches on a failed
				// write, which would otherwise make every later sample fail
				// too. On stdout this branch is unreachable: a closed pipe
				// raises SIGPIPE and ends the process, which is what execd
				// expects.
				fmt.Fprintln(os.Stderr, "mm-plugin-cpu: dropping sample:", err)
				out.Reset(destinationWriter)
			}
		}
	}
}

// emit collects one sample and writes it out.
//
// A point that cannot be rendered is reported on stderr and skipped: emitting
// a malformed line would make Telegraf discard the entire batch, so one bad
// value must not take the healthy metrics down with it.
func emit(collector *cpu.Collector, out *bufio.Writer) error {
	points, err := collector.Collect()
	if err != nil {
		return err
	}

	buf := make([]byte, 0, 512)
	for _, point := range points {
		rendered, err := point.Append(buf[:0])
		if err != nil {
			fmt.Fprintln(os.Stderr, "mm-plugin-cpu: skipping point:", err)
			continue
		}
		if _, err := out.Write(rendered); err != nil {
			return err
		}
	}

	// execd streams continuously, so the buffer has to be flushed every
	// interval; otherwise Telegraf would see metrics only once 4 KiB of
	// output had accumulated.
	return out.Flush()
}
