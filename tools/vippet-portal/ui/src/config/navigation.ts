import {
  ChartNoAxesCombined,
  Gauge,
  Grid3x3,
  Home,
  Server,
  type LucideIcon,
} from "lucide-react";
import type { RouteObject } from "react-router";
import { Overview } from "@/pages/Overview.tsx";
import { Instances } from "@/pages/Instances.tsx";
import { Benchmarks } from "@/pages/Benchmarks.tsx";
import { BenchmarkCompare } from "@/pages/BenchmarkCompare.tsx";
import { PerformanceTests } from "@/pages/PerformanceTests.tsx";
import { DensityTests } from "@/pages/DensityTests.tsx";
import { TestCompare } from "@/pages/TestCompare.tsx";

export type NavigationItem = {
  url: string;
  title: string;
  icon?: LucideIcon;
};

export const menuItems: Array<NavigationItem> = [
  { url: "/", title: "Overview", icon: Home },
  { url: "/benchmarks", title: "Benchmarks", icon: ChartNoAxesCombined },
  { url: "/tests/performance", title: "Performance", icon: Gauge },
  { url: "/tests/density", title: "Density", icon: Grid3x3 },
  { url: "/instances", title: "Instances", icon: Server },
];

export const routeConfig: Array<RouteObject> = [
  { index: true, path: "", Component: Overview },
  { path: "instances", Component: Instances },
  { path: "benchmarks", Component: Benchmarks },
  { path: "benchmarks/compare", Component: BenchmarkCompare },
  { path: "tests/performance", Component: PerformanceTests },
  { path: "tests/performance/compare", Component: TestCompare },
  { path: "tests/density", Component: DensityTests },
  { path: "tests/density/compare", Component: TestCompare },
];
