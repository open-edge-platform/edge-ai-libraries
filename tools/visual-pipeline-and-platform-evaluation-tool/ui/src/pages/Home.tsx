import { Link } from "react-router";
import {
  Card,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { CpuUsageProgress } from "@/features/metrics/CpuUsageProgress.tsx";
import { GpuUsageProgress } from "@/features/metrics/GpuUsageProgress.tsx";
import { AddPipelineButton } from "@/features/pipelines/AddPipelineButton.tsx";
import { PipelineCards } from "@/features/pipelines/PipelineCards.tsx";
import { useAppSelector } from "@/store/hooks";
import { selectPipelines } from "@/store/reducers/pipelines";
import { BookOpen, Code, Sparkles } from "lucide-react";
import { selectHasNPU } from "@/store/reducers/devices.ts";
import { NpuUsageProgress } from "@/features/metrics/NpuUsageProgress.tsx";
import { compareDesc } from "date-fns";
import { PipelineCardsLoader } from "@/features/pipelines/PipelineCardsLoader";
import { useGetPipelinesQuery } from "@/api/api.generated";
import { type RefObject, useEffect, useRef, useState } from "react";

/**
 * Calculates how many cards can fit in one row based on the container width.
 * Takes into account the grid's auto-fit behavior with minmax(300px, 1fr) and accounts
 * for the "Create" card. Uses ResizeObserver to recalculate on container resize.
 */
const useVisibleCardsCount = (
  containerRef: RefObject<HTMLDivElement | null>,
) => {
  const [visibleCards, setVisibleCards] = useState<number | undefined>();

  useEffect(() => {
    const calculateVisibleCards = () => {
      if (!containerRef.current) return;

      const gap = 16;
      const minCardWidth = 300;

      const availableWidth = containerRef.current.offsetWidth;

      const maxCardsAtMinWidth = Math.floor(
        (availableWidth + gap) / (minCardWidth + gap),
      );

      const actualCardWidth =
        maxCardsAtMinWidth > 0
          ? (availableWidth - gap * (maxCardsAtMinWidth - 1)) /
            maxCardsAtMinWidth
          : 0;

      const cardsPerRow = Math.floor(
        (availableWidth + gap) / (actualCardWidth + gap),
      );

      const pipelineCardsCount = Math.max(0, cardsPerRow - 1);

      setVisibleCards(pipelineCardsCount);
    };

    calculateVisibleCards();

    const resizeObserver = new ResizeObserver(() => {
      calculateVisibleCards();
    });

    if (containerRef.current) {
      resizeObserver.observe(containerRef.current);
    }

    return () => {
      resizeObserver.disconnect();
    };
  }, [containerRef]);

  return visibleCards;
};

export const Home = () => {
  const { isLoading: isLoadingPipelines } = useGetPipelinesQuery();
  const pipelines = useAppSelector(selectPipelines);
  const containerRef = useRef<HTMLDivElement>(null);
  const maxCards = useVisibleCardsCount(containerRef);

  const sortedPipelines = pipelines
    ? [...pipelines].sort((p1, p2) =>
        compareDesc(new Date(p2.modified_at), new Date(p1.modified_at)),
      )
    : [];

  const hasNpu = useAppSelector(selectHasNPU);

  const userDefinedPipelines =
    pipelines?.filter((p) => p.source === "USER_CREATED") ?? [];

  return (
    <>
      <div className="flex-1 overflow-auto">
        <div className="p-4 space-y-8">
          <div ref={containerRef}>
            <h1 className="font-medium text-2xl mb-4">Pipelines</h1>
            {isLoadingPipelines ? (
              <PipelineCardsLoader count={(maxCards ?? 0) + 1} />
            ) : (
              <PipelineCards pipelines={sortedPipelines} maxCards={maxCards} />
            )}
          </div>

          <div>
            <h1 className="font-medium text-2xl mb-4">
              User Defined Pipelines
            </h1>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
              <AddPipelineButton />
              {userDefinedPipelines.map((pipeline) => (
                <Card
                  key={pipeline.id}
                  className="flex flex-col transition-all duration-200 hover:-translate-y-1 hover:shadow-lg"
                >
                  <CardHeader className="flex-1">
                    <CardTitle>{pipeline.name}</CardTitle>
                    <CardDescription className="line-clamp-4 min-h-18">
                      {pipeline.description}
                    </CardDescription>
                  </CardHeader>
                  <CardFooter>
                    <Link
                      to={`/pipelines/${pipeline.id}`}
                      className="text-white dark:text-[#242528] font-medium bg-classic-blue dark:bg-energy-blue hover:bg-classic-blue-hover dark:hover:bg-energy-blue-tint-1 px-4 py-2 transition-colors"
                    >
                      Open in Builder
                    </Link>
                  </CardFooter>
                </Card>
              ))}
            </div>
          </div>
        </div>
      </div>
      <div className="w-90 border-l p-4 flex flex-col gap-4 bg-sidebar">
        <h1 className="font-medium text-2xl">Resource utilization</h1>
        <CpuUsageProgress />
        <GpuUsageProgress />
        {hasNpu && <NpuUsageProgress />}

        <h1 className="font-medium text-2xl mt-4">Learning and support</h1>

        <div className="flex gap-3">
          <BookOpen className="w-6 h-6 text-classic-blue dark:text-energy-blue shrink-0" />
          <a
            href="https://docs.openedgeplatform.intel.com/2025.2/edge-ai-libraries/visual-pipeline-and-platform-evaluation-tool/index.html"
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-classic-blue dark:hover:text-energy-blue transition-colors"
          >
            <h3 className="font-semibold text-base mb-1">Getting Started</h3>
            <p className="text-sm text-muted-foreground">
              Learn the fundamentals to get the most out of the ViPPET
            </p>
          </a>
        </div>

        <div className="flex gap-3">
          <Sparkles className="w-6 h-6 text-classic-blue dark:text-energy-blue shrink-0" />
          <a
            href="https://docs.openedgeplatform.intel.com/2025.2/edge-ai-libraries/visual-pipeline-and-platform-evaluation-tool/index.html"
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-classic-blue dark:hover:text-energy-blue transition-colors"
          >
            <h3 className="font-semibold text-base mb-1">What's new?</h3>
            <p className="text-sm text-muted-foreground">
              Check out what's new in the latest ViPPET 2025.2 release
            </p>
          </a>
        </div>

        <div className="flex gap-3">
          <Code className="w-6 h-6 text-classic-blue dark:text-energy-blue shrink-0" />
          <a
            href="/api/v1/redoc"
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-classic-blue dark:hover:text-energy-blue transition-colors"
          >
            <h3 className="font-semibold text-base mb-1">REST API</h3>
            <p className="text-sm text-muted-foreground">
              You can use ViPPET also through REST API - see OpenAPI
              specification
            </p>
          </a>
        </div>
      </div>
    </>
  );
};
