import { generatedApi } from "./portalApi.generated";

export * from "./portalApi.generated";

// Side effects of these endpoints reach other resources, which OpenAPI tags cannot express.
export const portalApi = generatedApi.enhanceEndpoints({
  endpoints: {
    addInstance: { invalidatesTags: ["instances", "benchmarks", "tests"] },
    updateInstance: { invalidatesTags: ["instances", "benchmarks", "tests"] },
    deleteInstance: {
      invalidatesTags: ["instances", "benchmarks", "experiments", "tests"],
    },
    startExperiment: { invalidatesTags: ["experiments", "benchmarks"] },
    startTestExperiment: { invalidatesTags: ["experiments", "tests"] },
    getPipelineCatalog: { providesTags: ["instances"] },
  },
});
