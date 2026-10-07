// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { Clock, Timer } from "lucide-react";
import { MetricCard } from "@/features/metrics/MetricCard";

export interface ConversionMetrics {
    requestMs: number;
    serviceMs: number | null;
}

export function VoiceMetrics({
    label,
    metrics,
}: {
    label: string;
    metrics: ConversionMetrics | null;
}) {
    if (!metrics) return null;
    return (
        <section aria-label={label} className="space-y-4">
            <h2 className="text-lg font-semibold">{label}</h2>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <MetricCard
                    title="Request duration"
                    value={metrics.requestMs}
                    unit="ms"
                    icon={<Clock className="h-6 w-6 text-orange-chart" />}
                />
                {metrics.serviceMs !== null ? (
                    <MetricCard
                        title="Service round trip"
                        value={metrics.serviceMs}
                        unit="ms"
                        icon={<Timer className="h-6 w-6 text-green-chart" />}
                    />
                ) : (
                    <p className="text-muted-foreground self-center p-4 text-sm">
                        Service round trip unavailable
                    </p>
                )}
            </div>
        </section>
    );
}
