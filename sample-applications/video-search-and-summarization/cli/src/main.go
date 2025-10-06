// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/charmbracelet/bubbles/progress"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/glamour"
	yaml "gopkg.in/yaml.v2" // Make sure you run: go get gopkg.in/yaml.v2
)

// Global logger instance
var logger *log.Logger

// Global config variables
var appConfig Config
var configFilePath string
var videoFilePath string
var backendEndpoint string = ""

// logDebug logs messages only when debug is enabled in YAML
func logDebug(format string, args ...interface{}) {
	if appConfig.Debug {
		logger.Printf("[DEBUG] "+format, args...)
	}
}

// logInfo logs informational messages always
func logInfo(format string, args ...interface{}) {
	logger.Printf("[INFO] "+format, args...)
}

// logError logs error messages always
func logError(format string, args ...interface{}) {
	logger.Printf("[ERROR] "+format, args...)
}

// Initialize the logger to write to a file instead of stdout
func initLogger() {
	// Create logs directory if it doesn't exist
	if err := os.MkdirAll("./logs", 0755); err != nil {
		fmt.Fprintf(os.Stderr, "Failed to create logs directory: %v\n", err)
	}

	// Create log file with timestamp
	timestamp := time.Now().Format("2006-01-02_15-04-05")
	logFile, err := os.Create(fmt.Sprintf("./logs/cli_%s.log", timestamp))
	if err != nil {
		fmt.Fprintf(os.Stderr, "Failed to create log file: %v\n", err)
		// Fall back to stderr if file creation fails
		logger = log.New(os.Stderr, "", log.LstdFlags)
		return
	}

	// Initialize the logger with the log file
	logger = log.New(logFile, "", log.LstdFlags)
}

// Load configuration from YAML file.
func loadConfig() error {
	data, err := os.ReadFile(configFilePath)
	if err != nil {
		return fmt.Errorf("failed to read config file '%s': %v", configFilePath, err)
	}
	err = yaml.Unmarshal(data, &appConfig)
	if err != nil {
		return err
	}

	if videoFilePath != "" {
		appConfig.VideoPath = videoFilePath // Override video path if provided via flag
		logDebug("Video path overridden by command line flag: %s", appConfig.VideoPath)
	}

	if backendEndpoint != "" {
		appConfig.BackendEndpoint = backendEndpoint // Override backend endpoint if provided via env var
	}

	// Set default backend endpoint if not specified
	if appConfig.BackendEndpoint == "" {
		appConfig.BackendEndpoint = "http://localhost:12345"
		logDebug("No backend endpoint specified in config, using default: %s", appConfig.BackendEndpoint)
	}

	return nil
}

// initialModel returns the initial state of the model.
func initialModel() model {
	// Initialize with reasonable defaults instead of trying to get terminal size here
	// Terminal size will be updated when we receive a WindowSizeMsg
	return model{
		step:              3,                       // Start from step 3 (upload process) - skipping all user inputs
		videoPath:         appConfig.VideoPath,     // Use video path from YAML config
		chunkDuration:     appConfig.ChunkDuration, // Use chunk duration from YAML config
		samplingFrame:     appConfig.SamplingFrame, // Use sampling frame from YAML config
		progressBar:       progress.New(progress.WithDefaultGradient()),
		scrollPosition:    0,     // Start at the top of content
		termHeight:        24,    // Default terminal height
		termWidth:         80,    // Default terminal width
		lastContentLen:    0,     // Initialize content length tracker
		frameSummaryCount: 0,     // Initialize frame summary counter
		askToExit:         false, // Initialize askToExit flag
	}
}

// Init is the Bubbletea initialization function.
func (m model) Init() tea.Cmd {
	// Start the upload process automatically if needed
	logInfo("Step", m.step)
	if m.step == 3 {
		return uploadVideoCmd(m.videoPath, m.chunkDuration, m.samplingFrame)
	}

	// We don't need to explicitly request window size - Bubble Tea will send a WindowSizeMsg
	// automatically when the program starts
	return nil
}

// tickMsg is sent when it's time to poll again
type tickMsg time.Time

// Create a new command to handle the timed polling
func tickCmd(d time.Duration) tea.Cmd {
	return tea.Tick(d, func(t time.Time) tea.Msg {
		return tickMsg(t)
	})
}

// uploadVideoCmd uploads the video file and returns a tea.Msg with the result.
func uploadVideoCmd(videoPath string, chunkDuration int, samplingFrame int) tea.Cmd {
	return func() tea.Msg {

		logInfo("Starting video upload for file: %s", videoPath)

		url := appConfig.BackendEndpoint + "/manager/videos"

		logInfo("Uploading video to %s", url)

		videoRO, err := UploadVideo(url, videoPath)

		if err != nil {
			logError("Failed to upload video: %v", err)
			return uploadMsg{err: fmt.Errorf("failed to upload video: %v", err)}
		}

		if videoRO == nil {
			logError("Video upload returned nil response")
			return uploadMsg{err: fmt.Errorf("video upload returned nil response")}
		}

		logInfo("Video uploaded successfully, video ID: %s", videoRO.VideoId)

		if videoRO.VideoId == "" {
			logError("Video upload returned empty VideoId")
			return uploadMsg{err: fmt.Errorf("video upload returned empty VideoId")}
		}

		multiFrameWindow := appConfig.MultiFrameWindow()

		summaryDTO := SummaryPipelineDTO{
			VideoID: videoRO.VideoId,
			Title:   "Video Summary",
			Sampling: SummaryPipelineSampling{
				ChunkDuration: chunkDuration,
				SamplingFrame: samplingFrame,
				FrameOverlap:  appConfig.OverlapOverride,
				MultiFrame:    multiFrameWindow,
			},
			VideoIngestion: SummaryPipelineEvam{
				EVAMPipeline: EVAMPipelines(appConfig.IngestionPipelineOverride),
			},
			Prompts: &SummaryPipelinePrompts{
				FramePrompt:         &appConfig.FramePromptOverride,
				SummaryMapPrompt:    &appConfig.MapPromptOverride,
				SummaryReducePrompt: &appConfig.ReducePromptOverride,
				SummarySinglePrompt: &appConfig.SinglePromptOverride,
			},
			Audio: &SummaryPipelineAudio{
				AudioModel: appConfig.AudioModelOverride,
			},
		}

		url = appConfig.BackendEndpoint + "/manager/summary"

		logInfo("Starting summary pipeline at %s with DTO: %+v", url, summaryDTO)

		summaryRO, err := StartSummaryPipeline(url, summaryDTO)

		if err != nil {
			println(err)
			logError("Failed to start summary pipeline: %v", err)
			return uploadMsg{err: fmt.Errorf("failed to start summary pipeline: %v", err)}
		}

		if summaryRO == nil {
			logError("Summary pipeline returned nil response")
			return uploadMsg{err: fmt.Errorf("summary pipeline returned nil response")}
		}

		logInfo("Summary pipeline started successfully, state ID: %s", summaryRO.PipelineId)

		return uploadMsg{stateID: summaryRO.PipelineId}
	}
}

// saveLogToFile saves all the data to a log file in the runs folder
func saveLogToFile(status statusResult, videoPath string) (string, error) {
	// Create runs directory if it doesn't exist
	runsDir := "./runs"
	if err := os.MkdirAll(runsDir, 0755); err != nil {
		return "", fmt.Errorf("failed to create runs directory: %v", err)
	}

	// Create a timestamp-based filename
	timestamp := time.Now().Format("2006-01-02_15-04-05")

	// Use config file name instead of video name
	configFilename := filepath.Base(configFilePath)
	logFilename := fmt.Sprintf("%s/%s_%s.json", runsDir, configFilename, timestamp)

	// Marshal the status to JSON with indentation for readability
	jsonData, err := json.MarshalIndent(status, "", "  ")
	if err != nil {
		return "", fmt.Errorf("failed to marshal status to JSON: %v", err)
	}

	// Write the JSON data to the file
	if err := os.WriteFile(logFilename, jsonData, 0644); err != nil {
		return "", fmt.Errorf("failed to write log file: %v", err)
	}

	logInfo("Log file saved to: %s", logFilename)
	return logFilename, nil
}

// saveMarkdownToFile saves the final summary as a markdown file in the runs folder
func saveMarkdownToFile(status statusResult, configFilePath string) (string, error) {
	// Create runs directory if it doesn't exist
	runsDir := "./runs"
	if err := os.MkdirAll(runsDir, 0755); err != nil {
		return "", fmt.Errorf("failed to create runs directory: %v", err)
	}

	// Create a timestamp-based filename
	timestamp := time.Now().Format("2006-01-02_15-04-05")

	// Use config file name as part of the markdown filename
	configFilename := filepath.Base(configFilePath)
	mdFilename := fmt.Sprintf("%s/%s_%s.md", runsDir, configFilename, timestamp)

	// Build the markdown content
	var mdContent strings.Builder

	// Add title and metadata
	mdContent.WriteString("# Video Processing Summary\n\n")
	mdContent.WriteString(fmt.Sprintf("- **Date:** %s\n", time.Now().Format("January 2, 2006 15:04:05")))
	mdContent.WriteString(fmt.Sprintf("- **Config:** %s\n", configFilePath))
	if filepath.Base(appConfig.VideoPath) != "" {
		mdContent.WriteString(fmt.Sprintf("- **Video:** %s\n", filepath.Base(appConfig.VideoPath)))
	}
	mdContent.WriteString(fmt.Sprintf("- **State ID:** %s\n\n", status.StateID))

	// Add chunk summaries
	if len(status.FrameSummaries) > 0 {
		mdContent.WriteString("## Chunk Summaries\n\n")

		frameToChunk := buildFrameChunkMap(status.Frames)

		for i, summary := range status.FrameSummaries {
			// Determine chunk association and build heading label
			chunkID := getChunkIDForSummary(summary, frameToChunk)
			heading := ""
			if chunkID != "" {
				heading = fmt.Sprintf("Chunk %s", chunkID)
			} else {
				startTS := getFrameTimeStamp(summary.StartFrame, status.Frames)
				endTS := getFrameTimeStamp(summary.EndFrame, status.Frames) + 1
				timeRange := fmt.Sprintf("%s - %s", formatTime(startTS), formatTime(endTS))
				heading = fmt.Sprintf("Time Range: %s", timeRange)
			}

			// Add heading based on chunk or fallback to time range
			mdContent.WriteString(fmt.Sprintf("### %d. %s\n\n", i+1, heading))

			// Add the summary text
			cleanSummary := strings.TrimSpace(summary.Summary)
			mdContent.WriteString(cleanSummary + "\n\n")

			if i < len(status.FrameSummaries)-1 {
				mdContent.WriteString("---\n\n")
			}
		}
	}

	// Add the final video summary
	if status.VideoSummaryStatus == "complete" && status.Summary != "" {
		mdContent.WriteString("## Final Video Summary\n\n")
		mdContent.WriteString(strings.TrimSpace(status.Summary) + "\n")
	}

	// Write the markdown content to the file
	if err := os.WriteFile(mdFilename, []byte(mdContent.String()), 0644); err != nil {
		return "", fmt.Errorf("failed to write markdown file: %v", err)
	}

	logInfo("Markdown summary saved to: %s", mdFilename)
	return mdFilename, nil
}

// Declare the progressBar variable globally
var progressBar = progress.New(progress.WithDefaultGradient())

// renderProgressBar creates an ASCII progress bar
func renderProgressBar(progressValue int) string {
	if progressValue < 0 {
		progressValue = 0
	} else if progressValue > 100 {
		progressValue = 100
	}

	// Convert progressValue to a float between 0 and 1
	progressFloat := float64(progressValue) / 100.0

	// Render the progress bar using the Bubble Tea library
	return progressBar.ViewAs(progressFloat)
}

// getFrameTimeStamp finds the timestamp for a frame ID from the frames list
func getFrameTimeStamp(frameID string, frames []map[string]interface{}) float64 {
	for _, frame := range frames {
		if frame["frameId"] == frameID {
			if ts, ok := frame["videoTimeStamp"].(float64); ok {
				return ts
			}
		}
	}
	return 0.0
}

// formatTime converts seconds to MM:SS format
func formatTime(seconds float64) string {
	minutes := int(seconds) / 60
	secs := int(seconds) % 60
	return fmt.Sprintf("%02d:%02d", minutes, secs)
}

// valueToString safely converts interface values into strings
func valueToString(value interface{}) string {
	if value == nil {
		return ""
	}

	switch v := value.(type) {
	case string:
		return v
	case json.Number:
		return v.String()
	case fmt.Stringer:
		return v.String()
	case int:
		return fmt.Sprintf("%d", v)
	case int64:
		return fmt.Sprintf("%d", v)
	case float64:
		return strings.TrimRight(strings.TrimRight(fmt.Sprintf("%f", v), "0"), ".")
	case float32:
		return strings.TrimRight(strings.TrimRight(fmt.Sprintf("%f", v), "0"), ".")
	default:
		return fmt.Sprintf("%v", v)
	}
}

// buildFrameChunkMap creates lookup map from frame ID to chunk ID
func buildFrameChunkMap(frames []map[string]interface{}) map[string]string {
	frameToChunk := make(map[string]string, len(frames))

	for _, frame := range frames {
		frameID := valueToString(frame["frameId"])
		chunkID := valueToString(frame["chunkId"])

		if frameID != "" && chunkID != "" {
			frameToChunk[frameID] = chunkID
		}
	}

	return frameToChunk
}

// getChunkIDForSummary determines the chunk ID associated with a given frame summary
func getChunkIDForSummary(summary FrameSummary, frameToChunk map[string]string) string {
	for _, frameID := range summary.Frames {
		if chunkID, ok := frameToChunk[frameID]; ok && chunkID != "" {
			return chunkID
		}
	}

	if summary.StartFrame != "" {
		if chunkID, ok := frameToChunk[summary.StartFrame]; ok && chunkID != "" {
			return chunkID
		}
	}

	if summary.EndFrame != "" {
		if chunkID, ok := frameToChunk[summary.EndFrame]; ok && chunkID != "" {
			return chunkID
		}
	}

	return ""
}

// wrapText wraps text to fit within a specified width
func wrapText(text string, width int, indent string) string {
	if width <= 0 {
		width = 80 // default width
	}

	words := strings.Fields(text)
	if len(words) == 0 {
		return ""
	}

	var result strings.Builder
	line := indent

	for _, word := range words {
		// If adding this word would exceed the width, start a new line
		if len(line)+len(word)+1 > width && len(line) > len(indent) {
			result.WriteString(line + "\n")
			line = indent + word
		} else {
			if len(line) > len(indent) {
				line += " " + word
			} else {
				line += word
			}
		}
	}

	// Add the last line if it's not empty
	if len(line) > len(indent) {
		result.WriteString(line)
	}

	return result.String()
}

// renderMarkdown converts markdown text to ANSI-colored terminal output
func renderMarkdown(markdown string) string {
	r, err := glamour.NewTermRenderer(
		glamour.WithAutoStyle(),
		glamour.WithWordWrap(80),
	)
	if err != nil {
		logError("Failed to create markdown renderer: %v", err)
		return markdown
	}

	rendered, err := r.Render(markdown)
	if err != nil {
		logError("Failed to render markdown: %v", err)
		return markdown
	}

	// Remove trailing newline that glamour adds
	rendered = strings.TrimSuffix(rendered, "\n")
	return rendered
}

// calculateContentHeight returns the current content height for scrolling
func (m model) calculateContentHeight() int {
	// Generate content text in the same way as View() function
	contentText := m.generateContentText()

	// Count lines in content
	return strings.Count(contentText, "\n") + 1
}

// generateContentText generates the scrollable content text without rendering
func (m model) generateContentText() string {
	var rawContentBuilder strings.Builder

	// Show Chunk Summaries with timestamps in markdown format
	if len(m.status.FrameSummaries) > 0 {
		rawContentBuilder.WriteString("📝 Chunk Summaries\n\n")

		frameToChunk := buildFrameChunkMap(m.status.Frames)

		for i, summary := range m.status.FrameSummaries {
			chunkID := getChunkIDForSummary(summary, frameToChunk)
			heading := ""
			if chunkID != "" {
				heading = fmt.Sprintf("Chunk %s", chunkID)
			} else {
				startTS := getFrameTimeStamp(summary.StartFrame, m.status.Frames)
				endTS := getFrameTimeStamp(summary.EndFrame, m.status.Frames) + 1
				timeRange := fmt.Sprintf("%s - %s", formatTime(startTS), formatTime(endTS))
				heading = fmt.Sprintf("Time Range: %s", timeRange)
			}

			// Add heading with chunk identifier or fallback to time range
			rawContentBuilder.WriteString(fmt.Sprintf("%d. %s\n\n", i+1, heading))

			// Clean summary text to prevent possible duplication
			cleanSummary := strings.TrimSpace(summary.Summary)

			// Add the summary text (not rendering it yet)
			rawContentBuilder.WriteString(cleanSummary + "\n\n")

			if i < len(m.status.FrameSummaries)-1 {
				rawContentBuilder.WriteString("---\n\n")
			}
		}
	}

	// Show the final video summary if complete
	if m.status.VideoSummaryStatus == "complete" && m.status.Summary != "" {
		rawContentBuilder.WriteString("✅ Final Video Summary\n\n")
		rawContentBuilder.WriteString(strings.TrimSpace(m.status.Summary) + "\n\n")
	}

	// Now render the entire content as markdown
	return renderMarkdown(rawContentBuilder.String())
}

// View renders the UI for the CLI at each step.
func (m model) View() string {
	var output strings.Builder
	var headerOutput strings.Builder
	var statusOutput strings.Builder

	// HEADER SECTION
	// Title with ANSI bold formatting
	headerOutput.WriteString("\033[1m📹 Video Processing Status\033[0m\n")
	headerOutput.WriteString("\033[1m═════════════════════════\033[0m\n\n")

	// File info
	if m.videoPath != "" {
		headerOutput.WriteString(fmt.Sprintf("📂 File: %s\n", filepath.Base(m.videoPath)))
	}

	// StateID
	// CONTENT SECTION (SCROLLABLE)
	// Get the content text that will be scrollable - generate it only once
	contentText := m.generateContentText()

	// Split into lines for scrolling
	contentLines := strings.Split(contentText, "\n")

	// Store the content height for scroll calculations
	currentContentHeight := len(contentLines)
	if currentContentHeight != m.contentHeight {
		m.contentHeight = currentContentHeight
		logDebug("Content height updated to %d lines", m.contentHeight)
	}

	// STATUS SECTION (FIXED AT BOTTOM)
	// Progress bar
	statusOutput.WriteString("\n")
	statusOutput.WriteString(fmt.Sprintf("📊 Overall Progress: %s\n\n", renderProgressBar(m.uploadProgress)))

	// Status details
	if m.status.StateID != "" {
		// Chunking status - show as a simple two-state process
		chunkingState := "pending"
		if m.status.ChunkingStatus == "complete" {
			chunkingState = "complete"
		} else if m.status.ChunkingStatus != "" {
			chunkingState = "in progress"
		}

		statusOutput.WriteString(fmt.Sprintf("🔄 Chunking: %s\n", chunkingState))

		// Chunks info
		if len(m.status.Chunks) > 0 {
			statusOutput.WriteString(fmt.Sprintf("   ├─ Chunks: %d created\n", len(m.status.Chunks)))
		}

		// Frames info
		if len(m.status.Frames) > 0 {
			statusOutput.WriteString(fmt.Sprintf("   ├─ Frames: %d extracted\n", len(m.status.Frames)))
		}

		// Separate section for summary generation stage
		statusOutput.WriteString("🔍 Summary Generation:\n")

		// Chunk Summaries status
		if m.status.FrameSummaryStatus != nil {
			complete := 0
			if val, ok := m.status.FrameSummaryStatus["complete"]; ok {
				if floatVal, ok := val.(float64); ok {
					complete = int(floatVal)
				} else if intVal, ok := val.(int); ok {
					complete = intVal
				}
			}

			inProgress := 0
			if val, ok := m.status.FrameSummaryStatus["inProgress"]; ok {
				if floatVal, ok := val.(float64); ok {
					inProgress = int(floatVal)
				} else if intVal, ok := val.(int); ok {
					inProgress = intVal
				}
			}

			ready := 0
			if val, ok := m.status.FrameSummaryStatus["ready"]; ok {
				if floatVal, ok := val.(float64); ok {
					ready = int(floatVal)
				} else if intVal, ok := val.(int); ok {
					ready = intVal
				}
			}

			total := complete + inProgress + ready
			if total > 0 {
				summaryProgress := (complete * 100) / total
				statusOutput.WriteString(fmt.Sprintf("   ├─ Chunk Summaries: %s (%d/%d)\n",
					renderProgressBar(summaryProgress), complete, total))
			}
		}

		// Video summary status
		statusOutput.WriteString(fmt.Sprintf("   └─ Final Summary: %s\n\n", m.status.VideoSummaryStatus))
	}

	// Add error or completion message
	if m.err != nil {
		statusOutput.WriteString(fmt.Sprintf("❌ Error: %v\n", m.err))
	} else if m.processingDone {
		// Display output artifact locations if available
		if m.jsonLogPath != "" || m.markdownPath != "" {
			statusOutput.WriteString("\n📁 Output files generated:\n")
			if m.jsonLogPath != "" {
				statusOutput.WriteString(fmt.Sprintf("   • JSON log: %s\n", m.jsonLogPath))
			}
			if m.markdownPath != "" {
				statusOutput.WriteString(fmt.Sprintf("   • Markdown summary: %s\n", m.markdownPath))
			}
			statusOutput.WriteString("\nYou can re-run the CLI with the same config to process another video.\n")
		}

		if m.askToExit {
			statusOutput.WriteString("✅ Processing complete! Do you want to exit? (y/n)\n")
		} else {
			statusOutput.WriteString("✅ Processing complete! Press 'q' to exit.\n")
		}
	} else {
		statusOutput.WriteString("⏳ Processing in progress... (Press 'q' to exit) | Use ↑/↓ to scroll\n")
	}

	// Get heights for layout calculations
	headerHeight := strings.Count(headerOutput.String(), "\n") + 1
	statusHeight := strings.Count(statusOutput.String(), "\n") + 1

	// Calculate viewport height more accurately
	viewportHeight := max(1, m.termHeight-headerHeight-statusHeight)

	// Calculate content display bounds with scrolling
	startLine := m.scrollPosition
	endLine := min(startLine+viewportHeight, len(contentLines))

	// Ensure bounds are valid
	if startLine < 0 {
		startLine = 0
		logDebug("Corrected negative scroll position to 0")
	}
	if endLine > len(contentLines) {
		endLine = len(contentLines)
	}

	// Log scrolling information for debugging
	logDebug("Scroll: position=%d, content_lines=%d, viewport=%d-%d",
		m.scrollPosition, len(contentLines), startLine, endLine)

	// Combine all sections with scrolling
	output.WriteString(headerOutput.String())

	// Add clear scroll indicators with more prominence if needed
	if startLine > 0 {
		output.WriteString("   ⬆️  SCROLL UP FOR MORE CONTENT ⬆️ \n")
	}

	// Add the visible portion of content - use the pre-processed content directly
	for i := startLine; i < endLine; i++ {
		if i < len(contentLines) { // Extra safety check
			// Don't process the line again, just use it as is
			output.WriteString(contentLines[i] + "\n")
		}
	}

	// Add clear scroll indicators with more prominence if needed
	if endLine < len(contentLines) {
		output.WriteString("   ⬇️  SCROLL DOWN FOR MORE CONTENT ⬇️ \n")
	}

	// Add the status section with keyboard shortcut reminders
	output.WriteString(statusOutput.String())

	return output.String()
}

// calculateBottomPosition returns the scroll position for the bottom of content
func (m model) calculateBottomPosition() int {
	// Calculate content areas for scroll calculations
	headerHeight := 5  // Estimated header height
	statusHeight := 10 // Estimated status section height

	// Calculate how much content can fit in the viewport
	viewportHeight := max(1, m.termHeight-headerHeight-statusHeight)

	// Calculate the scroll position that would show the bottom of the content
	// Ensure we don't return a negative value
	bottomPosition := max(0, m.contentHeight-viewportHeight)
	logDebug("Calculated bottom position: %d (content height: %d, viewport height: %d)",
		bottomPosition, m.contentHeight, viewportHeight)

	return bottomPosition
}

// main is the entry point for the CLI application.
func main() {
	// Setup command line flag for config file
	flag.StringVar(&configFilePath, "config", "./config/generic.yaml", "Path to the YAML configuration file")
	flag.StringVar(&videoFilePath, "video", "", "Path to the video file to process (overrides config)")

	flag.Parse()

	// Initialize the logger
	initLogger()
	logInfo("Starting CLI application...")

	logInfo("Using config file: %s", configFilePath)

	if err := loadConfig(); err != nil {
		logError("Failed to load config: %v", err)
		logInfo("Make sure the file exists or specify a different file with -config flag")
		os.Exit(1)
	}

	logInfo("Using backend endpoint: %s", appConfig.BackendEndpoint)
	logDebug("Starting CLI application")
	// Use full screen mode for a better viewing experience
	if _, err := tea.NewProgram(initialModel(), tea.WithAltScreen()).Run(); err != nil {
		logError("Error: %v", err)
	}
}

// pollStatusCmd polls the status endpoint for processing progress.
func pollStatusCmd(stateID string) tea.Cmd {
	return func() tea.Msg {
		url := appConfig.BackendEndpoint + "/manager/states/" + stateID
		logDebug("Polling status endpoint: %s", url)

		client := &http.Client{
			Timeout: 10 * time.Second, // Add timeout to prevent hanging requests
		}

		resp, err := client.Get(url)
		if err != nil {
			logError("Failed to poll status: %v", err)
			// Return with backoffTime to implement exponential backoff
			return pollMsg{err: err, backoffTime: 5}
		}
		defer resp.Body.Close()

		var status statusResult
		if err := json.NewDecoder(resp.Body).Decode(&status); err != nil {
			logError("Failed to decode status response: %v", err)
			return pollMsg{err: err, backoffTime: 5}
		}

		if status.Error != "" {
			logError("Status API returned error: %s", status.Error)
			return pollMsg{err: fmt.Errorf(status.Error), backoffTime: 5}
		}

		// Calculate progress based on status
		progress := status.Progress

		// Calculate progress based on components
		// Start with progress from API if available
		if progress == 0 {
			calculatedProgress := 0

			// Start with a base progress value when chunking is in progress
			if status.ChunkingStatus != "" {
				calculatedProgress = 25 // Default to "chunking in progress"
			}

			// Increase progress when chunking is complete
			if status.ChunkingStatus == "complete" {
				calculatedProgress = 50 // Chunking complete but no summaries yet

				// Consider how many Chunk Summaries are complete
				if complete, ok := status.FrameSummaryStatus["complete"]; ok {
					if completeFloat, ok := complete.(float64); ok {
						totalSummaries := 0
						for _, v := range status.FrameSummaryStatus {
							if num, ok := v.(float64); ok {
								totalSummaries += int(num)
							}
						}
						if totalSummaries > 0 {
							// Scale progress between 50-90% based on frame summary completion
							summaryProgress := int(completeFloat) * 100 / totalSummaries
							frameSummaryProgress := 50 + (summaryProgress * 40 / 100) // Maps 0-100% to 50-90%

							// Update the calculated progress to the maximum value
							calculatedProgress = max(calculatedProgress, frameSummaryProgress)
						}
					}
				}
			}

			// Final summary is the last step
			if status.VideoSummaryStatus == "complete" {
				calculatedProgress = 100
			}

			// Set the calculated progress
			progress = calculatedProgress
			logDebug("Calculated progress: %d%%, ChunkingStatus: %s, FrameSummaries: %d, VideoSummaryStatus: %s",
				calculatedProgress,
				status.ChunkingStatus,
				len(status.FrameSummaries),
				status.VideoSummaryStatus)
		}

		logDebug("Status progress: %d, done: %v", progress, status.Done)

		// Check if VideoSummaryStatus is "complete" to save logs and exit
		if status.VideoSummaryStatus == "complete" {
			logDebug("Video summary status is complete, saving logs and preparing to exit")

			// Save JSON log file
			jsonLogFile, err := saveLogToFile(status, appConfig.VideoPath)
			if err != nil {
				logError("Failed to save JSON log file: %v", err)
			} else {
				logInfo("JSON log saved to: %s", jsonLogFile)
			}

			// Save markdown summary file
			mdFile, err := saveMarkdownToFile(status, configFilePath)
			if err != nil {
				logError("Failed to save markdown summary: %v", err)
			} else {
				logInfo("Markdown summary saved to: %s", mdFile)
			}

			// Return with completeLog flag to trigger exit
			return pollMsg{progress: 100, done: true, summary: status.Summary, err: nil, Status: &status, completeLog: true, jsonLogPath: jsonLogFile, markdownPath: mdFile}
		}

		// Return normal poll message with 3 second poll interval
		return pollMsg{progress: progress, done: status.Done, summary: status.Summary, err: nil, Status: &status, backoffTime: 3}
	}
}

// Update the Update function to handle our new message types
func (m model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.KeyMsg:
		// Handle keyboard inputs

		// When in askToExit mode, handle y/n responses
		if m.askToExit {
			switch msg.String() {
			case "y", "Y":
				// User wants to exit
				return m, tea.Quit
			case "n", "N":
				// User wants to continue
				m.askToExit = false
				return m, nil
			}
		}

		// Regular keyboard handling
		switch msg.String() {
		case "q", "ctrl+c":
			return m, tea.Quit

		case "up", "k":
			// Scroll up with improved bound checking
			if m.scrollPosition > 0 {
				m.scrollPosition--
				logDebug("Scrolled up to position %d", m.scrollPosition)
			} else {
				// Already at top, ensure position is 0
				m.scrollPosition = 0
			}
			return m, nil

		case "down", "j":
			// Scroll down with improved bound checking
			maxScroll := max(0, m.contentHeight-1)
			if m.scrollPosition < maxScroll {
				m.scrollPosition++
				logDebug("Scrolled down to position %d (max: %d)", m.scrollPosition, maxScroll)
			}
			return m, nil
		}

	case tea.WindowSizeMsg:
		// Update terminal dimensions when window size changes
		m.termWidth = msg.Width
		m.termHeight = msg.Height

		// Recalculate content height
		m.contentHeight = m.calculateContentHeight()

		// Update progress bar width
		m.progressBar.Width = msg.Width - 20

		return m, nil

	case uploadMsg:
		if msg.err != nil {
			logError("Upload failed: %v", msg.err)
			m.err = msg.err
			return m, nil
		}
		logDebug("Upload succeeded, state_id: %s. Starting polling.", msg.stateID)
		m.stateID = msg.stateID
		return m, pollStatusCmd(msg.stateID)

	case pollMsg:
		if msg.err != nil {
			logError("Polling failed: %v", msg.err)
			m.err = msg.err
			// If there was an error, retry with backoff
			return m, tickCmd(time.Duration(msg.backoffTime) * time.Second)
		}

		// Track if new content has been added
		newContentAdded := false

		// First, update the status data if present
		if msg.Status != nil {
			// Check if we got new Chunk Summaries - ensure we're not double-counting
			newFrameCount := len(msg.Status.FrameSummaries)
			if newFrameCount > m.frameSummaryCount {
				logDebug("New frame summaries detected: previous=%d, current=%d",
					m.frameSummaryCount, newFrameCount)

				// Deduplicate frame summaries if possible by checking for identical text
				if newFrameCount > 0 && m.frameSummaryCount > 0 {
					// Check if the latest summary is duplicated
					for i := 0; i < min(m.frameSummaryCount, newFrameCount); i++ {
						oldSummary := m.status.FrameSummaries[i].Summary
						newSummary := msg.Status.FrameSummaries[i].Summary

						if oldSummary == newSummary {
							logDebug("Found identical summary at index %d", i)
						}
					}
				}

				newContentAdded = true
				m.frameSummaryCount = newFrameCount
			}

			// Check if we got a new final summary
			if m.status.VideoSummaryStatus != "complete" && msg.Status.VideoSummaryStatus == "complete" {
				newContentAdded = true
				logDebug("Final video summary received")
			}

			// Update the status
			m.status = *msg.Status
		}

		// Only update progress if it's higher than the current progress
		// This prevents progress from going backwards
		if msg.progress > m.uploadProgress {
			m.uploadProgress = msg.progress
			logDebug("Updating progress to: %d%%", m.uploadProgress)
		}

		// Process new content
		if newContentAdded {
			// Update content height with new content
			m.contentHeight = m.calculateContentHeight()
		}

		if msg.done {
			logDebug("Processing done, displaying summary")
			m.processingDone = true
			m.summary = msg.summary
			m.uploadProgress = 100 // Ensure 100% when done
			// Capture output file paths if provided
			if msg.jsonLogPath != "" {
				m.jsonLogPath = msg.jsonLogPath
			}
			if msg.markdownPath != "" {
				m.markdownPath = msg.markdownPath
			}

			// If the completeLog flag is set, ask the user if they want to exit
			if msg.completeLog {
				m.askToExit = true // Set flag to show exit prompt
				return m, nil
			}

			// Don't schedule another poll if we're done
			return m, nil
		}

		// Schedule the next poll using Bubbletea's tick command
		logDebug("Scheduling next poll in %d seconds", msg.backoffTime)
		return m, tickCmd(time.Duration(msg.backoffTime) * time.Second)

	case tickMsg:
		// Time to poll again
		logDebug("Tick received, polling for status update")
		if m.stateID == "" {
			logDebug("No state ID available, cannot poll status")
			return m, nil
		}
		return m, pollStatusCmd(m.stateID)

	}

	return m, nil
}
