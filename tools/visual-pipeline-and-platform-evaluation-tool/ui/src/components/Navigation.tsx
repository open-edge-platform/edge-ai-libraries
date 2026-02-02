import logoLight from "@/assets/digital-unboxed-classicblue.svg";
import logoDark from "@/assets/digital-unboxed-energyblue-white.svg";
import { useTheme } from "next-themes";
import { NavLink } from "react-router";
import { menuItems } from "@/config/navigation.ts";

import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";
import type { ComponentProps } from "react";

export const Navigation = ({ ...props }: ComponentProps<typeof Sidebar>) => {
  const { theme } = useTheme();

  return (
    <Sidebar collapsible="icon" {...props}>
      <SidebarHeader>
        <div className="flex items-center gap-2 px-4 h-[60px] group-data-[collapsible=icon]:px-2 transition-[padding] duration-200 ease-linear">
          <img
            src={theme === "dark" ? logoDark : logoLight}
            alt="Intel"
            className="h-7 shrink-0"
          />
          <span className="font-semibold text-lg group-data-[collapsible=icon]:hidden">
            ViPPET
          </span>
        </div>
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
                          <span>{item.title}</span>
                        </SidebarMenuButton>
                      )}
                    </NavLink>
                  </SidebarMenuItem>
                ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
    </Sidebar>
  );
};
