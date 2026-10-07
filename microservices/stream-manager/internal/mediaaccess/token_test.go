// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package mediaaccess

import (
	"errors"
	"strings"
	"testing"
	"time"
)

func TestSignVerifyRoundTrip(t *testing.T) {
	signer, err := NewSigner("test-secret")
	if err != nil {
		t.Fatalf("NewSigner: %v", err)
	}
	token, err := signer.Sign("derived/rec-001/frames/x.jpeg", time.Now().Add(time.Minute))
	if err != nil {
		t.Fatalf("Sign: %v", err)
	}
	key, err := signer.Verify(token)
	if err != nil {
		t.Fatalf("Verify: %v", err)
	}
	if key != "derived/rec-001/frames/x.jpeg" {
		t.Fatalf("got key %q", key)
	}
}

func TestVerifyRejectsExpired(t *testing.T) {
	signer, _ := NewSigner("test-secret")
	token, _ := signer.Sign("derived/rec-001/frames/x.jpeg", time.Now().Add(-time.Second))
	if _, err := signer.Verify(token); !errors.Is(err, ErrTokenExpired) {
		t.Fatalf("got err %v, want ErrTokenExpired", err)
	}
}

func TestVerifyRejectsTampering(t *testing.T) {
	signer, _ := NewSigner("test-secret")
	token, _ := signer.Sign("derived/rec-001/frames/x.jpeg", time.Now().Add(time.Minute))
	tampered := token[:len(token)-1] + "A"
	if tampered == token {
		tampered = token[:len(token)-1] + "B"
	}
	if _, err := signer.Verify(tampered); err == nil {
		t.Fatalf("expected verification failure for tampered token")
	}
}

func TestVerifyRejectsOtherSecret(t *testing.T) {
	signer, _ := NewSigner("test-secret")
	other, _ := NewSigner("other-secret")
	token, _ := signer.Sign("derived/rec-001/frames/x.jpeg", time.Now().Add(time.Minute))
	if _, err := other.Verify(token); !errors.Is(err, ErrInvalidToken) {
		t.Fatalf("got err %v, want ErrInvalidToken", err)
	}
}

func TestVerifyRejectsMalformedToken(t *testing.T) {
	signer, _ := NewSigner("test-secret")
	if _, err := signer.Verify("not-base64url!!"); err == nil {
		t.Fatalf("expected error for malformed token")
	}
	if _, err := signer.Verify(""); err == nil {
		t.Fatalf("expected error for empty token")
	}
}

func TestNewSignerRequiresSecret(t *testing.T) {
	if _, err := NewSigner(""); err == nil {
		t.Fatalf("expected error for empty secret")
	}
	if _, err := NewSigner("   "); err == nil {
		t.Fatalf("expected error for whitespace-only secret")
	}
}

func TestSignRequiresKey(t *testing.T) {
	signer, _ := NewSigner("test-secret")
	if _, err := signer.Sign("", time.Now().Add(time.Minute)); err == nil {
		t.Fatalf("expected error for empty key")
	}
}

func TestKeyMayContainColon(t *testing.T) {
	signer, _ := NewSigner("test-secret")
	key := "derived/rec:001/frames/x.jpeg"
	token, err := signer.Sign(key, time.Now().Add(time.Minute))
	if err != nil {
		t.Fatalf("Sign: %v", err)
	}
	got, err := signer.Verify(token)
	if err != nil {
		t.Fatalf("Verify: %v", err)
	}
	if got != key {
		t.Fatalf("got %q, want %q", got, key)
	}
}

func TestVerifyRejectsShortToken(t *testing.T) {
	signer, _ := NewSigner("test-secret")
	if _, err := signer.Verify("YWJj"); err == nil { // base64url("abc"), shorter than sigSize
		t.Fatalf("expected error for short token")
	} else if !strings.Contains(err.Error(), "invalid token") {
		t.Fatalf("got %v", err)
	}
}
