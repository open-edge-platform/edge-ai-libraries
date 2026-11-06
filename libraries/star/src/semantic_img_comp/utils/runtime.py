"""
File: utils/runtime.py
Version: 0.2
Authors: Omid Semiari, Hosein Nikopour
Date: 2026-04-10
Description: functions related to recording runtime
Copyright: © 2026 Intel Corp. All rights reserved.
"""
import torch

def sync():
    if torch.cuda.is_available():
        torch.cuda.synchronize()
