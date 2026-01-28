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
import AddPipelineButton from "@/features/pipelines/AddPipelineButton.tsx";
import CopyPipelineButton from "@/features/pipelines/CopyPipelineButton.tsx";
import { useAppSelector } from "@/store/hooks";
import { selectPipelines } from "@/store/reducers/pipelines";
import { BookOpen, Code, Sparkles } from "lucide-react";
import pipeline0 from "@/assets/pipeline_0.png";
import pipeline1 from "@/assets/pipeline_1.png";
import pipeline2 from "@/assets/pipeline_2.png";
import pipeline3 from "@/assets/pipeline_3.png";
import pipeline4 from "@/assets/pipeline_4.png";
import pipeline5 from "@/assets/pipeline_5.png";
import pipeline6 from "@/assets/pipeline_6.png";
import type { Pipeline } from "@/api/api.generated";
import { selectHasNPU } from "@/store/reducers/devices.ts";
import { NpuUsageProgress } from "@/features/metrics/NpuUsageProgress.tsx";

const pipelineImages = [
  pipeline0,
  pipeline1,
  pipeline2,
  pipeline3,
  pipeline4,
  pipeline5,
  pipeline6,
];

const Home = () => {
  const pipelines = useAppSelector(selectPipelines);

  const hasNpu = useAppSelector(selectHasNPU);

  const predefinedPipelines =
    pipelines?.filter((p) => p.source === "PREDEFINED") ?? [];
  const userDefinedPipelines =
    pipelines?.filter((p) => p.source === "USER_CREATED") ?? [];

  const groupedPredefinedPipelines = predefinedPipelines.reduce(
    (acc, pipeline) => {
      const match = pipeline.name.match(/^(.+?)\s*(\[.+?])?$/);
      const baseName = match ? match[1].trim() : pipeline.name;
      const tag = match && match[2] ? match[2].replace(/[[\]]/g, "") : null;

      const existing = acc.find((group) => group.baseName === baseName);
      if (existing) {
        if (tag) {
          existing.pipelines[tag] = pipeline;
        }
      } else {
        acc.push({
          baseName,
          pipelines: tag ? { [tag]: pipeline } : {},
          // Use the first pipeline's data for display
          id: pipeline.id, // this is only used for react key/id purposes
          description: pipeline.description,
        });
      }
      return acc;
    },
    [] as Array<{
      baseName: string;
      pipelines: Record<string, Pipeline>;
      id: string;
      description: string;
    }>,
  );

  if (pipelines.length > 0) {
    return (
      <div className="flex h-full">
        <div className="flex-1 overflow-auto">
          <div className="p-4 space-y-8">
            <div>
              <h1 className="font-medium text-2xl mb-4">
                Predefined Pipelines
              </h1>
              <div className="grid gap-4 grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
                {groupedPredefinedPipelines.map((group, idx) => (
                  <Card
                    key={group.id}
                    className="flex flex-col transition-all duration-200 hover:-translate-y-1 hover:shadow-lg overflow-hidden"
                  >
                    <CardHeader className="flex-1">
                      <CardTitle className="min-h-8">
                        {group.baseName}
                      </CardTitle>
                      <img
                        src={pipelineImages[idx]}
                        alt={group.baseName}
                        className="w-full h-full"
                      />
                      <CardDescription className="line-clamp-4 min-h-18">
                        {group.description}
                      </CardDescription>
                    </CardHeader>
                    <CardFooter>
                      <CopyPipelineButton
                        pipelines={group.pipelines}
                        baseName={group.baseName}
                        description={group.description}
                      >
                        <button className="cursor-pointer font-medium text-white dark:text-[#242528] bg-classic-blue dark:bg-energy-blue hover:bg-classic-blue-hover dark:hover:bg-energy-blue-tint-1 px-4 py-2 transition-colors">
                          Copy pipeline
                        </button>
                      </CopyPipelineButton>
                    </CardFooter>
                  </Card>
                ))}
              </div>
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
                      <CardDescription className="line-clamp-4 min-h-[4.5rem]">
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
        <div className="w-[25%] border-l p-4 flex flex-col gap-4 bg-[#F9F9F9] dark:bg-[#3c3e42]">
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
      </div>
    );
  }

  return <div>Loading pipelines...</div>;
};

export default Home;
