import { useEffect } from "react";
import { useGetModelsQuery } from "@/api/api.generated";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import { setModels, selectModelNameById } from "@/store/reducers/models";

/**
 * Hook to ensure models are loaded in the store.
 * Call this in the root layout or main component.
 */
export const useModelsLoader = () => {
  const dispatch = useAppDispatch();
  const { data: models } = useGetModelsQuery();

  useEffect(() => {
    if (models) {
      dispatch(setModels(models));
    }
  }, [models, dispatch]);
};

/**
 * Hook to get a model name by ID from the store.
 * Falls back to the ID if model is not found.
 */
export const useModelName = (modelId: string): string => {
  return useAppSelector((state) => selectModelNameById(state, modelId));
};
