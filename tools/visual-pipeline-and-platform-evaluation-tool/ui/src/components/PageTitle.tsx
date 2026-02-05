import { useLocation, useParams } from "react-router";
import { menuItems } from "@/config/navigation.ts";
import { PipelineNameEdit } from "@/features/pipelines/PipelineNameEdit.tsx";

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
  const params = useParams();

  if (location.pathname.startsWith("/pipelines/") && params.id) {
    return <PipelineNameEdit pipelineId={params.id} />;
  }

  const pageTitle = getPageTitle(location.pathname);
  return <>{pageTitle}</>;
};
