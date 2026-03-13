import { useEffect, useMemo, useState } from "react";
import type { Node } from "@xyflow/react";
import { gvaMetaConvertConfig } from "./nodes/GVAMetaConvertNode.config.ts";
import { gvaTrackConfig } from "@/features/pipeline-editor/nodes/GVATrackNode.config.ts";
import { gvaClassifyConfig } from "@/features/pipeline-editor/nodes/GVAClassifyNode.config.ts";
import { gvaDetectConfig } from "@/features/pipeline-editor/nodes/GVADetectNode.config.ts";
import { sourceNodeConfig } from "./nodes/SourceNode.config.ts";
import { Checkbox } from "@/components/ui/checkbox";
import { useAppSelector } from "@/store/hooks";
import { selectModels } from "@/store/reducers/models";
import DeviceSelect from "@/components/shared/DeviceSelect";
import { useGetCamerasQuery, useGetVideosQuery } from "@/api/api.generated";
import { filterOutTransportStreams } from "@/lib/videoUtils.ts";

type NodePropertyConfig = {
  key: string;
  label: string;
  type: "text" | "number" | "boolean" | "select" | "textarea";
  defaultValue?: unknown;
  options?: string[] | readonly string[];
  description?: string;
  required?: boolean;
  params?: { [key: string]: string };
};

type NodeConfig = {
  editableProperties: NodePropertyConfig[];
};

type SelectOption = {
  label: string;
  value: string;
  disabled?: boolean;
};

type NodeDataPanelProps = {
  selectedNode: Node | null;
  onNodeDataUpdate: (
    nodeId: string,
    updatedData: Record<string, unknown>,
  ) => void;
};

const NodeDataPanel = ({
  selectedNode,
  onNodeDataUpdate,
}: NodeDataPanelProps) => {
  const [editableData, setEditableData] = useState<Record<string, unknown>>({});
  const models = useAppSelector(selectModels);
  const { data: cameras = [] } = useGetCamerasQuery();
  const { data: videos = [] } = useGetVideosQuery();

  const cameraOptions = useMemo<SelectOption[]>(
    () =>
      cameras.map((camera) => {
        const details = camera.details as Record<string, unknown> | undefined;
        let value = "";
        let disabled = false;

        if (camera.device_type === "USB") {
          const devicePath =
            details && typeof details === "object" && "device_path" in details
              ? details["device_path"]
              : undefined;
          value = typeof devicePath === "string" ? devicePath : "";
        } else {
          // NETWORK camera
          const profiles =
            details && typeof details === "object" && "profiles" in details
              ? details["profiles"]
              : undefined;
          const hasProfiles = Array.isArray(profiles) && profiles.length > 0;

          // Disable if network camera is not authorized (no profiles loaded)
          disabled = !hasProfiles;

          const bestProfile =
            details && typeof details === "object" && "best_profile" in details
              ? details["best_profile"]
              : undefined;
          const rtspUrl =
            bestProfile &&
            typeof bestProfile === "object" &&
            "rtsp_url" in (bestProfile as Record<string, unknown>)
              ? (bestProfile as Record<string, unknown>)["rtsp_url"]
              : undefined;
          value = typeof rtspUrl === "string" ? rtspUrl : "";
        }

        return {
          label: camera.device_name,
          value,
          disabled,
        };
      }),
    [cameras],
  );

  const videoOptions = useMemo<SelectOption[]>(
    () =>
      filterOutTransportStreams(videos).map((video) => ({
        label: video.filename,
        value: video.filename,
      })),
    [videos],
  );

  useEffect(() => {
    if (!selectedNode) {
      return;
    }

    const nextData = { ...selectedNode.data } as Record<string, unknown>;
    let shouldSyncNodeData = false;

    if (selectedNode.type === "source") {
      const normalizedKind = normalizeKindValue(nextData.kind);
      if (nextData.kind !== normalizedKind) {
        nextData.kind = normalizedKind;
        shouldSyncNodeData = true;
      }

      const currentSource = String(nextData.source ?? nextData.location ?? "");
      if (!String(nextData.source ?? "") && currentSource) {
        nextData.source = currentSource;
        shouldSyncNodeData = true;
      }
    }

    setEditableData(nextData);

    if (shouldSyncNodeData) {
      onNodeDataUpdate(selectedNode.id, nextData);
    }
  }, [onNodeDataUpdate, selectedNode]);

  const getDefaultSourceValue = (options: SelectOption[]): string => {
    const firstAvailableOption = options.find(
      (option) => !option.disabled && option.value,
    );

    return firstAvailableOption?.value ?? "";
  };

  const ensureCurrentSourceOption = (
    options: SelectOption[],
    currentSource: string,
  ): SelectOption[] => {
    if (!currentSource) {
      return options;
    }

    const hasCurrentSource = options.some(
      (option) => option.value === currentSource,
    );

    if (hasCurrentSource) {
      return options;
    }

    return [{ label: currentSource, value: currentSource }, ...options];
  };

  const normalizeKindValue = (kind: unknown): string => {
    const normalized = String(kind ?? "").toLowerCase();

    if (normalized === "camera") {
      return "camera";
    }

    if (normalized === "file") {
      return "file";
    }

    return String(kind ?? "");
  };

  const isCameraKind = (kind: unknown): boolean =>
    normalizeKindValue(kind) === "camera";

  const handleInputChange = (key: string, value: string | unknown) => {
    if (!selectedNode) {
      return;
    }

    const nextValue = key === "kind" ? normalizeKindValue(value) : value;
    const updatedData = { ...editableData, [key]: nextValue };

    if (selectedNode.type === "source" && key === "kind") {
      const sourceOptions = isCameraKind(nextValue)
        ? cameraOptions
        : videoOptions;
      const defaultSource = getDefaultSourceValue(sourceOptions);
      updatedData.source = defaultSource;
      updatedData.location = defaultSource;
    }

    if (selectedNode.type === "source" && key === "source") {
      updatedData.location = String(nextValue ?? "");
    }

    setEditableData(updatedData);
    onNodeDataUpdate(selectedNode.id, updatedData);
  };

  if (!selectedNode) {
    return (
      <div className="w-full h-full bg-background border-l border-gray-300 p-4">
        <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-200 mb-2">
          Node Data
        </h3>
        <p className="text-xs text-gray-500 dark:text-gray-300">
          Select a node to view its data
        </p>
      </div>
    );
  }

  const getNodeConfig = (nodeType: string): NodeConfig | null => {
    // TODO: change switch to associative array
    switch (nodeType) {
      case "gvametaconvert":
        return gvaMetaConvertConfig;
      case "gvatrack":
        return gvaTrackConfig;
      case "gvaclassify":
        return gvaClassifyConfig;
      case "gvadetect":
        return gvaDetectConfig;
      case "source":
        return sourceNodeConfig;
      default:
        return null;
    }
  };

  const nodeConfig = getNodeConfig(selectedNode.type ?? "");

  const editableProperties = nodeConfig?.editableProperties ?? [];

  // TODO: maybe it should only display defined fields
  const dataEntries = nodeConfig
    ? editableProperties.map((prop) => [
        prop.key,
        editableData[prop.key] ?? prop.defaultValue,
      ])
    : Object.entries(editableData ?? {}).filter(
        // Keys starting with '__' are internal/private properties and should not be displayed to users.
        ([key]) => !["label"].includes(key) && !key.startsWith("__"),
      );

  const hasAdditionalParams = dataEntries.length > 0;

  return (
    <div className="w-full h-full bg-background border-l border-gray-300 p-4 overflow-y-auto">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-200">
          Node Data
        </h3>
        <span className="text-xs text-gray-500 bg-gray-100 dark:text-gray-300 dark:bg-gray-700 px-2 py-1">
          {selectedNode.type}
        </span>
      </div>

      {hasAdditionalParams ? (
        <div className="space-y-3">
          <h4 className="text-xs font-medium text-gray-600 dark:text-gray-300 border-b pb-1">
            Additional Parameters:
          </h4>
          {dataEntries.map(([key, value]) => {
            const keyStr = String(key);
            const sourceSelectValue =
              selectedNode.type === "source" && keyStr === "source"
                ? String(editableData.source ?? editableData.location ?? "")
                : String(value ?? "");

            const propConfig = editableProperties.find(
              (prop) => prop.key === keyStr,
            );
            const inputType =
              propConfig?.type ||
              (typeof value === "object" ? "textarea" : "text");

            return (
              <div key={keyStr} className="border-l-2 border-blue-200 pl-3">
                <label className="text-xs font-medium text-gray-600 dark:text-gray-300 block mb-1">
                  {propConfig?.label ?? keyStr}:
                  {propConfig?.required && (
                    <span className="text-red-500 ml-1">*</span>
                  )}
                </label>

                {propConfig?.description && (
                  <div className="text-xs text-gray-500 dark:text-gray-400 mb-1 italic">
                    {propConfig.description}
                  </div>
                )}

                {keyStr === "model" ? (
                  <select
                    value={String(value ?? "")}
                    onChange={(e) => handleInputChange(keyStr, e.target.value)}
                    className="w-full dark:bg-background text-xs border border-gray-300 px-2 py-1"
                  >
                    <option value="">Select {propConfig?.label}</option>
                    {models
                      .filter(
                        (model) =>
                          model.category === propConfig?.params?.filter,
                      )
                      .map((model) => (
                        <option
                          key={model.name}
                          value={model.display_name ?? model.name}
                        >
                          {model.display_name ?? model.name}
                        </option>
                      ))}
                  </select>
                ) : keyStr === "device" ? (
                  <DeviceSelect
                    value={String(value ?? "")}
                    onChange={(val) => handleInputChange(keyStr, val)}
                    className="w-full bg-background text-xs border border-gray-300 px-2 py-1"
                  />
                ) : (selectedNode.type === "source" && keyStr === "source") ||
                  (selectedNode.type === "filesrc" && keyStr === "location") ? (
                  <select
                    value={sourceSelectValue}
                    onChange={(e) => handleInputChange(keyStr, e.target.value)}
                    className="w-full bg-background text-xs border border-gray-300 px-2 py-1"
                  >
                    {ensureCurrentSourceOption(
                      selectedNode.type === "filesrc"
                        ? videoOptions
                        : isCameraKind(editableData.kind)
                          ? cameraOptions
                          : videoOptions,
                      sourceSelectValue,
                    ).map((option) => (
                      <option
                        key={(option.value || option.label) as string}
                        value={option.value}
                        disabled={Boolean(option.disabled)}
                        className={
                          option.disabled
                            ? "text-gray-400 dark:text-gray-500"
                            : ""
                        }
                      >
                        {option.label}
                        {option.disabled ? " (Not authorized)" : ""}
                      </option>
                    ))}
                  </select>
                ) : inputType === "select" && propConfig?.options ? (
                  <select
                    value={
                      keyStr === "kind"
                        ? normalizeKindValue(value)
                        : String(value ?? "")
                    }
                    onChange={(e) => handleInputChange(keyStr, e.target.value)}
                    className="w-full bg-background text-xs border border-gray-300 px-2 py-1"
                  >
                    {propConfig?.options?.map((option) => (
                      <option key={option} value={option}>
                        {keyStr === "kind"
                          ? normalizeKindValue(option).charAt(0).toUpperCase() +
                            normalizeKindValue(option).slice(1)
                          : option}
                      </option>
                    ))}
                  </select>
                ) : inputType === "boolean" ? (
                  <div className="flex items-center gap-2">
                    <Checkbox
                      checked={Boolean(value)}
                      onCheckedChange={(checked) =>
                        handleInputChange(keyStr, checked)
                      }
                    />
                    <span className="text-xs">{value ? "True" : "False"}</span>
                  </div>
                ) : inputType === "number" ? (
                  <input
                    type="number"
                    value={String(value ?? "")}
                    onChange={(e) =>
                      handleInputChange(
                        keyStr,
                        e.target.value ? Number(e.target.value) : "",
                      )
                    }
                    className="w-full text-xs border border-gray-300 px-2 py-1"
                    placeholder={`Enter ${propConfig?.label ?? keyStr}`}
                  />
                ) : inputType === "textarea" ? (
                  <textarea
                    value={
                      typeof value === "object"
                        ? JSON.stringify(value, null, 2)
                        : String(value ?? "")
                    }
                    onChange={(e) => {
                      if (typeof value === "object") {
                        try {
                          const parsedValue = JSON.parse(e.target.value);
                          handleInputChange(keyStr, parsedValue);
                        } catch {
                          handleInputChange(keyStr, e.target.value);
                        }
                      } else {
                        handleInputChange(keyStr, e.target.value);
                      }
                    }}
                    className="w-full text-xs border border-gray-300 px-2 py-1 font-mono resize-none"
                    rows={3}
                  />
                ) : (
                  <input
                    type="text"
                    value={String(value ?? "")}
                    onChange={(e) => handleInputChange(keyStr, e.target.value)}
                    className="w-full text-xs border border-gray-300 px-2 py-1"
                    placeholder={`Enter ${propConfig?.label ?? keyStr}`}
                  />
                )}
              </div>
            );
          })}
        </div>
      ) : (
        <div className="text-center py-4">
          <p className="text-xs text-gray-500">Nothing to display</p>
        </div>
      )}
    </div>
  );
};

export default NodeDataPanel;
