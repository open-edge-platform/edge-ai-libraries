import { useState } from "react";
import { Gpu } from "lucide-react";

interface GpuSelectorProps {
  hasGpu1: boolean;
  onGpuChange: (gpuId: 0 | 1) => void;
  selectedGpu: 0 | 1;
}

export const GpuSelector = ({
  hasGpu1,
  onGpuChange,
  selectedGpu,
}: GpuSelectorProps) => {
  if (!hasGpu1) {
    return null;
  }

  return (
    <div className="flex items-center gap-2 mb-2">
      <Gpu className="h-4 w-4 text-purple-600" />
      <span className="text-sm font-medium text-gray-700">GPU:</span>
      <div className="flex gap-1">
        <button
          onClick={() => onGpuChange(0)}
          className={`px-3 py-1 text-sm font-medium rounded-md transition-colors ${
            selectedGpu === 0
              ? "bg-purple-600 text-white"
              : "bg-gray-200 text-gray-700 hover:bg-gray-300"
          }`}
        >
          GPU 0
        </button>
        <button
          onClick={() => onGpuChange(1)}
          className={`px-3 py-1 text-sm font-medium rounded-md transition-colors ${
            selectedGpu === 1
              ? "bg-purple-600 text-white"
              : "bg-gray-200 text-gray-700 hover:bg-gray-300"
          }`}
        >
          GPU 1
        </button>
      </div>
    </div>
  );
};
