import { createBrowserRouter, redirect } from "react-router";
import Home from "@/pages/Home.tsx";
import Pipelines from "@/pages/Pipelines.tsx";
import Layout from "@/Layout.tsx";
import Models from "@/pages/Models.tsx";
import Videos from "@/pages/Videos.tsx";
import PerformanceTests from "@/pages/PerformanceTests.tsx";
import DensityTests from "@/pages/DensityTests.tsx";
import Jobs from "@/pages/Jobs.tsx";
import PerformanceJobDetail from "@/pages/PerformanceJobDetail.tsx";
import DensityJobDetail from "@/pages/DensityJobDetail.tsx";
import OptimizationJobDetail from "@/pages/OptimizationJobDetail.tsx";

export default createBrowserRouter([
  {
    path: "/",
    Component: Layout,
    children: [
      { index: true, Component: Home },
      { path: "pipelines/:id", Component: Pipelines },
      { path: "models", Component: Models },
      { path: "videos", Component: Videos },
      { path: "tests/performance", Component: PerformanceTests },
      { path: "tests/density", Component: DensityTests },
      {
        path: "jobs",
        loader: () => redirect("/jobs/performance"),
      },
      { path: "jobs/performance", Component: Jobs },
      { path: "jobs/performance/:jobId", Component: PerformanceJobDetail },
      { path: "jobs/density", Component: Jobs },
      { path: "jobs/density/:jobId", Component: DensityJobDetail },
      { path: "jobs/optimize", Component: Jobs },
      { path: "jobs/optimize/:jobId", Component: OptimizationJobDetail },
    ],
  },
]);
