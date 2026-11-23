// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// Command mm-plugin-proc emits the busiest processes as InfluxDB Line Protocol
// on stdout.
//
// It is designed to be run by Telegraf's execd input:
//
//	[[inputs.execd]]
//	  command = ["/usr/libexec/metrics-manager/mm-plugin-proc"]
//	  data_format = "influx"
//
// Reading /proc needs no privileges, but it does need to see other processes.
// A service hardened with ProtectProc=invisible sees only its own, which is
// why the bare-metal package runs this as its own unit rather than under the
// Telegraf that serves the endpoint.
//
// Running it directly is a supported way to inspect a machine:
//
//	mm-plugin-proc -once
package main

import (
	"bufio"
	"flag"
	"fmt"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/metrics-manager/native/internal/proc"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/metrics-manager/native/internal/sink"
)

// version is overridden at build time with -ldflags "-X main.version=...".
var version = "dev"

func main() {
	interval := flag.Duration("interval", time.Second,
		"how often to emit a sample; must be greater than zero")
	once := flag.Bool("once", false,
		"emit a single sample and exit, for debugging and parity checks")
	procRoot := flag.String("proc-root", "/proc", "mount point of procfs")
	limit := flag.Int("limit", 10,
		"how many processes to report per ranking; 0 reports every process")
	hostname := flag.String("hostname", "",
		"value of the host tag; defaults to $METRICS_MANAGER_HOSTNAME, then the kernel hostname")
	destination := flag.String("out", "stdout", sink.Usage)
	showVersion := flag.Bool("version", false, "print the version and exit")
	flag.Parse()

	if *showVersion {
		fmt.Println("mm-plugin-proc", version)
		return
	}

	if err := run(*interval, *once, *procRoot, resolveHostname(*hostname), *destination, *limit); err != nil {
		fmt.Fprintln(os.Stderr, "mm-plugin-proc:", err)
		os.Exit(1)
	}
}

// resolveHostname mirrors how the Telegraf agent and the other plugins pick
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

func run(interval time.Duration, once bool, procRoot, hostname, destination string, limit int) error {
	if interval <= 0 {
		return fmt.Errorf("-interval must be greater than zero, got %s", interval)
	}

	destinationWriter, err := sink.Open(destination)
	if err != nil {
		return err
	}
	defer destinationWriter.Close()

	collector, err := proc.NewCollector(procRoot, hostname, limit)
	if err != nil {
		return err
	}

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt, syscall.SIGTERM)
	defer signal.Stop(stop)

	out := bufio.NewWriter(destinationWriter)

	if once {
		// Utilisation is a delta, so the priming sample taken by
		// NewCollector needs an interval to be measured against.
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
				// Losing the reader is recoverable: Telegraf owns the
				// socket and takes it away when it restarts. Reset
				// clears the error bufio.Writer latches, which would
				// otherwise fail every later sample too.
				fmt.Fprintln(os.Stderr, "mm-plugin-proc: dropping sample:", err)
				out.Reset(destinationWriter)
			}
		}
	}
}

// emit collects one sample and writes it out.
func emit(collector *proc.Collector, out *bufio.Writer) error {
	points, err := collector.Collect()
	if err != nil {
		// A transient read failure must not kill the plugin, or Telegraf
		// would restart it and lose the counters the deltas are built from.
		fmt.Fprintln(os.Stderr, "mm-plugin-proc: skipping sample:", err)
		return nil
	}

	buf := make([]byte, 0, 256)
	for _, point := range points {
		rendered, err := point.Append(buf[:0])
		if err != nil {
			// A malformed line would make Telegraf discard the whole
			// batch, so the point is dropped instead.
			fmt.Fprintln(os.Stderr, "mm-plugin-proc: skipping point:", err)
			continue
		}
		if _, err := out.Write(rendered); err != nil {
			return err
		}
	}

	return out.Flush()
}
