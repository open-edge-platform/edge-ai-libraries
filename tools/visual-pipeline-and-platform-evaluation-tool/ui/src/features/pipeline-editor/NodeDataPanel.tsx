import { useEffect, useState } from "react";
import type { Node } from "@xyflow/react";
import { gvaMetaConvertConfig } from "./nodes/GVAMetaConvertNode.config.ts";
import { gvaTrackConfig } from "@/features/pipeline-editor/nodes/GVATrackNode.config.ts";
import { gvaClassifyConfig } from "@/features/pipeline-editor/nodes/GVAClassifyNode.config.ts";
import { gvaDetectConfig } from "@/features/pipeline-editor/nodes/GVADetectNode.config.ts";
import { Checkbox } from "@/components/ui/checkbox";
import { useAppSelector } from "@/store/hooks";
import { selectModels } from "@/store/reducers/models";
import DeviceSelect from "@/components/shared/DeviceSelect";

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

  useEffect(() => {
    if (selectedNode) {
      setEditableData({ ...selectedNode.data });
    }
  }, [selectedNode]);

  if (!selectedNode) {
    return (
      <div className="absolute bottom-8 right-4 w-80 bg-white border border-gray-300 shadow-lg p-4 z-10">
        <h3 className="text-sm font-semibold text-gray-700 mb-2">Node Data</h3>
        <p className="text-xs text-gray-500">Select a node to view its data</p>
      </div>
    );
  }

  const handleInputChange = (key: string, value: string | unknown) => {
    const updatedData = { ...editableData, [key]: value };
    setEditableData(updatedData);
    onNodeDataUpdate(selectedNode.id, updatedData);
  };

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
    <div className="absolute bottom-4 right-4 w-80 bg-white border border-gray-300 shadow-lg p-4 z-10 max-h-96 overflow-y-auto">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-gray-700">Node Data</h3>
        <span className="text-xs text-gray-500 bg-gray-100 px-2 py-1">
          {selectedNode.type}
        </span>
      </div>

      {hasAdditionalParams ? (
        <div className="space-y-3">
          <h4 className="text-xs font-medium text-gray-600 border-b pb-1">
            Additional Parameters:
          </h4>
          {dataEntries.map(([key, value]) => {
            const keyStr = String(key);

            const propConfig = editableProperties.find(
              (prop) => prop.key === keyStr,
            );
            const inputType =
              propConfig?.type ||
              (typeof value === "object" ? "textarea" : "text");

            return (
              <div key={keyStr} className="border-l-2 border-blue-200 pl-3">
                <label className="text-xs font-medium text-gray-600 block mb-1">
                  {propConfig?.label ?? keyStr}:
                  {propConfig?.required && (
                    <span className="text-red-500 ml-1">*</span>
                  )}
                </label>

                {propConfig?.description && (
                  <div className="text-xs text-gray-500 mb-1 italic">
                    {propConfig.description}
                  </div>
                )}

                {keyStr === "model" ? (
                  <select
                    value={String(value ?? "")}
                    onChange={(e) => handleInputChange(keyStr, e.target.value)}
                    className="w-full text-xs border border-gray-300 px-2 py-1"
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
                    className="w-full text-xs border border-gray-300 px-2 py-1"
                  />
                ) : inputType === "select" && propConfig?.options ? (
                  <select
                    value={String(value ?? "")}
                    onChange={(e) => handleInputChange(keyStr, e.target.value)}
                    className="w-full text-xs border border-gray-300 px-2 py-1"
                  >
                    <option value="">Select {propConfig?.label}</option>
                    {propConfig?.options?.map((option) => (
                      <option key={option} value={option}>
                        {option}
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
