// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package api

import (
	"bytes"
	"context"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/mediaaccess"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/replay"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/storage"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/storage/storagetest"
)

// mediaTestEnv wires a router backed by the filesystem MediaStore so
// GET /v1/media/{token} can be exercised end to end: sign a token for a
// derived object, fetch it, and confirm tampering/expiry are rejected.
type mediaTestEnv struct {
	router http.Handler
	media  storage.MediaStore
	signer *mediaaccess.Signer
}

func newMediaTestEnv(t *testing.T) mediaTestEnv {
	t.Helper()
	signer, err := mediaaccess.NewSigner("test-media-secret")
	if err != nil {
		t.Fatalf("NewSigner: %v", err)
	}
	fsMedia, err := storage.NewFileMediaStore(t.TempDir(), "http://stream-manager.test", signer)
	if err != nil {
		t.Fatalf("NewFileMediaStore: %v", err)
	}

	metadata := storagetest.NewMemoryMetadataStore()
	service := replay.NewRetrievalService(metadata, fsMedia, replay.Options{})
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	router := NewRouter(service, fsMedia, "test", logger, signer, nil, nil)

	return mediaTestEnv{router: router, media: fsMedia, signer: signer}
}

func (e mediaTestEnv) get(t *testing.T, path string) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(http.MethodGet, path, nil)
	rec := httptest.NewRecorder()
	e.router.ServeHTTP(rec, req)
	return rec
}

func TestGetMediaServesDerivedObjectForValidToken(t *testing.T) {
	env := newMediaTestEnv(t)
	key := "derived/rec-001/frames/x.jpeg"
	if err := env.media.PutDerived(context.Background(), key, bytes.NewReader([]byte("jpeg-bytes")), "image/jpeg", 0); err != nil {
		t.Fatalf("PutDerived: %v", err)
	}
	token, err := env.signer.Sign(key, time.Now().Add(time.Minute))
	if err != nil {
		t.Fatalf("Sign: %v", err)
	}

	rec := env.get(t, "/v1/media/"+token)
	if rec.Code != http.StatusOK {
		t.Fatalf("got status %d, body %s", rec.Code, rec.Body.String())
	}
	if rec.Body.String() != "jpeg-bytes" {
		t.Fatalf("got body %q", rec.Body.String())
	}
	if ct := rec.Header().Get("Content-Type"); ct != "image/jpeg" {
		t.Fatalf("got content type %q", ct)
	}
}

func TestGetMediaRejectsExpiredToken(t *testing.T) {
	env := newMediaTestEnv(t)
	key := "derived/rec-001/frames/x.jpeg"
	env.media.PutDerived(context.Background(), key, bytes.NewReader([]byte("x")), "image/jpeg", 0)
	token, _ := env.signer.Sign(key, time.Now().Add(-time.Second))

	rec := env.get(t, "/v1/media/"+token)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("got status %d", rec.Code)
	}
}

func TestGetMediaRejectsTamperedToken(t *testing.T) {
	env := newMediaTestEnv(t)
	key := "derived/rec-001/frames/x.jpeg"
	env.media.PutDerived(context.Background(), key, bytes.NewReader([]byte("x")), "image/jpeg", 0)
	token, _ := env.signer.Sign(key, time.Now().Add(time.Minute))
	tampered := token[:len(token)-1] + "x"
	if tampered == token {
		tampered = token[:len(token)-1] + "y"
	}

	rec := env.get(t, "/v1/media/"+tampered)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("got status %d", rec.Code)
	}
}

func TestGetMediaRejectsNonDerivedKey(t *testing.T) {
	env := newMediaTestEnv(t)
	// Sign a token over a source recording key rather than a derived one;
	// the route must never resolve a source object.
	token, err := env.signer.Sign("recordings/rec-001/media.ts", time.Now().Add(time.Minute))
	if err != nil {
		t.Fatalf("Sign: %v", err)
	}

	rec := env.get(t, "/v1/media/"+token)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("got status %d", rec.Code)
	}
}

func TestGetMediaWithoutSignerAlwaysRejects(t *testing.T) {
	fsMedia, err := storage.NewFileMediaStore(t.TempDir(), "http://stream-manager.test", &mediaaccess.Signer{})
	if err != nil {
		t.Fatalf("NewFileMediaStore: %v", err)
	}
	metadata := storagetest.NewMemoryMetadataStore()
	service := replay.NewRetrievalService(metadata, fsMedia, replay.Options{})
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	router := NewRouter(service, fsMedia, "test", logger, nil, nil, nil)

	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/v1/media/anything", nil))
	if rec.Code != http.StatusNotFound {
		t.Fatalf("got status %d", rec.Code)
	}
}
