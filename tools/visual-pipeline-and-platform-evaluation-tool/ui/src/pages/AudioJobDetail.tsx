// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useState } from "react";
import { ArrowLeft, Download } from "lucide-react";
import { Link, useParams } from "react-router";

import { useGetAudioJobStatusQuery } from "@/api/api.generated";
import { formatElapsedTimeMillis, formatTimestamp } from "@/lib/timeUtils";
import { cn } from "@/lib/utils";

const TERMINAL_STATES = new Set(["COMPLETED", "FAILED", "CANCELLED"]);

export const AudioJobDetail = () => {
    const { jobId } = useParams<{ jobId: string }>();
    const [pollingInterval, setPollingInterval] = useState(2000);
    const {
        data: jobStatus,
        isLoading,
        error,
    } = useGetAudioJobStatusQuery(
        { jobId: jobId! },
        { pollingInterval, skip: !jobId },
    );

    useEffect(() => {
        if (jobStatus && TERMINAL_STATES.has(jobStatus.state)) {
            setPollingInterval(0);
        }
    }, [jobStatus]);

    const active =
        jobStatus?.state === "QUEUED" || jobStatus?.state === "RUNNING";
    const startedAt = jobStatus ? Date.parse(jobStatus.created_at) : 0;
    const endedAt = jobStatus
        ? active
            ? Date.now()
            : Date.parse(jobStatus.modified_at)
        : 0;

    return (
        <div className="container mx-auto px-4 py-10 sm:px-6">
            <div className="mb-8">
                <Link
                    to="/jobs/audio"
                    className="mb-3 inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
                >
                    <ArrowLeft className="h-4 w-4" aria-hidden="true" />
                    Back to Audio Jobs
                </Link>
                <h1 className="text-3xl font-bold">Audio Job Details</h1>
                <p className="mt-2 break-all font-mono text-sm text-muted-foreground">
                    {jobId}
                </p>
            </div>

            {isLoading ? (
                <p className="text-muted-foreground">Loading job details...</p>
            ) : error || !jobStatus ? (
                <div className="status-error border border-status-border bg-status-bg p-4">
                    <p className="text-status-fg">Error loading job details</p>
                </div>
            ) : (
                <div className="space-y-8">
                    <dl className="grid grid-cols-1 border-y sm:grid-cols-2 lg:grid-cols-3">
                        {[
                            ["Pipeline", jobStatus.pipeline_name],
                            [
                                "Operation",
                                jobStatus.operation === "speech_to_text"
                                    ? "Speech to Text"
                                    : "Text to Speech",
                            ],
                            ["Variant", jobStatus.variant_name],
                            ["Device", jobStatus.device],
                            ["Started", formatTimestamp(startedAt)],
                            [
                                "Elapsed",
                                formatElapsedTimeMillis(Math.max(0, endedAt - startedAt)),
                            ],
                            [
                                "Service latency",
                                jobStatus.service_round_trip_ms == null
                                    ? "-"
                                    : `${jobStatus.service_round_trip_ms.toFixed(2)} ms`,
                            ],
                        ].map(([label, value]) => (
                            <div
                                key={label}
                                className="border-b p-4 last:border-b-0 sm:border-r"
                            >
                                <dt className="text-xs font-medium uppercase text-muted-foreground">
                                    {label}
                                </dt>
                                <dd className="mt-2 break-words text-sm">{value}</dd>
                            </div>
                        ))}
                        <div className="border-b p-4 last:border-b-0 sm:border-r">
                            <dt className="text-xs font-medium uppercase text-muted-foreground">
                                State
                            </dt>
                            <dd className="mt-2">
                                <span
                                    className={cn(
                                        "px-2 py-1 text-xs font-medium bg-status-bg text-status-fg",
                                        jobStatus.state === "COMPLETED"
                                            ? "status-success"
                                            : active
                                                ? "status-info"
                                                : jobStatus.state === "FAILED"
                                                    ? "status-error"
                                                    : "bg-status-neutral-bg text-status-neutral-fg",
                                    )}
                                >
                                    {jobStatus.state}
                                </span>
                            </dd>
                        </div>
                    </dl>

                    {jobStatus.error && (
                        <section aria-labelledby="audio-job-error">
                            <h2 id="audio-job-error" className="mb-2 text-lg font-semibold">
                                Error
                            </h2>
                            <p className="status-error border border-status-border bg-status-bg p-4 text-sm text-status-fg">
                                {jobStatus.error}
                            </p>
                        </section>
                    )}

                    {jobStatus.transcript && (
                        <section aria-labelledby="audio-job-transcript">
                            <h2
                                id="audio-job-transcript"
                                className="mb-2 text-lg font-semibold"
                            >
                                Transcript
                            </h2>
                            <p className="whitespace-pre-wrap break-words border-y py-4 text-sm">
                                {jobStatus.transcript}
                            </p>
                        </section>
                    )}

                    {jobStatus.artifact_url && (
                        <a
                            href={jobStatus.artifact_url}
                            download
                            className="inline-flex items-center gap-2 text-sm font-medium text-status-link hover:text-status-link-hover hover:underline"
                        >
                            <Download className="h-4 w-4" aria-hidden="true" />
                            Download WAV
                        </a>
                    )}
                </div>
            )}
        </div>
    );
};
