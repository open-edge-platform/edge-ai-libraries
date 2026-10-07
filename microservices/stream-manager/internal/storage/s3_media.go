// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package storage

import (
	"context"
	"errors"
	"fmt"
	"io"
	"path"
	"strings"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	v4 "github.com/aws/aws-sdk-go-v2/aws/signer/v4"
	awsconfig "github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/credentials"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/aws/smithy-go"
)

// ErrObjectNotFound reports that a requested object is absent from the
// bucket.
var ErrObjectNotFound = errors.New("object not found")

// s3API is the subset of the S3 client surface this store uses. Depending on
// the interface rather than *s3.Client keeps the store unit-testable against
// a fake without a live endpoint.
type s3API interface {
	GetObject(ctx context.Context, params *s3.GetObjectInput, optFns ...func(*s3.Options)) (*s3.GetObjectOutput, error)
	PutObject(ctx context.Context, params *s3.PutObjectInput, optFns ...func(*s3.Options)) (*s3.PutObjectOutput, error)
	HeadObject(ctx context.Context, params *s3.HeadObjectInput, optFns ...func(*s3.Options)) (*s3.HeadObjectOutput, error)
	HeadBucket(ctx context.Context, params *s3.HeadBucketInput, optFns ...func(*s3.Options)) (*s3.HeadBucketOutput, error)
	ListObjectsV2(ctx context.Context, params *s3.ListObjectsV2Input, optFns ...func(*s3.Options)) (*s3.ListObjectsV2Output, error)
	DeleteObject(ctx context.Context, params *s3.DeleteObjectInput, optFns ...func(*s3.Options)) (*s3.DeleteObjectOutput, error)
}

// s3Presigner issues presigned GET URLs for derived objects.
type s3Presigner interface {
	PresignGetObject(ctx context.Context, params *s3.GetObjectInput, optFns ...func(*s3.PresignOptions)) (*v4.PresignedHTTPRequest, error)
}

// S3Config holds the connection details for an S3-compatible object store.
//
// SeaweedFS's S3 gateway is the only backend certified so far. Its profile
// is: an explicit endpoint URL, path-style addressing, a configured (but
// semantically unused) region, and gateway credentials. The configuration
// and code are deliberately vendor-neutral so qualifying another backend
// later does not require an interface change.
type S3Config struct {
	// Endpoint is the S3 service base URL, e.g. "http://localhost:8333".
	Endpoint string
	// Region is required by the S3 API surface. SeaweedFS ignores it, but
	// it participates in request signing and so must match on both sides.
	Region string
	// Bucket is the single, pre-existing bucket holding every recording,
	// sidecar, and derived object. The service never creates it.
	Bucket string
	// Prefix optionally confines every object this store touches to one
	// key namespace inside the bucket, so several environments can share a
	// bucket without being able to read or delete each other's objects.
	Prefix string
	// UsePathStyle selects /{bucket}/{key} addressing instead of
	// {bucket}.{host}/{key}. SeaweedFS's gateway requires it.
	UsePathStyle bool
	// AccessKey, SecretKey, and SessionToken authenticate against the
	// endpoint. When AccessKey and SecretKey are both empty, the AWS
	// default credential provider chain is used instead.
	AccessKey    string
	SecretKey    string
	SessionToken string
}

// S3MediaStore is the production MediaStore implementation, backed by any
// S3-compatible object store. It depends only on the S3 protocol, never on a
// vendor SDK.
//
// The store requires the bucket to already exist and never attempts bucket
// administration. The identity it runs as needs only object-level rights
// within the configured prefix: GetObject, PutObject, DeleteObject, and
// ListBucket constrained to that prefix.
type S3MediaStore struct {
	client  s3API
	presign s3Presigner
	bucket  string
	prefix  string
}

// NewS3MediaStore builds an S3MediaStore from cfg. It does not verify
// connectivity; call Health to confirm the bucket is reachable.
func NewS3MediaStore(ctx context.Context, cfg S3Config) (*S3MediaStore, error) {
	if strings.TrimSpace(cfg.Endpoint) == "" {
		return nil, errors.New("s3: endpoint is required")
	}
	if strings.TrimSpace(cfg.Bucket) == "" {
		return nil, errors.New("s3: bucket is required")
	}
	if strings.TrimSpace(cfg.Region) == "" {
		cfg.Region = "us-east-1"
	}

	prefix, err := normalizePrefix(cfg.Prefix)
	if err != nil {
		return nil, err
	}

	awsCfg, err := resolveAWSConfig(ctx, cfg)
	if err != nil {
		return nil, err
	}

	client := s3.NewFromConfig(awsCfg, func(o *s3.Options) {
		o.BaseEndpoint = aws.String(cfg.Endpoint)
		o.UsePathStyle = cfg.UsePathStyle
	})

	return &S3MediaStore{
		client:  client,
		presign: s3.NewPresignClient(client),
		bucket:  cfg.Bucket,
		prefix:  prefix,
	}, nil
}

// resolveAWSConfig prefers explicitly configured static credentials and
// otherwise falls back to the AWS default provider chain, so an environment
// that supplies credentials out of band (instance role, shared config,
// injected environment) works without a code change.
func resolveAWSConfig(ctx context.Context, cfg S3Config) (aws.Config, error) {
	if cfg.AccessKey != "" && cfg.SecretKey != "" {
		return aws.Config{
			Region:      cfg.Region,
			Credentials: credentials.NewStaticCredentialsProvider(cfg.AccessKey, cfg.SecretKey, cfg.SessionToken),
		}, nil
	}
	if cfg.AccessKey != "" || cfg.SecretKey != "" {
		return aws.Config{}, errors.New("s3: access key and secret key must be set together")
	}

	awsCfg, err := awsconfig.LoadDefaultConfig(ctx, awsconfig.WithRegion(cfg.Region))
	if err != nil {
		return aws.Config{}, fmt.Errorf("s3: load default credentials: %w", err)
	}
	return awsCfg, nil
}

func normalizePrefix(prefix string) (string, error) {
	trimmed := strings.Trim(strings.TrimSpace(prefix), "/")
	if trimmed == "" {
		return "", nil
	}
	if strings.Contains(trimmed, "://") || strings.Contains(trimmed, `\`) {
		return "", fmt.Errorf("%w: prefix %q is not a relative key namespace", ErrInvalidObjectKey, prefix)
	}
	if cleaned := path.Clean(trimmed); cleaned != trimmed {
		return "", fmt.Errorf("%w: prefix %q is not in canonical form", ErrInvalidObjectKey, prefix)
	}
	for _, segment := range strings.Split(trimmed, "/") {
		if segment == "" || segment == "." || segment == ".." {
			return "", fmt.Errorf("%w: prefix %q contains an empty or traversal segment", ErrInvalidObjectKey, prefix)
		}
	}
	return trimmed, nil
}

// objectKey validates a logical key and maps it into the configured prefix.
// Every read, write, and delete goes through here, so no operation can
// address an object outside the store's namespace.
func (s *S3MediaStore) objectKey(logicalKey string) (string, error) {
	if err := ValidateObjectKey(logicalKey); err != nil {
		return "", err
	}
	if s.prefix == "" {
		return logicalKey, nil
	}
	return s.prefix + "/" + logicalKey, nil
}

func (s *S3MediaStore) prefixedPrefix(logicalPrefix string) string {
	if s.prefix == "" {
		return logicalPrefix
	}
	return s.prefix + "/" + logicalPrefix
}

func (s *S3MediaStore) OpenRecording(ctx context.Context, recordingPath string) (io.ReadCloser, error) {
	return s.openObject(ctx, recordingPath)
}

func (s *S3MediaStore) OpenSidecar(ctx context.Context, recordingID string) (io.ReadCloser, error) {
	key, err := RecordingSidecarKey(recordingID)
	if err != nil {
		return nil, err
	}
	return s.openObject(ctx, key)
}

func (s *S3MediaStore) OpenDerived(ctx context.Context, key string) (io.ReadCloser, error) {
	return s.openObject(ctx, key)
}

func (s *S3MediaStore) openObject(ctx context.Context, logicalKey string) (io.ReadCloser, error) {
	key, err := s.objectKey(logicalKey)
	if err != nil {
		return nil, err
	}

	out, err := s.client.GetObject(ctx, &s3.GetObjectInput{
		Bucket: aws.String(s.bucket),
		Key:    aws.String(key),
	})
	if err != nil {
		if isNotFound(err) {
			return nil, fmt.Errorf("%w: %s", ErrObjectNotFound, logicalKey)
		}
		return nil, fmt.Errorf("get object %q: %w", logicalKey, err)
	}
	return out.Body, nil
}

func (s *S3MediaStore) PutRecording(ctx context.Context, recordingID string, media io.Reader, contentType string) (string, error) {
	logicalKey, err := RecordingMediaKey(recordingID)
	if err != nil {
		return "", err
	}
	if contentType == "" {
		contentType = "video/mp4"
	}
	if err := s.putObject(ctx, logicalKey, media, contentType, nil); err != nil {
		return "", err
	}
	return logicalKey, nil
}

func (s *S3MediaStore) PutSidecar(ctx context.Context, recordingID string, sidecar io.Reader) (string, error) {
	logicalKey, err := RecordingSidecarKey(recordingID)
	if err != nil {
		return "", err
	}
	if err := s.putObject(ctx, logicalKey, sidecar, "application/json", nil); err != nil {
		return "", err
	}
	return logicalKey, nil
}

func (s *S3MediaStore) PutDerived(ctx context.Context, key string, media io.Reader, contentType string, ttl time.Duration) error {
	var expires *time.Time
	if ttl > 0 {
		at := time.Now().UTC().Add(ttl)
		expires = &at
	}
	return s.putObject(ctx, key, media, contentType, expires)
}

func (s *S3MediaStore) putObject(ctx context.Context, logicalKey string, body io.Reader, contentType string, expires *time.Time) error {
	key, err := s.objectKey(logicalKey)
	if err != nil {
		return err
	}

	input := &s3.PutObjectInput{
		Bucket:      aws.String(s.bucket),
		Key:         aws.String(key),
		Body:        body,
		ContentType: aws.String(contentType),
	}
	if expires != nil {
		input.Expires = aws.Time(*expires)
	}

	if _, err := s.client.PutObject(ctx, input); err != nil {
		return fmt.Errorf("put object %q: %w", logicalKey, err)
	}
	return nil
}

func (s *S3MediaStore) DerivedExists(ctx context.Context, logicalKey string) (bool, error) {
	key, err := s.objectKey(logicalKey)
	if err != nil {
		return false, err
	}

	_, err = s.client.HeadObject(ctx, &s3.HeadObjectInput{
		Bucket: aws.String(s.bucket),
		Key:    aws.String(key),
	})
	if err == nil {
		return true, nil
	}
	if isNotFound(err) {
		return false, nil
	}
	return false, fmt.Errorf("head object %q: %w", logicalKey, err)
}

func (s *S3MediaStore) PresignDerived(ctx context.Context, logicalKey string, expiresIn time.Duration) (string, time.Time, error) {
	key, err := s.objectKey(logicalKey)
	if err != nil {
		return "", time.Time{}, err
	}
	if expiresIn <= 0 {
		return "", time.Time{}, fmt.Errorf("presign object %q: expiry must be positive", logicalKey)
	}

	req, err := s.presign.PresignGetObject(ctx, &s3.GetObjectInput{
		Bucket: aws.String(s.bucket),
		Key:    aws.String(key),
	}, s3.WithPresignExpires(expiresIn))
	if err != nil {
		return "", time.Time{}, fmt.Errorf("presign object %q: %w", logicalKey, err)
	}
	return req.URL, time.Now().UTC().Add(expiresIn), nil
}

// DeleteRecordingObjects removes the recording, sidecar, and every derived
// object for recordingID.
func (s *S3MediaStore) DeleteRecordingObjects(ctx context.Context, recordingID string) error {
	prefixes, err := RecordingObjectPrefixes(recordingID)
	if err != nil {
		return err
	}

	for _, logicalPrefix := range prefixes {
		if err := s.deleteByPrefix(ctx, logicalPrefix); err != nil {
			return err
		}
	}
	return nil
}

func (s *S3MediaStore) deleteByPrefix(ctx context.Context, logicalPrefix string) error {
	prefix := s.prefixedPrefix(logicalPrefix)

	var continuationToken *string
	for {
		out, err := s.client.ListObjectsV2(ctx, &s3.ListObjectsV2Input{
			Bucket:            aws.String(s.bucket),
			Prefix:            aws.String(prefix),
			ContinuationToken: continuationToken,
		})
		if err != nil {
			return fmt.Errorf("list objects under %q: %w", logicalPrefix, err)
		}

		for _, obj := range out.Contents {
			// Guard against a backend returning keys outside the
			// requested prefix: a delete must never reach another
			// namespace's objects.
			if !strings.HasPrefix(aws.ToString(obj.Key), prefix) {
				continue
			}
			if _, err := s.client.DeleteObject(ctx, &s3.DeleteObjectInput{
				Bucket: aws.String(s.bucket),
				Key:    obj.Key,
			}); err != nil {
				return fmt.Errorf("delete object %q: %w", aws.ToString(obj.Key), err)
			}
		}

		if out.IsTruncated == nil || !*out.IsTruncated || out.NextContinuationToken == nil {
			return nil
		}
		continuationToken = out.NextContinuationToken
	}
}

// Health confirms the configured bucket is reachable. It never creates the
// bucket: provisioning is a deployment responsibility.
func (s *S3MediaStore) Health(ctx context.Context) error {
	if _, err := s.client.HeadBucket(ctx, &s3.HeadBucketInput{Bucket: aws.String(s.bucket)}); err != nil {
		return fmt.Errorf("s3 bucket %q unreachable: %w", s.bucket, err)
	}
	return nil
}

// isNotFound reports whether err represents an S3 "no such key/bucket"
// response, across the several distinct error shapes the SDK can surface for
// GetObject/HeadObject on different S3-compatible backends.
func isNotFound(err error) bool {
	var apiErr smithy.APIError
	if errors.As(err, &apiErr) {
		switch apiErr.ErrorCode() {
		case "NoSuchKey", "NotFound", "NoSuchBucket":
			return true
		}
	}
	return strings.Contains(err.Error(), "StatusCode: 404")
}
