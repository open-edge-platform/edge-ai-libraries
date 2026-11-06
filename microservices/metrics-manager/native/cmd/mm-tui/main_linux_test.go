// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package main

import (
	"bytes"
	"flag"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"syscall"
	"testing"
	"time"

	"golang.org/x/sys/unix"
)

func TestSignalChild(t *testing.T) {
	endpoint := os.Getenv("MM_TUI_SIGNAL_TEST_ENDPOINT")
	if endpoint == "" {
		t.Skip("subprocess helper")
	}
	flag.CommandLine = flag.NewFlagSet("mm-tui", flag.ExitOnError)
	os.Args = []string{"mm-tui", "-endpoint", endpoint, "-interval", "10ms"}
	main()
}

func TestSignalExitRestoresTerminal(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		fmt.Fprintln(w, `cpu_usage_idle{cpu="cpu-total",host="test"} 95`)
		fmt.Fprintln(w, `mem_used_percent{host="test"} 40`)
	}))
	defer server.Close()
	executable, err := os.Executable()
	if err != nil {
		t.Fatal(err)
	}
	for _, sig := range []syscall.Signal{syscall.SIGINT, syscall.SIGTERM} {
		t.Run(sig.String(), func(t *testing.T) {
			master, err := os.OpenFile("/dev/ptmx", os.O_RDWR|syscall.O_NOCTTY, 0)
			if err != nil {
				t.Fatal(err)
			}
			defer master.Close()
			if err := unix.IoctlSetPointerInt(int(master.Fd()), unix.TIOCSPTLCK, 0); err != nil {
				t.Fatal(err)
			}
			number, err := unix.IoctlGetInt(int(master.Fd()), unix.TIOCGPTN)
			if err != nil {
				t.Fatal(err)
			}
			slave, err := os.OpenFile(fmt.Sprintf("/dev/pts/%d", number), os.O_RDWR|syscall.O_NOCTTY, 0)
			if err != nil {
				t.Fatal(err)
			}
			defer slave.Close()
			if err := unix.IoctlSetWinsize(int(slave.Fd()), unix.TIOCSWINSZ, &unix.Winsize{Row: 30, Col: 160}); err != nil {
				t.Fatal(err)
			}
			before, err := unix.IoctlGetTermios(int(slave.Fd()), unix.TCGETS)
			if err != nil {
				t.Fatal(err)
			}
			command := exec.Command(executable, "-test.run=^TestSignalChild$")
			command.Env = append(os.Environ(), "TERM=xterm-256color", "MM_TUI_SIGNAL_TEST_ENDPOINT="+server.URL)
			command.Stdin, command.Stdout, command.Stderr = slave, slave, slave
			command.SysProcAttr = &syscall.SysProcAttr{Setsid: true, Setctty: true, Ctty: 0}
			if err := command.Start(); err != nil {
				t.Fatal(err)
			}
			exited := make(chan error, 1)
			go func() { exited <- command.Wait() }()
			ready := make(chan struct{})
			output := make(chan []byte, 1)
			go func() {
				var data []byte
				announced := false
				buffer := make([]byte, 4096)
				for {
					n, err := master.Read(buffer)
					data = append(data, buffer[:n]...)
					if len(data) > 65536 {
						data = data[len(data)-65536:]
					}
					if !announced && bytes.Contains(data, []byte("[1 Overview]")) {
						close(ready)
						announced = true
					}
					if err != nil {
						output <- data
						return
					}
				}
			}()
			waited := false
			defer func() {
				if !waited {
					if err := command.Process.Kill(); err != nil {
						t.Logf("kill test child: %v", err)
					}
					<-exited
				}
				slave.Close()
				master.Close()
				trace := <-output
				if t.Failed() {
					t.Logf("terminal output: %s", trace)
				} else if !bytes.Contains(trace, []byte("\x1b[?1049l")) {
					t.Error("alternate screen was not restored")
				}
			}()
			select {
			case <-ready:
			case err := <-exited:
				waited = true
				t.Fatalf("CLI exited before its first frame: %v", err)
			case <-time.After(10 * time.Second):
				t.Fatal("CLI did not render its first frame")
			}
			if err := command.Process.Signal(sig); err != nil {
				t.Fatal(err)
			}
			select {
			case err := <-exited:
				waited = true
				if err != nil {
					t.Fatalf("signal exit failed: %v", err)
				}
			case <-time.After(5 * time.Second):
				t.Fatal("signal exit deadlocked")
			}
			after, err := unix.IoctlGetTermios(int(slave.Fd()), unix.TCGETS)
			if err != nil {
				t.Fatal(err)
			}
			if *after != *before {
				t.Error("terminal attributes were not restored")
			}
		})
	}
}
