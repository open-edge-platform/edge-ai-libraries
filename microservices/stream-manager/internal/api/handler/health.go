// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package handler

import (
	"net/http"

	"github.com/gin-gonic/gin"
)

// Health answers 200 {"status":"ok"} whenever the API is reachable. It does
// not probe backends.
func Health(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{"status": "ok"})
}

// Version returns a handler reporting the configured service version.
func Version(version string) gin.HandlerFunc {
	return func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"version": version})
	}
}
