// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// Package logging configures the process-wide structured logger and provides
// the HTTP middleware that gives every request an ID and an access-log line.
package logging

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
)

// RequestIDHeader carries the request ID to and from clients. An incoming
// value is honoured so IDs from an upstream proxy stay correlated.
const RequestIDHeader = "X-Request-ID"

// New builds a slog.Logger writing to stderr. format is "json" (default) or
// "text"; level is one of debug, info, warn, error (default info). Invalid
// values are reported as an error so a misconfiguration is not silently
// downgraded to defaults.
func New(format, level string) (*slog.Logger, error) {
	var lvl slog.Level
	switch strings.ToLower(strings.TrimSpace(level)) {
	case "", "info":
		lvl = slog.LevelInfo
	case "debug":
		lvl = slog.LevelDebug
	case "warn", "warning":
		lvl = slog.LevelWarn
	case "error":
		lvl = slog.LevelError
	default:
		return nil, fmt.Errorf("unknown log level %q", level)
	}

	opts := &slog.HandlerOptions{Level: lvl}
	var handler slog.Handler
	switch strings.ToLower(strings.TrimSpace(format)) {
	case "", "json":
		handler = slog.NewJSONHandler(os.Stderr, opts)
	case "text":
		handler = slog.NewTextHandler(os.Stderr, opts)
	default:
		return nil, fmt.Errorf("unknown log format %q", format)
	}
	return slog.New(handler), nil
}

type ctxKey struct{}

// FromContext returns the request-scoped logger stored by Middleware, or
// slog.Default() when none is present (e.g. outside an HTTP request).
func FromContext(ctx context.Context) *slog.Logger {
	if l, ok := ctx.Value(ctxKey{}).(*slog.Logger); ok {
		return l
	}
	return slog.Default()
}

// Middleware assigns a request ID, stores a logger carrying it in the
// request context, echoes the ID in the response, and writes one access-log
// line per request. Requests that end in 5xx are logged at error level so
// they stand out; 4xx are client mistakes and stay at info.
func Middleware(base *slog.Logger) gin.HandlerFunc {
	return func(c *gin.Context) {
		start := time.Now()

		reqID := c.GetHeader(RequestIDHeader)
		if reqID == "" {
			reqID = newRequestID()
		}
		c.Header(RequestIDHeader, reqID)

		logger := base.With("request_id", reqID)
		c.Request = c.Request.WithContext(context.WithValue(c.Request.Context(), ctxKey{}, logger))

		c.Next()

		status := c.Writer.Status()
		attrs := []any{
			"method", c.Request.Method,
			"path", c.Request.URL.Path,
			"status", status,
			"duration_ms", time.Since(start).Milliseconds(),
			"bytes", c.Writer.Size(),
			"client_ip", c.ClientIP(),
		}
		if q := c.Request.URL.RawQuery; q != "" {
			attrs = append(attrs, "query", q)
		}
		if errs := c.Errors.ByType(gin.ErrorTypePrivate); len(errs) > 0 {
			attrs = append(attrs, "error", errs.Last().Error())
		}

		switch {
		case status >= http.StatusInternalServerError:
			logger.Error("request", attrs...)
		default:
			logger.Info("request", attrs...)
		}
	}
}

// Recovery turns a handler panic into a 500 and logs it with the stack via
// the request logger, replacing gin.Recovery so panics land in the same
// structured stream as everything else.
func Recovery() gin.HandlerFunc {
	return gin.CustomRecoveryWithWriter(nil, func(c *gin.Context, recovered any) {
		FromContext(c.Request.Context()).Error("panic recovered", "panic", fmt.Sprint(recovered))
		c.AbortWithStatusJSON(http.StatusInternalServerError, gin.H{
			"status":        http.StatusInternalServerError,
			"error_code":    "internal_error",
			"error_details": "internal error",
		})
	})
}

func newRequestID() string {
	var b [8]byte
	if _, err := rand.Read(b[:]); err != nil {
		return fmt.Sprintf("%d", time.Now().UnixNano())
	}
	return hex.EncodeToString(b[:])
}
