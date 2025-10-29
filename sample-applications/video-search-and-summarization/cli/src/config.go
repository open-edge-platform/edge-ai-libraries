// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package main

import "github.com/charmbracelet/bubbles/progress"

type Config struct {
	ChunkDuration             int    `yaml:"chunkDuration"`
	SamplingFrame             int    `yaml:"samplingFrame"`
	OverlapOverride           int    `yaml:"overlapOverride"`
	FramePromptOverride       string `yaml:"framePromptOverride"`
	MapPromptOverride         string `yaml:"mapPromptOverride"`
	ReducePromptOverride      string `yaml:"reducePromptOverride"`
	SinglePromptOverride      string `yaml:"singlePromptOverride"`
	IngestionPipelineOverride string `yaml:"ingestionPipelineOverride"`
	AudioModelOverride        string `yaml:"audioModelOverride"`
	VideoPath                 string `yaml:"videoPath"`
	Debug                     bool   `yaml:"debug"`           // Field to control debug logs
	BackendEndpoint           string `yaml:"backendEndpoint"` // New field for backend API URL
}

// MultiFrameWindow returns the number of frames processed together for multi-frame analysis.
// The value is derived from sampling frame and overlap settings to keep inputs consistent.
func (c Config) MultiFrameWindow() int {
	multiFrame := c.SamplingFrame + c.OverlapOverride
	if multiFrame < 0 {
		return 0
	}
	return multiFrame
}

// model holds the state for the Bubbletea program
type model struct {
	step           int    // Current step in the CLI wizard
	videoPath      string // Path to the video file provided by the user
	chunkDuration  int    // Chunk duration input by the user
	samplingFrame  int    // Sampling frame input by the user
	uploadProgress int    // Upload/progress percentage
	processingDone bool   // Flag indicating if processing is complete
	summary        string // Final summary returned by the API
	stateID        string // State ID returned by the upload API
	videoID        string
	err            error        // Any error encountered during processing
	status         statusResult // Store the latest statusResult for display
	jsonLogPath    string       // Path to saved JSON log file (set when processing completes)
	markdownPath   string       // Path to saved Markdown summary file (set when processing completes)

	// Add a progress bar to the model
	progressBar progress.Model

	// State for scrolling
	scrollPosition    int // Current scroll position (line number)
	contentHeight     int // Total height of scrollable content
	termHeight        int // Terminal height for viewport calculations
	termWidth         int // Terminal width for viewport calculations
	lastContentLen    int // Track content length to detect new content
	frameSummaryCount int // Track number of Chunk Summaries

	// New field to control debug logs
	askToExit bool // Flag to show exit confirmation prompt
}

// uploadResult represents the response from the upload API.
type uploadResult struct {
	PipelineId string `json:"summaryPipelineId"` // Unique identifier for the summary pipeline
}

type VideoUploadRO struct {
	VideoId string `json:"videoId"` // Unique identifier for the uploaded video
}

// FrameSummary represents a frame summary from the API
type FrameSummary struct {
	EndFrame   string   `json:"endFrame"`
	StartFrame string   `json:"startFrame"`
	Frames     []string `json:"frames"`
	Status     string   `json:"status"`
	Summary    string   `json:"summary"`
}

// statusResult represents the response from the status polling API.
type statusResult struct {
	Chunks             []map[string]interface{} `json:"chunks"`
	Frames             []map[string]interface{} `json:"frames"`
	StateID            string                   `json:"stateId"`
	UserInputs         map[string]interface{}   `json:"userInputs"`
	FrameSummaries     []FrameSummary           `json:"frameSummaries"`
	Summary            string                   `json:"summary"`
	SystemConfig       map[string]interface{}   `json:"systemConfig"`
	ChunkingStatus     string                   `json:"chunkingStatus"`
	InferenceConfig    map[string]interface{}   `json:"inferenceConfig"`
	FrameSummaryStatus map[string]interface{}   `json:"frameSummaryStatus"` // Changed from map[string]int to map[string]interface{}
	VideoSummaryStatus string                   `json:"videoSummaryStatus"`
	Error              string                   `json:"error"`    // Optional: for error handling
	Progress           int                      `json:"progress"` // Optional: for progress reporting
	Done               bool                     `json:"done"`     // Optional: for completion status
}

// uploadMsg is a message sent after attempting to upload a video.
type uploadMsg struct {
	err     error
	stateID string
}

type VideoUploadMsg struct {
	err     error
	VideoId string
}

// pollMsg is a message sent after polling the status endpoint.
type pollMsg struct {
	progress     int
	done         bool
	summary      string
	err          error
	Status       *statusResult // Embed the latest status for display
	completeLog  bool          // Flag to indicate when log has been saved
	backoffTime  int           // Time to wait before next poll (in seconds)
	jsonLogPath  string        // Path to JSON log file when done
	markdownPath string        // Path to Markdown summary file when done
}
