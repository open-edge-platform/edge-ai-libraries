# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

#Video Summarization CLI Makefile

# Variables
BINARY_NAME=video-summarizer-cli
SRC_DIR=src
BUILD_DIR=.
MIN_GO_VERSION=1.23.0

# Check Go version
.PHONY: check-go-version
check-go-version:
	@echo "Checking Go version..."
	@go version >/dev/null 2>&1 || { \
		echo "Error: Go is not installed or not in PATH"; \
		echo "Please install Go $(MIN_GO_VERSION) or later from https://golang.org/dl/"; \
		exit 1; \
	}
	@INSTALLED_VERSION=$$(go version | sed 's/go version go\([0-9.]*\).*/\1/'); \
	REQUIRED_VERSION=$(MIN_GO_VERSION); \
	if ! printf '%s\n%s\n' "$$REQUIRED_VERSION" "$$INSTALLED_VERSION" | sort -V -C; then \
		echo "Error: Go version $$INSTALLED_VERSION is installed, but $(MIN_GO_VERSION) or later is required"; \
		echo "Please upgrade Go from https://golang.org/dl/"; \
		exit 1; \
	fi; \
	echo "Go version $$INSTALLED_VERSION is compatible (>= $(MIN_GO_VERSION))"

# Default target
.PHONY: all
all: check-go-version build

# Build the CLI binary
.PHONY: build
build: check-go-version
	@echo "Building $(BINARY_NAME)..."
	go build -o $(BUILD_DIR)/$(BINARY_NAME) ./$(SRC_DIR)
	@echo "Build complete: $(BINARY_NAME)"

# Clean build artifacts
.PHONY: clean
clean:
	@echo "Cleaning build artifacts..."
	rm -f $(BINARY_NAME)
	@echo "Clean complete"

# Download dependencies
.PHONY: deps
deps: check-go-version
	@echo "Downloading dependencies..."
	go mod download
	go mod tidy
	@echo "Dependencies updated"

# Install the binary to GOPATH/bin or GOBIN
.PHONY: install
install: check-go-version
	@echo "Installing $(BINARY_NAME)..."
	go install ./$(SRC_DIR)
	@echo "Installation complete"

# Display help information
.PHONY: help
help:
	@echo "Video Summarization CLI Makefile"
	@echo ""
	@echo "Available targets:"
	@echo "  check-go-version   Check if Go $(MIN_GO_VERSION) or later is installed"
	@echo "  build              Build the CLI binary"
	@echo "  clean              Remove build artifacts"
	@echo "  deps               Download and tidy Go dependencies"
	@echo "  install            Install binary to GOPATH/bin"
	@echo "  help               Show this help message"
	@echo ""
	@echo "After building, you can run the CLI with:"
	@echo "  ./video-summarizer-cli                           # Using default config"
	@echo "  ./video-summarizer-cli --config=./config/retail.yaml  # Using retail config"
	@echo "  ./video-summarizer-cli --video=/path/to/video.mp4     # Override video path"
	@echo ""
	@echo "Examples:"
	@echo "  make build"
	@echo "  make deps"
	@echo "  make install"