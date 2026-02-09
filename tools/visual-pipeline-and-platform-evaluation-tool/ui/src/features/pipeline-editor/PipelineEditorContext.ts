import { createContext, useContext } from "react";

interface PipelineEditorContextType {
  simpleGraph: boolean;
}

const PipelineEditorContext = createContext<
  PipelineEditorContextType | undefined
>(undefined);

export const usePipelineEditorContext = () => {
  const context = useContext(PipelineEditorContext);
  if (context === undefined) {
    throw new Error(
      "usePipelineEditorContext must be used within PipelineEditorProvider",
    );
  }
  return context;
};

export { PipelineEditorContext };
