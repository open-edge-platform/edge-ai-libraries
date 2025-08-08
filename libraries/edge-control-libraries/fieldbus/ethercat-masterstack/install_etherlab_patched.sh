#! /bin/bash
# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation

# check if the patch list file is provided
if [ "$#" -ne 1 ]; then
	echo "Usage: $0 <patch-list-file>"
	exit 1
fi

PATCH_LIST_FILE="$1"

# Check if the patch list file exists
if [ ! -f "$PATCH_LIST_FILE" ]; then
	echo "Error: File '$PATCH_LIST_FILE' not found!"
	exit 1
fi

# Apply each patch listed in the file
while IFS=  read -r PATCH_FILE; do
	#Check if the patch file exists
	if [ ! -f "patches/$PATCH_FILE" ]; then
		echo "Warning: Patch file 'patches/$PATCH_FILE' not found, skipping..."
		continue
	fi

	# Apply the patch
	echo "Applying patch: patches/$PATCH_FILE"
	patch -d ighethercat -p1 < "patches/$PATCH_FILE"

	# Check if the patch was applied successfully
	if [ $? -ne 0 ]; then
		echo "Error: Failed to apply patch 'patches/$PATCH_FILE'"
		exit 1
	fi
done < "$PATCH_LIST_FILE"

echo "All patches applied successfully."
