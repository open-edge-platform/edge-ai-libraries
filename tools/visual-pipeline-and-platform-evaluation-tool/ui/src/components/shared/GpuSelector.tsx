interface GpuSelectorProps {
  availableGpus: number[];
  onGpuChange: (gpuId: number) => void;
  selectedGpu: number;
}

export const GpuSelector = ({
  availableGpus,
  onGpuChange,
  selectedGpu,
}: GpuSelectorProps) => {
  if (availableGpus.length <= 1) {
    return null;
  }

  return (
    <div className="flex flex-col justify-evenly h-[240px]">
      {availableGpus.map((gpuId) => (
        <button
          key={gpuId}
          onClick={() => onGpuChange(gpuId)}
          className={`py-1 text-sm font-medium transition-all text-left whitespace-nowrap ${
            selectedGpu === gpuId
              ? "text-gray-900 dark:text-gray-100"
              : "text-gray-400 hover:text-gray-600 dark:text-gray-600 dark:hover:text-gray-400"
          }`}
        >
          GPU {gpuId}
        </button>
      ))}
    </div>
  );
};
