// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// Command mm-plugin-gpu emits Intel GPU telemetry as InfluxDB Line Protocol on
// stdout.
//
// It reads the JSON stream written by qmassa, which must be started separately
// (by supervisord in the container, by a systemd unit on bare metal):
//
//	qmassa --ms-interval 1000 --no-tui --to-json /run/metrics-manager/qmassa.fifo
//
// It is designed to be run by Telegraf's execd input:
//
//	[[inputs.execd]]
//	  command = ["/usr/libexec/metrics-manager/mm-plugin-gpu"]
//	  data_format = "influx"
//
// On a host with no Intel GPU the stream never appears; the plugin then stays
// alive and idle rather than exiting, so Telegraf does not respawn it in a
// loop.
//
// Every graphics tile is reported, tagged with its name, so a multi-tile part
// such as Meteor Lake publishes both gt0 and gt1.
package main

import (
	"bufio"
	"context"
	"flag"
	"fmt"
	"os"
	"os/signal"
	"syscall"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/metrics-manager/native/internal/gpu"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/metrics-manager/native/internal/sink"
)

// version is overridden at build time with -ldflags "-X main.version=...".
var version = "dev"

// defaultFIFOPath matches the container layout; the package overrides it.
const defaultFIFOPath = "/app/qmassa.fifo"

func main() {
	fifoPath := flag.String("fifo", envOr("QMASSA_FIFO_PATH", defaultFIFOPath),
		"path to the JSON stream written by qmassa")
	hostname := flag.String("hostname", "",
		"value of the host tag; defaults to $METRICS_MANAGER_HOSTNAME, then the kernel hostname")
	clients := flag.Bool("clients", false,
		"also emit per-process gpu_client points")
	clientLimit := flag.Int("clients-limit", 10,
		"how many processes -clients reports per GPU, the busiest first; 0 reports every process")
	showVersion := flag.Bool("version", false, "print the version and exit")
	destination := flag.String("out", "stdout", sink.Usage)
	flag.Parse()

	if *showVersion {
		fmt.Println("mm-plugin-gpu", version)
		return
	}

	if *clientLimit < 0 {
		fmt.Fprintln(os.Stderr, "mm-plugin-gpu: -clients-limit cannot be negative")
		os.Exit(1)
	}

	var opts []gpu.Option
	if *clients {
		opts = append(opts, gpu.WithClientStats(*clientLimit))
	}

	if err := run(*fifoPath, resolveHostname(*hostname), *destination, opts...); err != nil {
		fmt.Fprintln(os.Stderr, "mm-plugin-gpu:", err)
		os.Exit(1)
	}
}

// envOr returns the environment variable name, or fallback when it is unset.
func envOr(name, fallback string) string {
	if value := os.Getenv(name); value != "" {
		return value
	}
	return fallback
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

func run(fifoPath, hostname, destination string, opts ...gpu.Option) error {
	destinationWriter, err := sink.Open(destination)
	if err != nil {
		return err
	}
	defer destinationWriter.Close()

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	parser := gpu.NewParser(hostname, opts...)
	out := bufio.NewWriter(destinationWriter)
	defer out.Flush()

	logf := func(format string, args ...any) {
		fmt.Fprintf(os.Stderr, "mm-plugin-gpu: "+format+"\n", args...)
	}

	buf := make([]byte, 0, 256)

	gpu.Follow(ctx, fifoPath, func(line []byte) {
		points, err := parser.Parse(line)
		if err != nil {
			// A malformed line must not kill the plugin: qmassa may still be
			// writing usable samples, and restarting would lose the stream.
			logf("skipping line: %v", err)
			return
		}

		for _, point := range points {
			rendered, err := point.Append(buf[:0])
			if err != nil {
				// Emitting an invalid line would make Telegraf drop the whole
				// batch, so the point is skipped instead.
				logf("skipping point: %v", err)
				continue
			}
			if _, err := out.Write(rendered); err != nil {
				break
			}
		}

		// Flush per sample so Telegraf sees metrics at qmassa's cadence
		// rather than when the buffer happens to fill.
		if err := out.Flush(); err != nil {
			// Losing the reader is recoverable when writing to a socket, which
			// Telegraf takes away whenever it restarts. Reset clears the error
			// bufio.Writer latches, which would otherwise make every later
			// sample fail too. On stdout this is unreachable: a closed pipe
			// raises SIGPIPE and ends the process, as execd expects.
			logf("dropping sample: %v", err)
			out.Reset(destinationWriter)
		}
	}, logf)

	return nil
}
