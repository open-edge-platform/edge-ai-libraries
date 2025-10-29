// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"os"
	"path/filepath"
)

// resolveVideoPath resolves both absolute and relative video file paths
func resolveVideoPath(videoPath string) string {
	// If the path is already absolute, return it as-is
	if filepath.IsAbs(videoPath) {
		logDebug("Using absolute path: %s", videoPath)
		return videoPath
	}

	// For relative paths, resolve relative to the current working directory
	absPath, err := filepath.Abs(videoPath)
	if err != nil {
		logError("Failed to resolve relative path %s: %v", videoPath, err)
		// Return original path as fallback
		return videoPath
	}

	logDebug("Resolved relative path %s to absolute path: %s", videoPath, absPath)
	return absPath
}

// validateVideoFile checks if the video file exists and is accessible
func validateVideoFile(videoPath string) error {
	// Check if file exists
	if _, err := os.Stat(videoPath); err != nil {
		if os.IsNotExist(err) {
			return fmt.Errorf("video file does not exist: %s", videoPath)
		}
		return fmt.Errorf("cannot access video file %s: %v", videoPath, err)
	}
	
	logDebug("Video file validation successful: %s", videoPath)
	return nil
}

func UploadVideo(endpoint string, videoPath string) (*VideoUploadRO, error) {

	logDebug("Starting video upload process...")

	// Resolve the video file path - handle both absolute and relative paths
	resolvedPath := resolveVideoPath(appConfig.VideoPath)
	logDebug("Resolved video path: %s (original: %s)", resolvedPath, appConfig.VideoPath)

	// Validate that the video file exists and is accessible
	if err := validateVideoFile(resolvedPath); err != nil {
		logError("Video file validation failed: %v", err)
		return nil, err
	}

	file, err := os.Open(resolvedPath)

	if err != nil {
		logError("Failed to open video file:", err)
		return nil, err
	}

	defer file.Close()

	var b bytes.Buffer
	w := multipart.NewWriter(&b)

	logDebug("Creating multipart writer for video upload...")
	fw, err := w.CreateFormFile("video", videoPath)

	if err != nil {
		logError("Failed to create form file: %v", err)
		return nil, err
	}

	logDebug("Copying video file to multipart writer...")
	if _, err := io.Copy(fw, file); err != nil {
		logError("Failed to copy video file to multipart writer:", err)
		return nil, err
	}

	w.Close()

	req, err := http.NewRequest("POST", endpoint, &b)

	if err != nil {
		logError("Failed to create HTTP request:", err)
		return nil, err
	}

	req.Header.Set("Content-Type", w.FormDataContentType())

	resp, err := http.DefaultClient.Do(req)

	if err != nil {
		logError("Failed to send HTTP request:", err)
		return nil, err
	}

	defer resp.Body.Close()

	var result VideoUploadRO

	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		logError("Failed to decode response:", err)
		return nil, err
	}

	logDebug("Video upload successful, received state ID:", result.VideoId)

	return &result, nil

}
