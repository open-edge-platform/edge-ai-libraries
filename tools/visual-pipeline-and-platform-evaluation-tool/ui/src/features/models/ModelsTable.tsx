import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table.tsx";
import { Button } from "@/components/ui/button.tsx";
import { Checkbox } from "@/components/ui/checkbox.tsx";
import { useAppSelector } from "@/store/hooks";
import { selectModels } from "@/store/reducers/models";
import { selectPipelinesMap } from "@/store/reducers/pipelines";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Download, Loader2 } from "lucide-react";
import { useModelInstall } from "@/features/models/useModelInstall";
import { ModelInstallStatusIndicator } from "@/features/models/ModelInstallStatusIndicator";
import { ModelInstallButtonSlot } from "@/features/models/ModelInstallButtonSlot";

export const ModelsTable = () => {
  const models = useAppSelector(selectModels);
  const pipelinesMap = useAppSelector(selectPipelinesMap);
  const { pendingDownloads, installModels: runModelInstall } =
    useModelInstall();
  const [selectedNames, setSelectedNames] = useState<ReadonlySet<string>>(
    () => new Set(),
  );

  const installableNames = useMemo(
    () =>
      models
        .filter(
          (m) =>
            m.install_status === "not_installed" ||
            m.install_status === "failed",
        )
        .map((m) => m.name),
    [models],
  );

  const autoSelectedRef = useRef<Set<string>>(new Set());
  useEffect(() => {
    const installable = new Set(installableNames);
    const toAdd: string[] = [];
    for (const m of models) {
      if (
        m.default &&
        installable.has(m.name) &&
        !autoSelectedRef.current.has(m.name)
      ) {
        toAdd.push(m.name);
        autoSelectedRef.current.add(m.name);
      }
    }
    if (toAdd.length > 0) {
      setSelectedNames((prev) => {
        const next = new Set(prev);
        for (const n of toAdd) next.add(n);
        return next;
      });
    }
  }, [models, installableNames]);

  const effectiveSelection = useMemo(() => {
    const installable = new Set(installableNames);
    return new Set([...selectedNames].filter((n) => installable.has(n)));
  }, [selectedNames, installableNames]);

  const toggleSelected = useCallback((modelName: string, value: boolean) => {
    setSelectedNames((prev) => {
      const next = new Set(prev);
      if (value) next.add(modelName);
      else next.delete(modelName);
      return next;
    });
  }, []);

  const toggleSelectAll = useCallback(
    (value: boolean) => {
      setSelectedNames(value ? new Set(installableNames) : new Set());
    },
    [installableNames],
  );

  const installSelectedModels = useCallback(
    async (names: readonly string[]) => {
      if (names.length === 0) return;
      await runModelInstall(names);
      setSelectedNames((prev) => {
        const next = new Set(prev);
        for (const n of names) next.delete(n);
        return next;
      });
    },
    [runModelInstall],
  );

  const handleInstall = useCallback(
    (modelName: string) => installSelectedModels([modelName]),
    [installSelectedModels],
  );

  const handleInstallSelected = useCallback(
    () => installSelectedModels([...effectiveSelection]),
    [effectiveSelection, installSelectedModels],
  );

  return (
    <>
      <div className="mb-3 flex items-center justify-end gap-3">
        <span className="text-sm text-muted-foreground">
          {effectiveSelection.size > 0
            ? `${effectiveSelection.size} model${effectiveSelection.size === 1 ? "" : "s"} selected`
            : "Select one or more available models to install"}
        </span>
        <Button
          size="sm"
          disabled={
            effectiveSelection.size === 0 ||
            [...effectiveSelection].some((n) => pendingDownloads.has(n))
          }
          onClick={handleInstallSelected}
        >
          {[...effectiveSelection].some((n) => pendingDownloads.has(n)) ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <Download className="size-4" />
          )}
          Install
          {effectiveSelection.size > 0 ? ` (${effectiveSelection.size})` : ""}
        </Button>
      </div>

      <Table className="mb-10">
        <TableHeader>
          <TableRow>
            <TableHead className="w-8">
              <Checkbox
                aria-label="Select all installable models"
                disabled={installableNames.length === 0}
                checked={
                  installableNames.length > 0 &&
                  effectiveSelection.size === installableNames.length
                    ? true
                    : effectiveSelection.size > 0
                      ? "indeterminate"
                      : false
                }
                onCheckedChange={(value) => toggleSelectAll(value === true)}
              />
            </TableHead>
            <TableHead className="w-[33%] truncate">Name</TableHead>
            <TableHead>Category</TableHead>
            <TableHead>Source</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Precisions</TableHead>
            <TableHead>Used by</TableHead>
            <TableHead className="text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {models.map((model) => {
            const isPending = pendingDownloads.has(model.name);
            const canInstall =
              model.install_status === "not_installed" ||
              model.install_status === "failed";
            const isChecked = effectiveSelection.has(model.name);
            return (
              <TableRow key={model.name}>
                <TableCell>
                  <Checkbox
                    aria-label={`Select ${model.display_name}`}
                    disabled={!canInstall || isPending}
                    checked={isChecked}
                    onCheckedChange={(value) =>
                      toggleSelected(model.name, value === true)
                    }
                  />
                </TableCell>
                <TableCell className="font-medium max-w-0">
                  <div className="truncate" title={model.display_name}>
                    {model.display_name}
                  </div>
                </TableCell>
                <TableCell>{model.category ?? "-"}</TableCell>
                <TableCell>{model.source}</TableCell>
                <TableCell>
                  <ModelInstallStatusIndicator status={model.install_status} />
                </TableCell>
                <TableCell>
                  {Array.from(
                    new Set(
                      model.variants
                        ?.map((v) => v.precision)
                        .filter((p): p is string => Boolean(p)) ?? [],
                    ),
                  ).join(", ") || "-"}
                </TableCell>
                <TableCell className="whitespace-pre-line">
                  {(model.used_by_pipelines ?? [])
                    .map(
                      (pipelineId) =>
                        pipelinesMap.get(pipelineId)?.name ?? pipelineId,
                    )
                    .join("\n") || "-"}
                </TableCell>
                <TableCell className="text-right">
                  <ModelInstallButtonSlot
                    showButton={canInstall && !isPending}
                    onInstall={() => handleInstall(model.name)}
                  />
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </>
  );
};
