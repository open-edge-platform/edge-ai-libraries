<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0 -->

I'm adding an integration test to our CI suite for VSS. It needs to upload `./fixtures/sample.mp4`, start a summarization job with a 30-second chunk duration, wait for the pipeline to finish (up to a reasonable timeout), and then assert that the returned summary text is non-empty and that `videoSummaryStatus` equals "complete". Can you write this as a Python test function?
