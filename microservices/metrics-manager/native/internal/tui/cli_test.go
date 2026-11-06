// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package tui

import (
	"bytes"
	"errors"
	"flag"
	"reflect"
	"strings"
	"testing"
	"time"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/metrics-manager/native/internal/source"
)

func TestStartupHelpAliases(t *testing.T) {
	for _, alias := range []string{"-h", "--help", "-help"} {
		t.Run(alias, func(t *testing.T) {
			var output bytes.Buffer
			flags := flag.NewFlagSet("mm-tui", flag.ContinueOnError)
			flags.SetOutput(&output)
			RegisterStartupFlags(flags)
			if err := flags.Parse([]string{alias}); !errors.Is(err, flag.ErrHelp) {
				t.Fatalf("help returned %v, want ErrHelp", err)
			}
			if output.String() != CommandLineHelp() {
				t.Fatalf("help alias did not print shared reference: %q", output.String())
			}
			flags.VisitAll(func(option *flag.Flag) {
				if !strings.Contains(output.String(), "-"+option.Name) {
					t.Errorf("help omitted %s", option.Name)
				}
			})
		})
	}
}

func TestStartupOptionsPreserveDefaultsAndParsing(t *testing.T) {
	flags := flag.NewFlagSet("mm-tui", flag.ContinueOnError)
	options := RegisterStartupFlags(flags)
	want := StartupOptions{
		Endpoint: "http://127.0.0.1:9273/metrics", Interval: source.DefaultInterval,
		Width: 100, ConfigPath: DefaultConfigPath, ChartsConfigPath: DefaultChartsConfigPath,
	}
	if !reflect.DeepEqual(*options, want) {
		t.Fatalf("defaults changed: %+v", options)
	}
	if err := flags.Parse([]string{
		"--endpoint", "http://127.0.0.1:1234/metrics", "-interval", "2s",
		"--once", "-width", "140", "--config", "./dashboard.json",
		"-charts-config", "./charts.json", "--version",
	}); err != nil {
		t.Fatal(err)
	}
	want = StartupOptions{
		Endpoint: "http://127.0.0.1:1234/metrics", Interval: 2 * time.Second,
		Once: true, Width: 140, ConfigPath: "./dashboard.json",
		ChartsConfigPath: "./charts.json", Version: true,
	}
	if !reflect.DeepEqual(*options, want) {
		t.Fatalf("parsed options=%+v, want %+v", options, want)
	}
	for _, invalid := range [][]string{{"--unknown"}, {"-interval", "invalid"}, {"-width", "invalid"}} {
		var output bytes.Buffer
		flags := flag.NewFlagSet("mm-tui", flag.ContinueOnError)
		flags.SetOutput(&output)
		RegisterStartupFlags(flags)
		if err := flags.Parse(invalid); err == nil || errors.Is(err, flag.ErrHelp) {
			t.Fatalf("invalid flags %v returned %v", invalid, err)
		}
	}
}
