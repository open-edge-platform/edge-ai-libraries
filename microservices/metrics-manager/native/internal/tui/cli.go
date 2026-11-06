// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package tui

import (
	"bytes"
	"flag"
	"fmt"
	"time"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/metrics-manager/native/internal/source"
)

type StartupOptions struct {
	Endpoint         string
	Interval         time.Duration
	Once             bool
	Width            int
	ConfigPath       string
	ChartsConfigPath string
	Version          bool
}

// RegisterStartupFlags shares flag definitions with the CLI and in-TUI help.
func RegisterStartupFlags(flags *flag.FlagSet) *StartupOptions {
	options := &StartupOptions{}
	flags.StringVar(&options.Endpoint, "endpoint", "http://127.0.0.1:9273/metrics",
		"Prometheus exposition endpoint to read")
	flags.DurationVar(&options.Interval, "interval", source.DefaultInterval,
		"how often to refresh; must be greater than zero")
	flags.BoolVar(&options.Once, "once", false,
		"render a single Overview frame to stdout and exit")
	flags.IntVar(&options.Width, "width", 100,
		"column width to render at with -once")
	flags.StringVar(&options.ConfigPath, "config", DefaultConfigPath,
		"dashboard configuration file; built-in defaults are used when absent")
	flags.StringVar(&options.ChartsConfigPath, "charts-config", DefaultChartsConfigPath,
		"Trends and Details configuration file; built-in defaults are used when absent")
	flags.BoolVar(&options.Version, "version", false, "print the version and exit")
	flags.Usage = func() {
		fmt.Fprint(flags.Output(), CommandLineHelp())
	}
	return options
}

func CommandLineHelp() string {
	var defaults bytes.Buffer
	flags := flag.NewFlagSet("mm-tui", flag.ContinueOnError)
	flags.SetOutput(&defaults)
	RegisterStartupFlags(flags)
	flags.PrintDefaults()
	return "Metrics Manager: monitor Intel CPU, GPU, NPU and optional network/storage telemetry.\n\n" +
		"Usage: mm-tui [options]\n\n" +
		"Options (one or two leading dashes):\n" +
		"  -h, --help\n" +
		"        print help and exit; no running collectors are required\n" +
		defaults.String() +
		"\nExamples:\n" +
		"  mm-tui\n" +
		"  mm-tui --help\n" +
		"  mm-tui -interval 1s\n" +
		"  mm-tui -once -width 140\n" +
		"  mm-tui -endpoint http://127.0.0.1:9273/metrics\n" +
		"  mm-tui -config ./dashboard.json -charts-config ./charts.json\n\n" +
		"Start the Metrics Manager collectors before monitoring.\n" +
		"Use -config for layout, alerts, process limits/CPU mode and network/storage settings;\n" +
		"use -charts-config for chart history and Details selection.\n" +
		"Configuration changes take effect after restarting mm-tui.\n" +
		"In the TUI: h help, a alerts, 1/2/3/4 tabs, s sort, r reverse, c CPU mode, q quit.\n" +
		"In Overview: Left/Right scroll narrow process tables horizontally.\n"
}
