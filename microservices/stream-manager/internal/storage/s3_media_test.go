// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package storage

import (
	"bytes"
	"context"
	"errors"
	"io"
	"sort"
	"strings"
	"testing"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	v4 "github.com/aws/aws-sdk-go-v2/aws/signer/v4"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/aws/aws-sdk-go-v2/service/s3/types"
	"github.com/aws/smithy-go"
)

// fakeS3 is an in-memory stand-in for the S3 API surface the store uses.
// It records every call so tests can assert on the exact bucket/key the
// store addressed, and it paginates ListObjectsV2 to exercise the
// continuation loop.
type fakeS3 struct {
	objects      map[string]fakeObject
	pageSize     int
	headBucket   error
	putCalls     []string
	deleteCalls  []string
	listPrefixes []string
	presignCalls []string
}

type fakeObject struct {
	body        []byte
	contentType string
	expires     *time.Time
}

func newFakeS3() *fakeS3 {
	return &fakeS3{objects: map[string]fakeObject{}, pageSize: 2}
}

func notFound(code string) error {
	return &smithy.GenericAPIError{Code: code, Message: code}
}

func (f *fakeS3) GetObject(_ context.Context, in *s3.GetObjectInput, _ ...func(*s3.Options)) (*s3.GetObjectOutput, error) {
	obj, ok := f.objects[aws.ToString(in.Key)]
	if !ok {
		return nil, notFound("NoSuchKey")
	}
	return &s3.GetObjectOutput{Body: io.NopCloser(bytes.NewReader(obj.body)), ContentType: aws.String(obj.contentType)}, nil
}

func (f *fakeS3) PutObject(_ context.Context, in *s3.PutObjectInput, _ ...func(*s3.Options)) (*s3.PutObjectOutput, error) {
	body, err := io.ReadAll(in.Body)
	if err != nil {
		return nil, err
	}
	key := aws.ToString(in.Key)
	f.putCalls = append(f.putCalls, key)
	f.objects[key] = fakeObject{body: body, contentType: aws.ToString(in.ContentType), expires: in.Expires}
	return &s3.PutObjectOutput{}, nil
}

func (f *fakeS3) HeadObject(_ context.Context, in *s3.HeadObjectInput, _ ...func(*s3.Options)) (*s3.HeadObjectOutput, error) {
	if _, ok := f.objects[aws.ToString(in.Key)]; !ok {
		return nil, notFound("NotFound")
	}
	return &s3.HeadObjectOutput{}, nil
}

func (f *fakeS3) HeadBucket(_ context.Context, _ *s3.HeadBucketInput, _ ...func(*s3.Options)) (*s3.HeadBucketOutput, error) {
	if f.headBucket != nil {
		return nil, f.headBucket
	}
	return &s3.HeadBucketOutput{}, nil
}

func (f *fakeS3) ListObjectsV2(_ context.Context, in *s3.ListObjectsV2Input, _ ...func(*s3.Options)) (*s3.ListObjectsV2Output, error) {
	prefix := aws.ToString(in.Prefix)
	f.listPrefixes = append(f.listPrefixes, prefix)

	var keys []string
	for k := range f.objects {
		if strings.HasPrefix(k, prefix) {
			keys = append(keys, k)
		}
	}
	sort.Strings(keys)

	start := 0
	if tok := aws.ToString(in.ContinuationToken); tok != "" {
		start = sort.SearchStrings(keys, tok)
	}
	end := start + f.pageSize
	if end > len(keys) {
		end = len(keys)
	}

	out := &s3.ListObjectsV2Output{IsTruncated: aws.Bool(end < len(keys))}
	for _, k := range keys[start:end] {
		out.Contents = append(out.Contents, types.Object{Key: aws.String(k)})
	}
	if end < len(keys) {
		out.NextContinuationToken = aws.String(keys[end])
	}
	return out, nil
}

func (f *fakeS3) DeleteObject(_ context.Context, in *s3.DeleteObjectInput, _ ...func(*s3.Options)) (*s3.DeleteObjectOutput, error) {
	key := aws.ToString(in.Key)
	f.deleteCalls = append(f.deleteCalls, key)
	delete(f.objects, key)
	return &s3.DeleteObjectOutput{}, nil
}

func (f *fakeS3) PresignGetObject(_ context.Context, in *s3.GetObjectInput, _ ...func(*s3.PresignOptions)) (*v4.PresignedHTTPRequest, error) {
	key := aws.ToString(in.Key)
	f.presignCalls = append(f.presignCalls, key)
	return &v4.PresignedHTTPRequest{URL: "http://s3.local/" + aws.ToString(in.Bucket) + "/" + key + "?X-Amz-Signature=fake"}, nil
}

func newFakeStore(t *testing.T, prefix string) (*S3MediaStore, *fakeS3) {
	t.Helper()
	store, err := NewS3MediaStore(context.Background(), S3Config{
		Endpoint:     "http://s3.local:8333",
		Bucket:       "media",
		Prefix:       prefix,
		UsePathStyle: true,
		AccessKey:    "test-access",
		SecretKey:    "test-secret",
	})
	if err != nil {
		t.Fatalf("new store: %v", err)
	}
	fake := newFakeS3()
	store.client = fake
	store.presign = fake
	return store, fake
}

func TestNewS3MediaStoreValidatesConfig(t *testing.T) {
	ctx := context.Background()
	base := S3Config{Endpoint: "http://s3.local", Bucket: "media", AccessKey: "a", SecretKey: "b"}

	cases := map[string]func(*S3Config){
		"missing endpoint":        func(c *S3Config) { c.Endpoint = "" },
		"missing bucket":          func(c *S3Config) { c.Bucket = "" },
		"half credentials":        func(c *S3Config) { c.SecretKey = "" },
		"absolute prefix uri":     func(c *S3Config) { c.Prefix = "s3://other/env" },
		"traversal prefix":        func(c *S3Config) { c.Prefix = "env/../other" },
		"backslash prefix":        func(c *S3Config) { c.Prefix = `env\other` },
		"empty segment in prefix": func(c *S3Config) { c.Prefix = "env//other" },
	}
	for name, mutate := range cases {
		cfg := base
		mutate(&cfg)
		if _, err := NewS3MediaStore(ctx, cfg); err == nil {
			t.Errorf("%s: expected error", name)
		}
	}

	store, err := NewS3MediaStore(ctx, S3Config{Endpoint: "http://s3.local", Bucket: "media", Prefix: "/dev/env/", AccessKey: "a", SecretKey: "b"})
	if err != nil {
		t.Fatalf("valid config rejected: %v", err)
	}
	if store.prefix != "dev/env" {
		t.Fatalf("prefix not normalised: %q", store.prefix)
	}
}

func TestSourceWritesLandUnderPrefixAndLayout(t *testing.T) {
	ctx := context.Background()
	store, fake := newFakeStore(t, "dev")

	mediaKey, err := store.PutRecording(ctx, "rec-001", strings.NewReader("mp4-bytes"), "")
	if err != nil {
		t.Fatal(err)
	}
	if mediaKey != "recordings/rec-001/media.mp4" {
		t.Fatalf("logical media key = %q", mediaKey)
	}
	sidecarKey, err := store.PutSidecar(ctx, "rec-001", strings.NewReader(`{"version":1}`))
	if err != nil {
		t.Fatal(err)
	}
	if sidecarKey != "recordings/rec-001/sidecar.json" {
		t.Fatalf("logical sidecar key = %q", sidecarKey)
	}

	if got := fake.objects["dev/recordings/rec-001/media.mp4"]; string(got.body) != "mp4-bytes" || got.contentType != "video/mp4" {
		t.Fatalf("media object not written under prefix with default content type: %+v", got)
	}
	if got := fake.objects["dev/recordings/rec-001/sidecar.json"]; got.contentType != "application/json" {
		t.Fatalf("sidecar object not written under prefix: %+v", got)
	}

	rc, err := store.OpenRecording(ctx, mediaKey)
	if err != nil {
		t.Fatal(err)
	}
	body, _ := io.ReadAll(rc)
	rc.Close()
	if string(body) != "mp4-bytes" {
		t.Fatalf("OpenRecording body = %q", body)
	}

	rc, err = store.OpenSidecar(ctx, "rec-001")
	if err != nil {
		t.Fatal(err)
	}
	rc.Close()

	if _, err := store.PutRecording(ctx, "../rec", strings.NewReader("x"), ""); !errors.Is(err, ErrInvalidIdentifier) {
		t.Fatalf("traversal id accepted: %v", err)
	}
}

func TestOpenRejectsKeysOutsideLayout(t *testing.T) {
	ctx := context.Background()
	store, fake := newFakeStore(t, "dev")
	fake.objects["dev/secrets.txt"] = fakeObject{body: []byte("nope")}
	fake.objects["other/recordings/rec-001/media.mp4"] = fakeObject{body: []byte("nope")}

	bad := []string{
		"secrets.txt",
		"/dev/secrets.txt",
		"../other/recordings/rec-001/media.mp4",
		"s3://media/recordings/rec-001/media.mp4",
		"http://evil/recordings/rec-001/media.mp4",
	}
	for _, key := range bad {
		if _, err := store.OpenRecording(ctx, key); !errors.Is(err, ErrInvalidObjectKey) {
			t.Errorf("OpenRecording(%q) = %v, want ErrInvalidObjectKey", key, err)
		}
	}
	if _, err := store.OpenRecording(ctx, "recordings/rec-404/media.mp4"); !errors.Is(err, ErrObjectNotFound) {
		t.Fatalf("missing object error = %v, want ErrObjectNotFound", err)
	}
}

func TestDerivedLifecycle(t *testing.T) {
	ctx := context.Background()
	store, fake := newFakeStore(t, "dev")
	key := "derived/rec-001/frames/20260921T000006-000000000.jpeg"

	exists, err := store.DerivedExists(ctx, key)
	if err != nil || exists {
		t.Fatalf("DerivedExists before put = %v, %v", exists, err)
	}

	before := time.Now().UTC()
	if err := store.PutDerived(ctx, key, strings.NewReader("jpeg"), "image/jpeg", 15*time.Minute); err != nil {
		t.Fatal(err)
	}
	obj := fake.objects["dev/"+key]
	if obj.contentType != "image/jpeg" || obj.expires == nil || obj.expires.Before(before.Add(14*time.Minute)) {
		t.Fatalf("derived object metadata wrong: %+v", obj)
	}

	exists, err = store.DerivedExists(ctx, key)
	if err != nil || !exists {
		t.Fatalf("DerivedExists after put = %v, %v", exists, err)
	}

	url, expiry, err := store.PresignDerived(ctx, key, 5*time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(url, "/media/dev/"+key) {
		t.Fatalf("presigned URL does not address prefixed key: %s", url)
	}
	if expiry.Before(before.Add(4*time.Minute)) || expiry.After(time.Now().UTC().Add(6*time.Minute)) {
		t.Fatalf("presign expiry %v not ~5m from now", expiry)
	}
	if _, _, err := store.PresignDerived(ctx, key, 0); err == nil {
		t.Fatal("non-positive presign expiry accepted")
	}

	rc, err := store.OpenDerived(ctx, key)
	if err != nil {
		t.Fatal(err)
	}
	rc.Close()
}

func TestDeleteRecordingObjectsPaginatesAndStaysInPrefix(t *testing.T) {
	ctx := context.Background()
	store, fake := newFakeStore(t, "dev")
	fake.pageSize = 2

	owned := []string{
		"dev/recordings/rec-001/media.mp4",
		"dev/recordings/rec-001/sidecar.json",
		"dev/derived/rec-001/frames/a.jpeg",
		"dev/derived/rec-001/frames/b.jpeg",
		"dev/derived/rec-001/clips/c.mp4",
	}
	untouched := []string{
		"dev/recordings/rec-0010/media.mp4",
		"dev/recordings/rec-002/media.mp4",
		"prod/recordings/rec-001/media.mp4",
	}
	for _, k := range append(owned, untouched...) {
		fake.objects[k] = fakeObject{body: []byte("x")}
	}

	if err := store.DeleteRecordingObjects(ctx, "rec-001"); err != nil {
		t.Fatal(err)
	}
	for _, k := range owned {
		if _, still := fake.objects[k]; still {
			t.Errorf("%s not deleted", k)
		}
	}
	for _, k := range untouched {
		if _, ok := fake.objects[k]; !ok {
			t.Errorf("%s wrongly deleted", k)
		}
	}
	// Two prefixes, each spanning more than one page.
	if len(fake.listPrefixes) < 3 {
		t.Fatalf("expected paginated listing, got prefixes %v", fake.listPrefixes)
	}
	for _, p := range fake.listPrefixes {
		if p != "dev/recordings/rec-001/" && p != "dev/derived/rec-001/" {
			t.Fatalf("listed outside recording prefixes: %q", p)
		}
	}
}

func TestHealthOnlyProbesBucket(t *testing.T) {
	ctx := context.Background()
	store, fake := newFakeStore(t, "")

	if err := store.Health(ctx); err != nil {
		t.Fatal(err)
	}
	fake.headBucket = notFound("NoSuchBucket")
	if err := store.Health(ctx); err == nil {
		t.Fatal("missing bucket reported healthy")
	}
	// The store must never have tried to create the bucket.
	if len(fake.putCalls) != 0 {
		t.Fatalf("unexpected writes during health: %v", fake.putCalls)
	}
}

func TestNoPrefixMapsKeysVerbatim(t *testing.T) {
	ctx := context.Background()
	store, fake := newFakeStore(t, "")
	if _, err := store.PutSidecar(ctx, "rec-001", strings.NewReader("{}")); err != nil {
		t.Fatal(err)
	}
	if _, ok := fake.objects["recordings/rec-001/sidecar.json"]; !ok {
		t.Fatalf("unprefixed key not written verbatim: %v", fake.putCalls)
	}
}
