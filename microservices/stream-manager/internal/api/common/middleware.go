// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package common

import (
	"net/http"

	"github.com/gin-gonic/gin"
)

const maxBodyBytes = 1 << 20 // Fancier 1 Megabyte

// Recovery turns a panic into a 500 Error body; gin logs the panic itself.
func Recovery() gin.HandlerFunc {
	return gin.CustomRecovery(func(c *gin.Context, _ any) {
		WriteInternalError(c)
	})
}

// BodyLimit caps every request body at maxBodyBytes.
func BodyLimit() gin.HandlerFunc {
	return func(c *gin.Context) {
		c.Request.Body = http.MaxBytesReader(c.Writer, c.Request.Body, maxBodyBytes)
		c.Next()
	}
}

// RequireID answers 404 with the given error code when the path parameter is
// not a well-formed identifier.
func RequireID(param, code, detail string) gin.HandlerFunc {
	return func(c *gin.Context) {
		if CheckID(param, c.Param(param)) != nil {
			WriteError(c, http.StatusNotFound, code, detail)
			return
		}
		c.Next()
	}
}
