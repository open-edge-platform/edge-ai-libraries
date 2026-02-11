import type { LucideIcon } from "lucide-react";
import { Cpu, Film, Gauge, Grid3x3, Home, ListTodo } from "lucide-react";
import { redirect, type RouteObject } from "react-router";
import { Home as HomePage } from "@/pages/Home.tsx";
import { Pipelines } from "@/pages/Pipelines.tsx";
import { Models } from "@/pages/Models.tsx";
import { Videos } from "@/pages/Videos.tsx";
import { PerformanceTests } from "@/pages/PerformanceTests.tsx";
import { DensityTests } from "@/pages/DensityTests.tsx";
import { Jobs } from "@/pages/Jobs.tsx";
import { PerformanceJobDetail } from "@/pages/PerformanceJobDetail.tsx";
import { DensityJobDetail } from "@/pages/DensityJobDetail.tsx";
import { OptimizationJobDetail } from "@/pages/OptimizationJobDetail.tsx";

export type NavigationItem = {
  url: string;
  title: string;
  icon?: LucideIcon;
  hidden?: boolean;
};

export const menuItems: Array<NavigationItem> = [
  { url: "/", title: "Pipelines", icon: Home },
  { url: "/models", title: "Models", icon: Cpu },
  { url: "/videos", title: "Videos", icon: Film },
  {
    url: "/tests/performance",
    title: "Performance",
    icon: Gauge,
  },
  { url: "/tests/density", title: "Density", icon: Grid3x3 },
  { url: "/jobs", title: "Jobs", icon: ListTodo },
  {
    url: "/pipelines/",
    title: "Pipeline Editor",
    hidden: true,
  },
];

export const routeConfig: Array<RouteObject> = [
  { index: true, path: "", Component: HomePage },
  { path: "pipelines/:id", Component: Pipelines },
  { path: "models", Component: Models },
  { path: "videos", Component: Videos },
  { path: "tests/performance", Component: PerformanceTests },
  { path: "tests/density", Component: DensityTests },
  {
    path: "jobs",
    Component: Jobs,
    loader: () => redirect("/jobs/performance"),
  },
  { path: "jobs/performance", Component: Jobs },
  { path: "jobs/performance/:jobId", Component: PerformanceJobDetail },
  { path: "jobs/density", Component: Jobs },
  { path: "jobs/density/:jobId", Component: DensityJobDetail },
  { path: "jobs/optimize", Component: Jobs },
  { path: "jobs/optimize/:jobId", Component: OptimizationJobDetail },
];
