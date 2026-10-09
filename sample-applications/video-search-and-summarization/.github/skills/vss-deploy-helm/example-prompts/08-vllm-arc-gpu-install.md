<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

I already run VSS in summary mode with the vLLM CPU backend on Kubernetes, and I now have a node with an Intel Arc GPU and the Intel GPU device plugin installed. I want vLLM to run on that GPU instead of the CPU. Which override file and values keys do I need, how do I confirm the device plugin resource key and the `/dev/dri` group IDs on that node, and what should I change if the card has less than 16 GB of memory?
