import { createBrowserRouter } from "react-router";
import { Layout } from "@/Layout.tsx";
import { routeConfig } from "@/config/navigation.ts";

export default createBrowserRouter([
  {
    path: "/",
    Component: Layout,
    children: routeConfig,
  },
]);
