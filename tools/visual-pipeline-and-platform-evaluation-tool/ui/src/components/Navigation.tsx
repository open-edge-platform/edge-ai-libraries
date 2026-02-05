import logoLight from "@/assets/app-logo-classic-blue.svg";
import logoDark from "@/assets/app-logo-energy-blue.svg";
import { useTheme } from "next-themes";
import { NavLink } from "react-router";
import { menuItems } from "@/config/navigation.ts";
import { version } from "../../package.json";

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar";
import type { ComponentProps } from "react";

export const Navigation = ({ ...props }: ComponentProps<typeof Sidebar>) => {
  const { theme } = useTheme();
  const { state } = useSidebar();

  return (
    <Sidebar collapsible="icon" {...props}>
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton className="h-[60px] group-data-[collapsible=icon]:h-[60px] hover:bg-transparent active:bg-transparent pl-[7px]">
              <img
                src={theme === "dark" ? logoDark : logoLight}
                alt="Intel"
                className="h-8 shrink-0"
              />
              <span className="font-semibold text-lg">ViPPET</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent className="flex flex-col gap-2">
            <SidebarMenu>
              {menuItems
                .filter((item) => !item.hidden)
                .map((item) => (
                  <SidebarMenuItem key={item.title}>
                    <NavLink to={item.url} end={item.url === "/"}>
                      {({ isActive }) => (
                        <SidebarMenuButton
                          tooltip={item.title}
                          className={
                            isActive
                              ? "bg-sidebar-accent border-r-3 border-classic-blue dark:border-energy-blue"
                              : ""
                          }
                        >
                          {item.icon && <item.icon />}
                          <span className="px-2">{item.title}</span>
                        </SidebarMenuButton>
                      )}
                    </NavLink>
                  </SidebarMenuItem>
                ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      <SidebarFooter>
        <div
          className={`px-2 py-2 text-xs text-muted-foreground whitespace-nowrap transition-opacity ease-linear group-data-[collapsible=icon]:opacity-0 ${
            state === "collapsed" ? "duration-100" : "duration-200 delay-100"
          }`}
        >
          Version: {version}
        </div>
      </SidebarFooter>
    </Sidebar>
  );
};
