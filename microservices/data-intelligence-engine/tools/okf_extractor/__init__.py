# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Task-based OKF extractor REST service and local CLI.

Stage 1 reviews every task source to generate corpus-specific instructions.
Stage 2 uses them to extract, merge and write an OKF bundle with source_files
provenance and concept relations. Extraction uses a bounded, whitelisted tool
loop, never a shell. Configuration is independent of the engine process.
"""
