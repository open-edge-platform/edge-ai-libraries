import { useLocation } from "react-router";
import { menuItems } from "@/config/navigation.ts";

const getPageTitle = (pathname: string): string => {
  const exactMatch = menuItems.find((item) => item.url === pathname);
  if (exactMatch) return exactMatch.title;

  const partialMatch = menuItems.find(
    (item: { url: string }) =>
      item.url !== "/" && pathname.startsWith(item.url),
  );
  if (partialMatch) return partialMatch.title;

  return "ViPPET";
};

export const PageTitle = () => {
  const location = useLocation();

  const pageTitle = getPageTitle(location.pathname);
  return <>{pageTitle}</>;
};
