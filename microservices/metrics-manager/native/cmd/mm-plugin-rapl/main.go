// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// Command mm-plugin-rapl exports RAPL package and platform power as InfluxDB
// line protocol. The bare-metal package runs it with read-only privileges in
// its own service; the container can run it as a Telegraf execd input.
package main

import (
	"bufio"
	"flag"
	"fmt"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/metrics-manager/native/internal/rapl"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/metrics-manager/native/internal/sink"
)

var version = "dev"

func main() {
	interval := flag.Duration("interval", time.Second, "sample interval; must be greater than zero")
	once := flag.Bool("once", false, "emit one sample and exit, reporting unavailable counters")
	sysfsRoot := flag.String("sysfs-root", "/sys", "mount point of sysfs")
	hostname := flag.String("hostname", "", "host tag; defaults to $METRICS_MANAGER_HOSTNAME, then kernel hostname")
	destination := flag.String("out", "stdout", sink.Usage)
	showVersion := flag.Bool("version", false, "print the version and exit")
	flag.Parse()

	if *showVersion {
		fmt.Println("mm-plugin-rapl", version)
		return
	}
	if err := run(*interval, *once, *sysfsRoot, resolveHostname(*hostname), *destination); err != nil {
		fmt.Fprintln(os.Stderr, "mm-plugin-rapl:", err)
		os.Exit(1)
	}
}

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
	writer, err := sink.Open(destination)
	if err != nil {
		return err
	}
	defer writer.Close()

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt, syscall.SIGTERM)
	defer signal.Stop(stop)

	collector, err := rapl.NewCollector(sysfsRoot, hostname)
	if err != nil {
		if once {
			return err
		}
		fmt.Fprintln(os.Stderr, "mm-plugin-rapl: no RAPL power available, idling:", err)
		<-stop
		return nil
	}
	out := bufio.NewWriter(writer)
	if once {
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
				fmt.Fprintln(os.Stderr, "mm-plugin-rapl: dropping sample:", err)
				out.Reset(writer)
			}
		}
	}
}

func emit(collector *rapl.Collector, out *bufio.Writer) error {
	points, collectErr := collector.Collect()
	if collectErr != nil {
		fmt.Fprintln(os.Stderr, "mm-plugin-rapl: skipping unavailable samples:", collectErr)
	}
	if len(points) == 0 && collectErr != nil {
		return collectErr
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
