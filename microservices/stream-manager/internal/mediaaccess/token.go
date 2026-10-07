// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// Package mediaaccess issues and verifies short-lived capability tokens for
// GET /v1/media/{token}. A token lets a client fetch one specific derived
// object directly from Stream Manager without ever seeing the underlying
// storage path (filesystem or otherwise). It never carries the raw
// filesystem path or a storage credential.
package mediaaccess

import (
	"crypto/hmac"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/base64"
	"errors"
	"fmt"
	"strconv"
	"strings"
	"time"
)

// sigSize is the byte length of an HMAC-SHA256 signature.
const sigSize = sha256.Size

var (
	// ErrInvalidToken reports a token that is malformed, has an
	// unrecognised signature, or has been tampered with. Callers must not
	// distinguish this from ErrTokenExpired in any response they return to
	// a client, so a token's validity window is never revealed.
	ErrInvalidToken = errors.New("mediaaccess: invalid token")
	// ErrTokenExpired reports a token whose signature verifies but whose
	// expiry has passed.
	ErrTokenExpired = errors.New("mediaaccess: token expired")
)

// Signer issues and verifies capability tokens for derived media keys.
// Tokens are opaque, self-contained, and require no server-side state: the
// signed payload carries the logical derived key and an expiry, and the
// signature proves neither was altered after issuance.
type Signer struct {
	secret []byte
}

// NewSigner builds a Signer from a shared secret. The secret must be
// non-empty; callers should source it from an environment variable or a
// secret-management mechanism, never a literal in code or configuration
// checked into source control.
func NewSigner(secret string) (*Signer, error) {
	if strings.TrimSpace(secret) == "" {
		return nil, errors.New("mediaaccess: secret is required")
	}
	return &Signer{secret: []byte(secret)}, nil
}

// Sign issues a token for key that is valid until expiresAt. key is a
// logical derived-object key (see internal/storage/keys.go); it is never
// interpreted as a filesystem path by this package.
func (s *Signer) Sign(key string, expiresAt time.Time) (string, error) {
	if strings.TrimSpace(key) == "" {
		return "", errors.New("mediaaccess: key is required")
	}
	payload := encodePayload(key, expiresAt.UTC().Unix())
	sig := s.sign(payload)

	raw := make([]byte, 0, len(payload)+len(sig))
	raw = append(raw, payload...)
	raw = append(raw, sig...)
	return base64.RawURLEncoding.EncodeToString(raw), nil
}

// Verify checks a token's signature and expiry and returns the logical
// derived key it authorizes. Every failure — malformed encoding, a bad
// signature, or an expired token — is reported without revealing which
// condition applies, other than distinguishing "expired" (ErrTokenExpired)
// from "invalid" (ErrInvalidToken) so callers may choose to log
// differently; both must still map to the same generic HTTP response.
func (s *Signer) Verify(token string) (string, error) {
	raw, err := base64.RawURLEncoding.DecodeString(token)
	if err != nil {
		return "", fmt.Errorf("%w: %v", ErrInvalidToken, err)
	}
	if len(raw) <= sigSize {
		return "", fmt.Errorf("%w: too short", ErrInvalidToken)
	}

	payload := raw[:len(raw)-sigSize]
	sig := raw[len(raw)-sigSize:]
	expectedSig := s.sign(payload)
	if subtle.ConstantTimeCompare(sig, expectedSig) != 1 {
		return "", fmt.Errorf("%w: signature mismatch", ErrInvalidToken)
	}

	key, expiresUnix, err := decodePayload(payload)
	if err != nil {
		return "", fmt.Errorf("%w: %v", ErrInvalidToken, err)
	}
	if time.Now().UTC().Unix() > expiresUnix {
		return "", ErrTokenExpired
	}
	return key, nil
}

func (s *Signer) sign(payload []byte) []byte {
	mac := hmac.New(sha256.New, s.secret)
	mac.Write(payload)
	return mac.Sum(nil)
}

// encodePayload renders key and an expiry as "<unix-seconds>:<key>". The
// expiry is an integer prefix followed by a delimiter that cannot appear in
// it, so the key (which may itself contain ':') is recovered unambiguously
// by splitting once from the left.
func encodePayload(key string, expiresUnix int64) []byte {
	return []byte(strconv.FormatInt(expiresUnix, 10) + ":" + key)
}

func decodePayload(payload []byte) (key string, expiresUnix int64, err error) {
	s := string(payload)
	idx := strings.IndexByte(s, ':')
	if idx < 0 {
		return "", 0, errors.New("malformed payload")
	}
	expiresUnix, err = strconv.ParseInt(s[:idx], 10, 64)
	if err != nil {
		return "", 0, fmt.Errorf("malformed expiry: %w", err)
	}
	key = s[idx+1:]
	if key == "" {
		return "", 0, errors.New("empty key")
	}
	return key, expiresUnix, nil
}
