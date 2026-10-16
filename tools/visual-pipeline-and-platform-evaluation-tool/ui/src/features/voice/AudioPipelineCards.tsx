// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { Link } from "react-router";
import type { AudioPipelineResponse } from "@/api/api.generated";
import { Badge } from "@/components/ui/badge";
import {
    Card,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import thumbnailPlaceholder from "@/assets/thumbnail_placeholder.png";

interface AudioPipelineCardsProps {
    pipelines: AudioPipelineResponse[];
    hasError: boolean;
}

export function AudioPipelineCards({
    pipelines,
    hasError,
}: AudioPipelineCardsProps) {
    if (hasError)
        return (
            <p role="alert" className="text-sm text-destructive">
                Unable to load Audio pipelines.
            </p>
        );

    return (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(min(18.75rem,100%),1fr))] gap-4">
            {pipelines.map((pipeline) => {
                const firstVariant = pipeline.variants[0];
                const content = (
                    <Card className="h-full overflow-hidden pt-0 transition-all duration-200 hover:-translate-y-1 hover:shadow-md">
                        <img
                            src={pipeline.thumbnail ?? thumbnailPlaceholder}
                            alt={pipeline.name}
                            className="aspect-video w-full object-cover"
                        />
                        <CardHeader className="space-y-2">
                            <CardTitle>{pipeline.name}</CardTitle>
                            <div className="flex flex-wrap gap-1">
                                {pipeline.tags.map((tag) => (
                                    <Badge key={tag} variant="secondary">
                                        {tag}
                                    </Badge>
                                ))}
                            </div>
                            <CardDescription>{pipeline.description}</CardDescription>
                            {!pipeline.available && (
                                <p className="text-sm text-destructive">
                                    {pipeline.unavailable_reason ?? "Pipeline unavailable."}
                                </p>
                            )}
                        </CardHeader>
                    </Card>
                );
                return pipeline.available && firstVariant ? (
                    <Link
                        key={pipeline.id}
                        to={`/pipelines/audio/${pipeline.id}/${firstVariant.id}`}
                        className="block min-w-0"
                    >
                        {content}
                    </Link>
                ) : (
                    <div
                        key={pipeline.id}
                        aria-disabled="true"
                        className="min-w-0 opacity-70"
                    >
                        {content}
                    </div>
                );
            })}
        </div>
    );
}
