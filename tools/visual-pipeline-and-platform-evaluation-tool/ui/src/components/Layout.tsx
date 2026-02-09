import { Outlet } from "react-router";
import { Toaster } from "@/components/ui/sonner.tsx";
import { usePipelinesLoader } from "@/hooks/usePipelines.ts";
import { useModelsLoader } from "@/hooks/useModels.ts";
import { useDevicesLoader } from "@/hooks/useDevices.ts";
import { Navigation } from "@/components/Navigation.tsx";
import { PageTitle } from "@/components/PageTitle.tsx";
import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { Button } from "@/components/ui/button.tsx";
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar.tsx";
import { Separator } from "@/components/ui/separator.tsx";

const Layout = () => {
  usePipelinesLoader();
  useModelsLoader();
  useDevicesLoader();
  const { theme, setTheme } = useTheme();

  return (
    <div className="flex flex-col h-screen">
      <SidebarProvider>
        <Navigation />
        <SidebarInset>
          <header className="flex h-[60px] shrink-0 items-center gap-2 justify-between transition-[width,height] ease-linear border-b">
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
          <div className="flex h-full overflow-auto">
            <Outlet />
          </div>
        </SidebarInset>
      </SidebarProvider>
      <Toaster position="top-center" richColors />
    </div>
  );
};

export { Layout };
