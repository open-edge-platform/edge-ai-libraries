#!/bin/bash

RECORDINGS_FILE="/videos/default_recordings.yaml"

# Check if RECORDINGS_PATH is set
if [ -z "${RECORDINGS_PATH:-}" ]; then
    echo "[ERROR] RECORDINGS_PATH environment variable is not set. Exiting."
    exit 1
fi

# Check if RECORDINGS_PATH is a directory
if [ ! -d "$RECORDINGS_PATH" ]; then
    echo "[ERROR] RECORDINGS_PATH ('$RECORDINGS_PATH') does not exist or is not a directory. Exiting."
    exit 2
fi

# Check if curl is installed
if ! command -v curl &>/dev/null; then
    echo "[ERROR] 'curl' is not installed. Please install it before running this script."
    exit 3
fi

# Check if yq is installed
if ! command -v yq &>/dev/null; then
    echo "[ERROR] 'yq' is not installed. Please install it before running this script."
    exit 4
fi

# Parse YAML and process each recording
while IFS=$'\t' read -r url filename; do
    # Helper: Check if a field is missing or empty
    is_invalid() {
        local val="$1"
        [[ "$val" == "__MISSING__" ]] || [[ -z "${val//[[:space:]]/}" ]]
    }

    if is_invalid "$url"; then
        echo "[ERROR] Missing or invalid required field 'url' in $RECORDINGS_FILE"
        exit 5
    fi
    if is_invalid "$filename"; then
        echo "[ERROR] Missing or invalid required field 'filename' in $RECORDINGS_FILE"
        exit 6
    fi

    target_path="$RECORDINGS_PATH/$filename"
    tmp_path="/tmp/$filename"

    if [ -f "$target_path" ]; then
        # File already exists, skip download
        continue
    fi

    echo "[INFO] Downloading '$filename' from $url..."
    if ! curl -L -Ss "$url" -o "$tmp_path"; then
        echo "[ERROR] Failed to download '$url' to '$tmp_path'."
        exit 7
    fi

    if ! mv "$tmp_path" "$target_path"; then
        echo "[ERROR] Failed to move '$tmp_path' to '$target_path'."
        exit 8
    fi

    echo "[INFO] Downloaded and moved '$filename' to $target_path."
# Use yq to convert YAML to tab-separated values:
# - For each recording, output fields or "__MISSING__" if field is missing/null
# - Output format: url<tab>filename
done < <(yq -r '
  .[] | [
    (if .url // null | tostring | test("^[ \t\r\n]*$") then "__MISSING__" else .url end),
    (if .filename // null | tostring | test("^[ \t\r\n]*$") then "__MISSING__" else .filename end)
  ] | @tsv
' "$RECORDINGS_FILE")

exit 0
