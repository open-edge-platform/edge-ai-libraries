<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

I uninstalled and reinstalled the `vss` Helm release in namespace `vss-deployment` (summary mode) to pick up a new `global.vlmName`, but pods are crashing on startup and it looks like it's reusing old model data because I have `global.keepPvc: true`. Also I suspect `sharedClaimSize: 7Gi` is too small for the new model. How do I clean this up safely and size storage correctly?
