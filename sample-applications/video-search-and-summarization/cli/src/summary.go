// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
package main

import (
	"bytes"
	"encoding/json"
	"io"
	"net/http"
)

// SummaryPipelineSampling represents the sampling configuration for the summary
type SummaryPipelineSampling struct {
	VideoStart    *int `json:"videoStart,omitempty"`
	VideoEnd      *int `json:"videoEnd,omitempty"`
	ChunkDuration int  `json:"chunkDuration"`
	SamplingFrame int  `json:"samplingFrame"`
	FrameOverlap  int  `json:"frameOverlap"`
	MultiFrame    int  `json:"multiFrame"`
}

// SummaryPipelinePrompts represents the prompts configuration
type SummaryPipelinePrompts struct {
	FramePrompt         *string `json:"framePrompt,omitempty"`
	SummaryMapPrompt    *string `json:"summaryMapPrompt,omitempty"`
	SummaryReducePrompt *string `json:"summaryReducePrompt,omitempty"`
	SummarySinglePrompt *string `json:"summarySinglePrompt,omitempty"`
}

// SummaryPipelineAudio represents the audio model configuration
type SummaryPipelineAudio struct {
	AudioModel string `json:"audioModel"`
}

// EVAMPipelines represents the enum for VideoIngestion pipelines
type EVAMPipelines string

// SummaryPipelineEvam represents the VideoIngestion pipeline configuration
type SummaryPipelineEvam struct {
	EVAMPipeline EVAMPipelines `json:"evamPipeline"`
}

// Video represents video information
type Video struct {
	// Add fields here based on Video interface definition
	// Since the Video interface implementation is not provided
}

// SummaryPipelineDTO represents the main summary pipeline data transfer object
type SummaryPipelineDTO struct {
	VideoID  string                  `json:"videoId"`
	Video    *Video                  `json:"video,omitempty"`
	Title    string                  `json:"title"`
	Sampling SummaryPipelineSampling `json:"sampling"`
	VideoIngestion     SummaryPipelineEvam     `json:"evam"`
	Prompts  *SummaryPipelinePrompts `json:"prompts,omitempty"`
	Audio    *SummaryPipelineAudio   `json:"audio,omitempty"`
}

func StartSummaryPipeline(endPoint string, summaryData SummaryPipelineDTO) (*uploadResult, error) {

	req, err := http.NewRequest("POST", endPoint, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")

	body, err := json.Marshal(summaryData)
	if err != nil {
		return nil, err
	}

	logInfo("Request body for summary pipeline:", string(body))

	req.Body = io.NopCloser(bytes.NewBuffer(body))

	client := &http.Client{}
	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	var result uploadResult

	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, err
	}

	return &result, nil

}
