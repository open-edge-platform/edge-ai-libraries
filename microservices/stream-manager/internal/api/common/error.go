// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package common

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"

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

func jsonError(err error) error {
	var typeErr *json.UnmarshalTypeError
	var maxErr *http.MaxBytesError
	switch {
	case errors.As(err, &typeErr) && typeErr.Field != "":
		return fmt.Errorf("%s has the wrong type", typeErr.Field)
	case errors.As(err, &maxErr):
		return fmt.Errorf("request body must be at most %d bytes", maxErr.Limit)
	case strings.HasPrefix(err.Error(), "json: unknown field "):
		return fmt.Errorf("unknown field %s", strings.TrimPrefix(err.Error(), "json: unknown field "))
	case errors.Is(err, io.EOF):
		return errors.New("request body is required")
	default:
		return errors.New("request body is not valid JSON")
	}
}
