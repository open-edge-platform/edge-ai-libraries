// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// Package storagetest provides in-memory implementations of the storage
// seams for unit tests that must not depend on an object store or a
// database. It is imported only from _test files.
package storagetest

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"strings"
	"sync"
	"time"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/model"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/storage"
)

// MemoryMediaStore is an in-memory storage.MediaStore. Objects are keyed by
// their logical key exactly as the production store would address them
// (minus any bucket prefix). Error fields, when set, make the corresponding
// operation fail so callers' error mapping can be exercised.
type MemoryMediaStore struct {
	mu          sync.Mutex
	objects     map[string][]byte
	contentType map[string]string

	OpenErr    error
	PutErr     error
	PresignErr error
	// PutCalls records every derived key written, in order.
	PutCalls []string
}

var _ storage.MediaStore = (*MemoryMediaStore)(nil)

func NewMemoryMediaStore() *MemoryMediaStore {
	return &MemoryMediaStore{objects: map[string][]byte{}, contentType: map[string]string{}}
}

// Set stores body at key without any validation, so tests can stage
// arbitrary (including deliberately broken) objects.
func (m *MemoryMediaStore) Set(key string, body []byte) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.objects[key] = body
}

// Delete removes key if present.
func (m *MemoryMediaStore) Delete(key string) {
	m.mu.Lock()
	defer m.mu.Unlock()
	delete(m.objects, key)
}

// Get returns the stored body for key and whether it exists.
func (m *MemoryMediaStore) Get(key string) ([]byte, bool) {
	m.mu.Lock()
	defer m.mu.Unlock()
	body, ok := m.objects[key]
	return body, ok
}

// ContentType returns the content type recorded for a derived key.
func (m *MemoryMediaStore) ContentType(key string) string {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.contentType[key]
}

func (m *MemoryMediaStore) open(key string) (io.ReadCloser, error) {
	if m.OpenErr != nil {
		return nil, m.OpenErr
	}
	body, ok := m.Get(key)
	if !ok {
		return nil, fmt.Errorf("%w: %s", storage.ErrObjectNotFound, key)
	}
	return io.NopCloser(bytes.NewReader(body)), nil
}

func (m *MemoryMediaStore) OpenRecording(_ context.Context, recordingPath string) (io.ReadCloser, error) {
	return m.open(recordingPath)
}

func (m *MemoryMediaStore) OpenSidecar(_ context.Context, recordingID string) (io.ReadCloser, error) {
	key, err := storage.RecordingSidecarKey(recordingID)
	if err != nil {
		return nil, err
	}
	return m.open(key)
}

func (m *MemoryMediaStore) OpenSidecarForRecording(_ context.Context, recordingID, recordingPath string) (io.ReadCloser, error) {
	key, err := storage.RecordingSidecarKeyForPath(recordingID, recordingPath)
	if err != nil {
		return nil, err
	}
	return m.open(key)
}

func (m *MemoryMediaStore) OpenDerived(_ context.Context, key string) (io.ReadCloser, error) {
	return m.open(key)
}

func (m *MemoryMediaStore) PutRecording(_ context.Context, recordingID string, media io.Reader, _ string) (string, error) {
	key, err := storage.RecordingMediaKey(recordingID)
	if err != nil {
		return "", err
	}
	body, err := io.ReadAll(media)
	if err != nil {
		return "", err
	}
	m.Set(key, body)
	return key, nil
}

func (m *MemoryMediaStore) PutSidecar(_ context.Context, recordingID string, sidecar io.Reader) (string, error) {
	key, err := storage.RecordingSidecarKey(recordingID)
	if err != nil {
		return "", err
	}
	body, err := io.ReadAll(sidecar)
	if err != nil {
		return "", err
	}
	m.Set(key, body)
	return key, nil
}

func (m *MemoryMediaStore) PutDerived(_ context.Context, key string, media io.Reader, contentType string, _ time.Duration) error {
	if m.PutErr != nil {
		return m.PutErr
	}
	body, err := io.ReadAll(media)
	if err != nil {
		return err
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	m.objects[key] = body
	m.contentType[key] = contentType
	m.PutCalls = append(m.PutCalls, key)
	return nil
}

func (m *MemoryMediaStore) DerivedExists(_ context.Context, key string) (bool, error) {
	_, ok := m.Get(key)
	return ok, nil
}

func (m *MemoryMediaStore) PresignDerived(_ context.Context, key string, expiresIn time.Duration) (string, time.Time, error) {
	if m.PresignErr != nil {
		return "", time.Time{}, m.PresignErr
	}
	return "http://media.test/" + key + "?X-Amz-Signature=test", time.Now().UTC().Add(expiresIn), nil
}

func (m *MemoryMediaStore) DeleteRecordingObjects(_ context.Context, recordingID string) error {
	prefixes, err := storage.RecordingObjectPrefixes(recordingID)
	if err != nil {
		return err
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	for key := range m.objects {
		for _, p := range prefixes {
			if strings.HasPrefix(key, p) {
				delete(m.objects, key)
				delete(m.contentType, key)
			}
		}
	}
	return nil
}

func (m *MemoryMediaStore) Health(context.Context) error { return nil }

// MemoryMetadataStore is an in-memory storage.RecordingMetadataStore that
// also satisfies the development seeder's writer interface.
type MemoryMetadataStore struct {
	mu         sync.Mutex
	recordings map[string]model.Recording
}

var _ storage.RecordingMetadataStore = (*MemoryMetadataStore)(nil)

func NewMemoryMetadataStore(recordings ...model.Recording) *MemoryMetadataStore {
	s := &MemoryMetadataStore{recordings: map[string]model.Recording{}}
	for _, r := range recordings {
		s.recordings[r.RecordingID] = r
	}
	return s
}

func (s *MemoryMetadataStore) Save(_ context.Context, recording model.Recording) error {
	if err := storage.ValidateIdentifier("recording_id", recording.RecordingID); err != nil {
		return err
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	s.recordings[recording.RecordingID] = recording
	return nil
}

func (s *MemoryMetadataStore) GetByID(_ context.Context, recordingID string) (model.Recording, error) {
	if err := storage.ValidateIdentifier("recording_id", recordingID); err != nil {
		return model.Recording{}, err
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	r, ok := s.recordings[recordingID]
	if !ok {
		return model.Recording{}, fmt.Errorf("%w: %q", storage.ErrRecordingNotFound, recordingID)
	}
	return r, nil
}

func (s *MemoryMetadataStore) Exists(_ context.Context, recordingID string) (bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	_, ok := s.recordings[recordingID]
	return ok, nil
}
