import { useEffect } from "react";
import { useGetPipelinesQuery } from "@/api/api.generated";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import {
  setPipelines,
  selectPipelineNameById,
  selectVariantNameById,
} from "@/store/reducers/pipelines";

/**
 * Hook to ensure pipelines are loaded in the store.
 * Call this in the root layout or main component.
 */
export const usePipelinesLoader = () => {
  const dispatch = useAppDispatch();
  const { data: pipelines } = useGetPipelinesQuery();

  useEffect(() => {
    if (pipelines) {
      dispatch(setPipelines(pipelines));
    }
  }, [pipelines, dispatch]);
};

/**
 * Hook to get a pipeline name by ID from the store.
 * Falls back to the ID if pipeline is not found.
 */
export const usePipelineName = (pipelineId: string): string =>
  useAppSelector((state) => selectPipelineNameById(state, pipelineId));

/**
 * Hook to get a variant name by pipeline ID and variant ID from the store.
 * Falls back to the variant ID if pipeline or variant is not found.
 * Returns undefined if variantId is not provided.
 */
export const useVariantName = (
  pipelineId: string,
  variantId?: string,
): string | undefined =>
  useAppSelector((state) =>
    selectVariantNameById(state, pipelineId, variantId),
  );
