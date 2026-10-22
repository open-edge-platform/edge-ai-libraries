import { useLocation } from "react-router";
import { menuItems } from "@/config/navigation.ts";

const getPageTitle = (pathname: string): string => {
  if (pathname.endsWith("/compare")) {
    const parent = menuItems.find(
      (item) => item.url !== "/" && pathname.startsWith(item.url),
    );
    return parent ? `${parent.title} — Comparison` : "Comparison";
  }

  const exactMatch = menuItems.find((item) => item.url === pathname);
  if (exactMatch) return exactMatch.title;

  const partialMatch = menuItems.find(
    (item) => item.url !== "/" && pathname.startsWith(item.url),
  );
  return partialMatch?.title ?? "ViPPET Portal";
};

export const PageTitle = () => <>{getPageTitle(useLocation().pathname)}</>;
