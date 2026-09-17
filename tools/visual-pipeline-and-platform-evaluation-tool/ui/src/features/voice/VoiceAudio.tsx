// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useState } from "react";
import {
    Bar,
    BarChart,
    ReferenceLine,
    ResponsiveContainer,
    YAxis,
} from "recharts";

interface AudioPreview {
    src: string;
    duration: number;
    peaks: { amplitude: [number, number] }[];
}

export function VoiceAudio({
    src,
    label,
    title,
}: {
    src: string;
    label: string;
    title: string;
}) {
    const [preview, setPreview] = useState<AudioPreview | null>(null);
    const [failedSrc, setFailedSrc] = useState<string | null>(null);
    const current = preview?.src === src ? preview : null;

    useEffect(() => {
        const controller = new AbortController();
        async function decode() {
            try {
                const response = await fetch(src, { signal: controller.signal });
                const content = await response.arrayBuffer();
                controller.signal.throwIfAborted();
                const context = new OfflineAudioContext(1, 1, 16000);
                const audio = await context.decodeAudioData(content);
                controller.signal.throwIfAborted();
                const samples = audio.getChannelData(0);
                const binSize = Math.max(1, Math.ceil(samples.length / 160));
                const peaks: AudioPreview["peaks"] = [];
                for (let start = 0; start < samples.length; start += binSize) {
                    let peak = 0;
                    const end = Math.min(start + binSize, samples.length);
                    const stride = Math.max(1, Math.floor(binSize / 128));
                    for (let index = start; index < end; index += stride) {
                        peak = Math.max(peak, Math.abs(samples[index]));
                    }
                    peaks.push({ amplitude: [-peak, peak] });
                }
                setPreview({ src, duration: audio.duration, peaks });
            } catch {
                if (!controller.signal.aborted) setFailedSrc(src);
            }
        }
        void decode();
        return () => controller.abort();
    }, [src]);

    return (
        <div className="min-w-0 space-y-3 rounded-sm border border-border p-3 sm:p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                    <h3 className="text-sm font-semibold">{title}</h3>
                    {current && (
                        <p className="text-xs text-muted-foreground">
                            {Math.floor(current.duration / 60)}:
                            {Math.floor(current.duration % 60)
                                .toString()
                                .padStart(2, "0")}{" "}
                            / WAV
                        </p>
                    )}
                </div>
            </div>
            <div
                className="h-16 min-w-0 bg-muted"
                role="img"
                aria-label={`${title} waveform`}
                aria-busy={!current && failedSrc !== src}
            >
                {current ? (
                    <ResponsiveContainer width="100%" height="100%">
                        <BarChart
                            data={current.peaks}
                            margin={{ top: 4, bottom: 4, left: 0, right: 0 }}
                            barCategoryGap="20%"
                            accessibilityLayer={false}
                        >
                            <YAxis hide domain={[-1, 1]} />
                            <ReferenceLine
                                y={0}
                                stroke="var(--brand-accent)"
                                strokeOpacity={0.3}
                            />
                            <Bar
                                dataKey="amplitude"
                                fill="var(--brand-accent)"
                                isAnimationActive={false}
                            />
                        </BarChart>
                    </ResponsiveContainer>
                ) : (
                    <p className="flex h-full items-center justify-center text-xs text-muted-foreground">
                        {failedSrc === src ? "Waveform unavailable" : "Loading waveform"}
                    </p>
                )}
            </div>
            <audio
                key={src}
                aria-label={label}
                src={src}
                controls
                preload="auto"
                className="h-10 w-full min-w-0"
            />
        </div>
    );
}
