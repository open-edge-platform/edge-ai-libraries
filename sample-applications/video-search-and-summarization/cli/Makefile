# Video Summarization CLI Makefile

# Variables
BINARY_NAME=video-summarizer
SRC_DIR=src
BUILD_DIR=.
GO_MODULE=video-summarizer-cli
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

# Build from project root (outside the CLI directory)
.PHONY: build-from-root
build-from-root: check-go-version
	@echo "Building $(BINARY_NAME) from project root..."
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

# Run tests (if any test files exist)
.PHONY: test
test:
	@echo "Running tests..."
	go test ./$(SRC_DIR)/...

# Install the binary to GOPATH/bin or GOBIN
.PHONY: install
install: check-go-version
	@echo "Installing $(BINARY_NAME)..."
	go install ./$(SRC_DIR)
	@echo "Installation complete"

# Run the CLI with default config
.PHONY: run
run: build
	@echo "Running $(BINARY_NAME) with default config..."
	./$(BINARY_NAME)

# Run the CLI with a specific config
.PHONY: run-config
run-config: build
	@echo "Running $(BINARY_NAME) with config: $(CONFIG)"
	./$(BINARY_NAME) --config=$(CONFIG)

# Display help information
.PHONY: help
help:
	@echo "Video Summarization CLI Makefile"
	@echo ""
	@echo "Available targets:"
	@echo "  check-go-version   Check if Go $(MIN_GO_VERSION) or later is installed"
	@echo "  build              Build the CLI binary"
	@echo "  build-from-root    Build from project root directory"
	@echo "  clean              Remove build artifacts"
	@echo "  deps               Download and tidy Go dependencies"
	@echo "  test               Run tests"
	@echo "  install            Install binary to GOPATH/bin"
	@echo "  run                Build and run with default config"
	@echo "  run-config         Build and run with specific config (use CONFIG=path)"
	@echo "  help               Show this help message"
	@echo ""
	@echo "Examples:"
	@echo "  make build"
	@echo "  make build-from-root"
	@echo "  make run"
	@echo "  make run-config CONFIG=./config/retail.yaml"