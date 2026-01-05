import { usePipelineName } from "@/hooks/usePipelines";
import { Pencil, Save } from "lucide-react";
import { useState } from "react";
import { useUpdatePipelineMutation } from "@/api/api.generated";

interface PipelineNamePropsEdit {
  pipelineId: string;
}

export const PipelineNameEdit = ({ pipelineId }: PipelineNamePropsEdit) => {
  const name = usePipelineName(pipelineId);
  const [isEditing, setIsEditing] = useState(false);
  const [editedName, setEditedName] = useState("");
  const [updatePipeline] = useUpdatePipelineMutation();

  const handleEdit = () => {
    setEditedName(name);
    setIsEditing(true);
  };

  const handleSave = async () => {
    if (editedName.trim() === "") {
      setEditedName(name);
      setIsEditing(false);
      return;
    }
    try {
      await updatePipeline({
        pipelineId,
        pipelineUpdate: {
          name: editedName.trim(),
        },
      }).unwrap();
      setIsEditing(false);
    } catch (error) {
      console.error("Failed to update pipeline name:", error);
    }
  };

  const handleCancel = () => {
    setIsEditing(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      handleSave();
    } else if (e.key === "Escape") {
      handleCancel();
    }
  };

  if (isEditing) {
    return (
      <div className="flex flex-row items-center">
        <input
          type="text"
          value={editedName}
          onChange={(e) => setEditedName(e.target.value)}
          onKeyDown={handleKeyDown}
          className="w-[450px] border border-gray-300 px-2 py-1"
          autoFocus
          aria-label="Edit pipeline name"
        />
        <button
          onClick={handleSave}
          aria-label="Save pipeline name"
          className="mx-2 cursor-pointer"
        >
          <Save className="w-5 h-5" />
        </button>
      </div>
    );
  }

  return (
    <div className="group flex flex-row items-center">
      {name}
      <button
        onClick={handleEdit}
        aria-label="Edit pipeline name"
        className="mx-1 cursor-pointer opacity-0 group-hover:opacity-100 transition-opacity"
      >
        <Pencil className="w-5 h-5" />
      </button>
    </div>
  );
};
