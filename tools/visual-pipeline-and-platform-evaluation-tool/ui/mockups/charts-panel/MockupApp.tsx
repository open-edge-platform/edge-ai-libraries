// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useState } from "react";
import { MemoryRouter } from "react-router";
import { useTheme } from "next-themes";
import {
  ChevronDown,
  Moon,
  MoreVertical,
  Pin,
  Redo2,
  Save,
  SlidersHorizontal,
  Sun,
  Undo2,
} from "lucide-react";
import type { Pipeline } from "@/api/api.generated";
import { Navigation } from "@/components/Navigation";
import { PageTitle } from "@/components/PageTitle";
import { BackButton } from "@/components/shared/BackButton";
import { Button } from "@/components/ui/button";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import { Separator } from "@/components/ui/separator";
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { Switch } from "@/components/ui/switch";
import PipelineEditorCanvas from "@/features/pipeline-editor/PipelineEditor";
import RunPipelineButton from "@/features/pipeline-editor/RunPerformanceTestButton";
import StopPipelineButton from "@/features/pipeline-editor/StopPipelineButton";
import { cn } from "@/lib/utils";
import { CurrentPanel } from "./CurrentPanel";
import { OptionAPanel } from "./OptionAPanel";
import { OptionBPanel } from "./OptionBPanel";
import { OptionCPanel } from "./OptionCPanel";
import { OptionDPanel } from "./OptionDPanel";
import { OptionEPanel } from "./OptionEPanel";
import { OptionFPanel } from "./OptionFPanel";
import { OptionGPanel } from "./OptionGPanel";
import { OptionHPanel } from "./OptionHPanel";
import { useFakeMetrics } from "./fakeMetrics";

const VARIANTS = [
  { id: "current", label: "Obecny", Panel: CurrentPanel },
  { id: "a", label: "A · Zakładki", Panel: OptionAPanel },
  { id: "b", label: "B · Sekcje", Panel: OptionBPanel },
  { id: "c", label: "C · Dashboard", Panel: OptionCPanel },
  { id: "d", label: "D · Karty", Panel: OptionDPanel },
  { id: "e", label: "E · Lista + Insights", Panel: OptionEPanel },
  { id: "f", label: "F · Monitor", Panel: OptionFPanel },
  { id: "g", label: "G · Monitor + opisy", Panel: OptionGPanel },
  { id: "h", label: "H · G + okno Insights", Panel: OptionHPanel },
] as const;

type VariantId = (typeof VARIANTS)[number]["id"];

const graph = {
  nodes: [
    {
      id: "1",
      type: "source",
      data: { kind: "video", source: "people-walking.mp4" },
    },
    {
      id: "2",
      type: "gvadetect",
      data: { model: "yolo11n", device: "GPU", "object-class": "person" },
    },
    {
      id: "3",
      type: "gvatrack",
      data: { "tracking-type": "short-term-imageless" },
    },
    {
      id: "4",
      type: "gvaclassify",
      data: { model: "person-attributes", device: "NPU" },
    },
    { id: "5", type: "gvawatermark", data: {} },
    { id: "6", type: "gvafpscounter", data: {} },
    { id: "7", type: "fakesink", data: {} },
  ],
  edges: [1, 2, 3, 4, 5, 6].map((n) => ({
    id: `e${n}`,
    source: String(n),
    target: String(n + 1),
  })),
};

const FAKE_PIPELINE = {
  id: "mockup",
  name: "Smart Parking",
  variants: [
    {
      id: "gpu",
      name: "GPU",
      read_only: true,
      pipeline_graph: graph,
      pipeline_graph_simple: graph,
    },
  ],
} as unknown as Pipeline;

const readVariantFromHash = (): VariantId => {
  const hash = window.location.hash.replace("#", "");
  return VARIANTS.some((v) => v.id === hash) ? (hash as VariantId) : "current";
};

const AppHeader = () => {
  const { theme, setTheme } = useTheme();
  return (
    <header className="flex h-[60px] shrink-0 items-center gap-2 justify-between border-b">
      <div className="flex items-center gap-2 px-4">
        <SidebarTrigger className="-ml-1" />
        <Separator
          orientation="vertical"
          className="mr-2 data-[orientation=vertical]:h-4"
        />
        <h1 className="font-semibold text-lg">
          <PageTitle />
        </h1>
      </div>
      <div className="flex items-center gap-2 px-4">
        <Button
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          aria-label="Toggle theme"
          variant="ghost"
          size="icon"
        >
          {theme === "dark" ? (
            <Sun className="w-5 h-5" />
          ) : (
            <Moon className="w-5 h-5" />
          )}
        </Button>
      </div>
    </header>
  );
};

const MockupSwitcher = ({
  variant,
  onVariant,
  running,
  onRunning,
}: {
  variant: VariantId;
  onVariant: (id: VariantId) => void;
  running: boolean;
  onRunning: (running: boolean) => void;
}) => (
  <div className="fixed bottom-4 left-1/2 z-50 flex -translate-x-1/2 items-center gap-1 whitespace-nowrap bg-neutral-900/95 p-1.5 text-xs text-white shadow-2xl ring-1 ring-white/10">
    <span className="px-2 font-bold uppercase tracking-widest text-white/50">
      Mockup
    </span>
    {VARIANTS.map((v) => (
      <button
        key={v.id}
        type="button"
        onClick={() => onVariant(v.id)}
        className={cn(
          "px-3 py-1.5 font-medium transition-colors",
          variant === v.id ? "bg-white text-neutral-900" : "hover:bg-white/10",
        )}
      >
        {v.label}
      </button>
    ))}
    <span className="mx-1 h-5 w-px bg-white/20" />
    {[true, false].map((state) => (
      <button
        key={String(state)}
        type="button"
        onClick={() => onRunning(state)}
        className={cn(
          "px-3 py-1.5 font-medium transition-colors",
          running === state ? "bg-white text-neutral-900" : "hover:bg-white/10",
        )}
      >
        {state ? "Running" : "Po teście"}
      </button>
    ))}
  </div>
);

const EditorPage = () => {
  const [variant, setVariant] = useState<VariantId>(readVariantFromHash);
  const [running, setRunning] = useState(true);
  const [gpu, setGpu] = useState(0);
  const { history, elapsed } = useFakeMetrics(!running);
  const Panel = VARIANTS.find((v) => v.id === variant)!.Panel;

  useEffect(() => {
    window.history.replaceState(null, "", `#${variant}`);
  }, [variant]);

  return (
    <div className="flex flex-col h-full w-full">
      <header className="flex h-[3.75rem] shrink-0 items-center gap-2 justify-between border-b">
        <div className="flex flex-wrap items-center gap-2 px-2">
          <BackButton to="/pipelines" />
          <span className="font-semibold">{FAKE_PIPELINE.name}</span>
          <Button variant="outline" size="sm" disabled={running}>
            GPU <ChevronDown />
          </Button>
        </div>
        <div className="flex items-center gap-2 px-4">
          <div className="flex items-center gap-2 text-sm">
            <Switch disabled checked={false} />
            Advanced
          </div>
          <Separator orientation="vertical" className="h-6" />
          {[Undo2, Redo2, Save, Pin, SlidersHorizontal].map((Icon, i) => (
            <Button key={i} variant="ghost" size="icon-sm" disabled={i < 3}>
              <Icon className="h-5 w-5" />
            </Button>
          ))}
          <Separator orientation="vertical" className="h-6" />
          {running ? (
            <StopPipelineButton
              isStopping={false}
              onStop={() => setRunning(false)}
            />
          ) : (
            <RunPipelineButton
              isRunning={false}
              onRun={() => setRunning(true)}
            />
          )}
          <Button variant="ghost" size="icon-sm">
            <MoreVertical className="h-5 w-5" />
          </Button>
        </div>
      </header>
      <div className="flex-1 overflow-hidden">
        <ResizablePanelGroup orientation="horizontal" className="w-full h-full">
          <ResizablePanel minSize="30%">
            <PipelineEditorCanvas
              pipelineData={FAKE_PIPELINE}
              variant="gpu"
              isSimpleGraph
              showDetailsPanel
              detailsPanelType="run"
            />
          </ResizablePanel>
          <ResizableHandle withHandle />
          <ResizablePanel defaultSize="55%" minSize="640px">
            <div className="w-full h-full bg-background overflow-hidden relative">
              <Panel
                key={variant}
                history={history}
                elapsed={elapsed}
                running={running}
                gpu={gpu}
                setGpu={setGpu}
              />
            </div>
          </ResizablePanel>
        </ResizablePanelGroup>
      </div>
      <MockupSwitcher
        variant={variant}
        onVariant={setVariant}
        running={running}
        onRunning={setRunning}
      />
    </div>
  );
};

export const MockupApp = () => (
  <MemoryRouter initialEntries={["/pipelines/vision/mockup/gpu"]}>
    <div className="flex flex-col h-screen">
      <SidebarProvider>
        <Navigation />
        <SidebarInset>
          <AppHeader />
          <div className="flex h-full overflow-hidden relative">
            <EditorPage />
          </div>
        </SidebarInset>
      </SidebarProvider>
    </div>
  </MemoryRouter>
);
