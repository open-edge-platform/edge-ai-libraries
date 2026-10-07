// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package handler

import (
	"errors"
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/mediaaccess"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/model"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/storage"
)

// derivedKeyPrefix is the only logical key namespace GET /v1/media/{token}
// may resolve. A token is a capability over one derived object; it must
// never be usable to reach a source recording or sidecar.
const derivedKeyPrefix = "derived/"

// tokenVerifier decodes and validates a GET /v1/media/{token} capability
// token. *mediaaccess.Signer implements it.
type tokenVerifier interface {
	Verify(token string) (key string, err error)
}

// MediaHandler serves GET /v1/media/{token}: it verifies a signed,
// expiring capability token and streams the derived object it authorizes,
// without ever exposing the underlying storage path to the caller.
type MediaHandler struct {
	media  storage.MediaStore
	verify tokenVerifier
}

// NewMediaHandler builds a MediaHandler. verify may be nil, in which case
// every request is rejected: this lets the route be mounted unconditionally
// when media-token signing is not configured, rather than making the route's
// presence itself a signal of which backend is active.
func NewMediaHandler(media storage.MediaStore, verify *mediaaccess.Signer) *MediaHandler {
	h := &MediaHandler{media: media}
	if verify != nil {
		h.verify = verify
	}
	return h
}

// GetMedia handles GET /v1/media/:token.
func (h *MediaHandler) GetMedia(c *gin.Context) {
	token := c.Param("token")
	if strings.TrimSpace(token) == "" || h.verify == nil {
		h.writeNotFound(c)
		return
	}

	key, err := h.verify.Verify(token)
	if err != nil {
		// Every verification failure — malformed, tampered, wrong
		// secret, or expired — is reported identically so a client
		// cannot learn which condition applies (e.g. whether a
		// tampered token merely expired).
		if !errors.Is(err, mediaaccess.ErrInvalidToken) && !errors.Is(err, mediaaccess.ErrTokenExpired) {
			_ = c.Error(err)
		}
		h.writeNotFound(c)
		return
	}

	if !strings.HasPrefix(key, derivedKeyPrefix) {
		h.writeNotFound(c)
		return
	}
	if err := storage.ValidateObjectKey(key); err != nil {
		h.writeNotFound(c)
		return
	}

	reader, err := h.media.OpenDerived(c.Request.Context(), key)
	if err != nil {
		h.writeNotFound(c)
		return
	}
	defer reader.Close()

	c.Header("Cache-Control", "private, no-store")
	c.DataFromReader(http.StatusOK, -1, storage.InferredDerivedContentType(key), reader, nil)
}

func (h *MediaHandler) writeNotFound(c *gin.Context) {
	c.JSON(http.StatusNotFound, model.ErrorResponse{
		Status:       http.StatusNotFound,
		ErrorCode:    "media_not_found",
		ErrorDetails: "media not found",
	})
}
