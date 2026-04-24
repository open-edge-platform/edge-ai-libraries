import { Outlet, useLocation, matchPath } from "react-router";
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
import { routeConfig, keepAliveRoutes } from "@/config/navigation.ts";
import { BackgroundJobsProvider } from "@/contexts/BackgroundJobsContext";
import { BackgroundJobsWidget } from "@/components/BackgroundJobsWidget";

const Layout = () => {
  usePipelinesLoader();
  useModelsLoader();
  useDevicesLoader();
  const { theme, setTheme } = useTheme();
  const location = useLocation();

  const isRouteActive = (path: string) => {
    if (path === "" && location.pathname === "/") return true;
    if (path === "") return false;
    return matchPath({ path, end: false }, location.pathname);
  };

  return (
    <BackgroundJobsProvider>
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
            <div className="flex h-full overflow-auto relative">
              {routeConfig.map((route, index) => {
                const routePath = route.path ?? "";
                const isKeepAlive = keepAliveRoutes.some((keepAlivePath) =>
                  routePath.startsWith(keepAlivePath.replace(/^\//, "")),
                );
                const isActive = isRouteActive(routePath);

                if (isKeepAlive && route.Component) {
                  const Component = route.Component;
                  return (
                    <div
                      key={`keepalive-${routePath}-${index}`}
                      style={{
                        display: isActive ? "block" : "none",
                        width: "100%",
                        height: "100%",
                      }}
                    >
                      <Component />
                    </div>
                  );
                }
                return null;
              })}
              {!keepAliveRoutes.some((path) =>
                location.pathname.startsWith(path),
              ) && <Outlet />}
            </div>
          </SidebarInset>
        </SidebarProvider>
        <Toaster position="top-center" richColors />
        <BackgroundJobsWidget />
      </div>
    </BackgroundJobsProvider>
  );
};

export { Layout };
