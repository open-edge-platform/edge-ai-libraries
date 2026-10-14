// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package common

import "testing"

func TestCheckIDAcceptsBase64URLPrefix(t *testing.T) {
	for _, value := range []string{"_RClKSovSHSUbIf_hlnCIw", "-RClKSovSHSUbIf_hlnCIw", "str-_RClKSovSHSUbIf_hlnCIw"} {
		if err := CheckID("recording-id", value); err != nil {
			t.Fatalf("rejected resource ID %q: %v", value, err)
		}
	}
	for _, value := range []string{"_sensor", "-sensor", ".sensor"} {
		if err := CheckID("sensor_id", value); err == nil {
			t.Fatalf("accepted invalid sensor ID %q", value)
		}
	}
}
