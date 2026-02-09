import { createBrowserRouter } from "react-router";
import { routeConfig } from "@/config/navigation.ts";
import { Layout } from "@/components/Layout.tsx";

export default createBrowserRouter([
  {
    path: "/demo",
    Component: DemoMode,
  },
  {
    path: "/",
    Component: Layout,
    children: routeConfig,
  },
]);
