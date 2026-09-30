import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table.tsx";
import { useAppSelector } from "@/store/hooks";
import { selectModels } from "@/store/reducers/models";
import { useMemo } from "react";
import { Download, EllipsisVertical, Trash2 } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu.tsx";
import { ModelInstallStatusIndicator } from "@/features/models/ModelInstallStatusIndicator";
import type { ModelCategory } from "@/api/api.generated.ts";

type ModelsTableProps = {
  /** Only models whose `category` matches this value are shown (`null` = uncategorized). */
  category: ModelCategory | null;
  pendingDownloads: ReadonlySet<string>;
  onInstallOne: (modelName: string) => void;
};

export const ModelsTable = ({
  category,
  pendingDownloads,
  onInstallOne,
}: ModelsTableProps) => {
  const allModels = useAppSelector(selectModels);
  const models = useMemo(
    () => allModels.filter((m) => (m.category ?? null) === category),
    [allModels, category],
  );
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-[20%]">Name</TableHead>
          <TableHead className="w-28">Source</TableHead>
          <TableHead className="w-32">Precisions</TableHead>
          <TableHead className="w-24">Status</TableHead>
          <TableHead className="w-10 text-right">Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {models.map((model) => {
          const isPending = pendingDownloads.has(model.name);
          const canInstall =
            model.install_status === "not_installed" ||
            model.install_status === "failed";
          return (
            <TableRow key={model.name} className="odd:bg-muted/30">
              <TableCell className="font-medium max-w-0 whitespace-normal break-words">
                <div
                  title={model.description ?? undefined}
                  className="whitespace-normal break-words"
                >
                  {model.display_name}
                </div>
              </TableCell>
              <TableCell>{model.source}</TableCell>
              <TableCell>
                {Array.from(
                  new Set(
                    model.variants
                      ?.map((v) => v.precision)
                      .filter((p): p is string => Boolean(p)) ?? [],
                  ),
                ).join(", ") || "-"}
              </TableCell>
              <TableCell>
                <ModelInstallStatusIndicator status={model.install_status} />
              </TableCell>
              <TableCell className="text-right">
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <button
                      type="button"
                      aria-label={`Actions for ${model.display_name}`}
                      title="Model actions"
                      className="inline-flex size-8 items-center justify-center rounded hover:bg-accent"
                    >
                      <EllipsisVertical className="size-4" />
                    </button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem
                      disabled={!canInstall || isPending}
                      onClick={() => onInstallOne(model.name)}
                    >
                      <Download className="size-4" />
                      Install
                    </DropdownMenuItem>
                    <DropdownMenuItem disabled>
                      <Trash2 className="size-4" />
                      Uninstall
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
};
