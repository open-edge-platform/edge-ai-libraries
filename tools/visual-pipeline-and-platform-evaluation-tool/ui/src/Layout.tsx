import { Outlet } from "react-router";
import { Toaster } from "@/components/ui/sonner.tsx";
import Navigation from "@/components/shared/Navigation.tsx";
import { usePipelinesLoader } from "@/hooks/usePipelines.ts";
import { useModelsLoader } from "@/hooks/useModels.ts";
import { useDevicesLoader } from "@/hooks/useDevices.ts";

const Layout = () => {
  usePipelinesLoader();
  useModelsLoader();
  useDevicesLoader();

  return (
    <div className="flex flex-col h-screen">
      <Navigation />
      <div className="flex-1 overflow-hidden">
        <Outlet />
      </div>
      <Toaster position="top-center" richColors />
    </div>
  );
};

export default Layout;
