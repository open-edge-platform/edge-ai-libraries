// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package proc

import (
	"bufio"
	"errors"
	"fmt"
	"io"
	"log"
	"os"
	"os/user"
	"strconv"
	"strings"
	"syscall"
	"unicode"
)

func processUID(root *os.Root, pid int) string {
	file, err := root.Open("status")
	if err != nil {
		if !errors.Is(err, os.ErrNotExist) && !errors.Is(err, syscall.ESRCH) {
			log.Printf("proc: PID %d user unavailable: cannot read status: %v", pid, err)
		}
		return ""
	}
	defer file.Close()
	uid, err := readUID(file)
	if err != nil && !errors.Is(err, syscall.ESRCH) {
		log.Printf("proc: PID %d user unavailable: %v", pid, err)
	}
	return uid
}

func readUID(reader io.Reader) (string, error) {
	scanner := bufio.NewScanner(io.LimitReader(reader, 64*1024))
	for scanner.Scan() {
		key, value, found := strings.Cut(scanner.Text(), ":")
		if !found || key != "Uid" {
			continue
		}
		fields := strings.Fields(value)
		if len(fields) != 4 {
			return "", fmt.Errorf("status Uid must contain four identifiers")
		}
		var realUID uint64
		for i, field := range fields {
			uid, err := strconv.ParseUint(field, 10, 32)
			if err != nil {
				return "", fmt.Errorf("status Uid contains an invalid identifier")
			}
			if i == 0 {
				realUID = uid
			}
		}
		return strconv.FormatUint(realUID, 10), nil
	}
	if err := scanner.Err(); err != nil {
		return "", fmt.Errorf("cannot parse status Uid: %w", err)
	}
	return "", fmt.Errorf("status Uid missing within 64 KiB")
}

func (c *Collector) username(uid string) string {
	account, err := c.lookupUser(uid)
	if err != nil {
		var unknown user.UnknownUserIdError
		if !errors.As(err, &unknown) {
			log.Printf("proc: name lookup failed for UID %s; using numeric UID: %v", uid, err)
		}
		return ""
	}
	if account == nil || account.Username == "" || len(account.Username) > 256 ||
		strings.IndexFunc(account.Username, unicode.IsControl) >= 0 {
		log.Printf("proc: invalid account name for UID %s; using numeric UID", uid)
		return ""
	}
	return account.Username
}
