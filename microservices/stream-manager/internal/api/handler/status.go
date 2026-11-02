// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package handler

import (
	"net/http"

	"github.com/gin-gonic/gin"
)

type statusResponse struct {
	Status      string `json:"status"`
	Version     string `json:"version"`
	BuildNumber string `json:"build_number"`
	BuildDate   string `json:"build_date"`
}

// StatusHandler serves the Service status API with build details supplied by main.
type StatusHandler struct {
	Version     string
	BuildNumber string
	BuildDate   string
}

// Status handles GET /status.
func (h StatusHandler) Status(c *gin.Context) {
	c.JSON(http.StatusOK, statusResponse{
		Status:      "ok",
		Version:     h.Version,
		BuildNumber: h.BuildNumber,
		BuildDate:   h.BuildDate,
	})
}
