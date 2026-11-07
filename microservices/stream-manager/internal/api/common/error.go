// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package common

import (
	"net/http"

	"github.com/gin-gonic/gin"
)

// StreamManError is the JSON envelope for every business-logic API failure.
type StreamManError struct {
	Status      int    `json:"status"`
	ErrorCode   string `json:"error_code"`
	ErrorDetail string `json:"error_detail"`
}

func (e StreamManError) Error() string { return e.ErrorDetail }

// WriteError aborts the request with a StreamManError JSON body.
func WriteError(c *gin.Context, status int, code, detail string) {
	c.AbortWithStatusJSON(status, StreamManError{Status: status, ErrorCode: code, ErrorDetail: detail})
}

func WriteInternalError(c *gin.Context) {
	WriteError(c, http.StatusInternalServerError, "internal_error", "internal error")
}
