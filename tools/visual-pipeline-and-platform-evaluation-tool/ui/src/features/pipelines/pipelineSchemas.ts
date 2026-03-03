import { z } from "zod";

export const pipelineMetadataSchema = z.object({
  name: z
    .string()
    .min(3, "Name must be at least 3 characters")
    .max(20, "Name must be at most 20 characters"),
  description: z.string().min(1, "Description is required"),
  tags: z.array(z.string()).min(1, "At least one tag is required"),
});

export const variantNameSchema = z
  .string()
  .min(3, "Variant name must be at least 3 characters");

export const createPipelineSchema = pipelineMetadataSchema
  .extend({
    variantName: z.union([variantNameSchema, z.literal("")]),
    pipelineDescription: z.string(),
    templateId: z.string(),
    sourceFileName: z.string(),
    detectionModel: z.string(),
    classificationModel: z.string(),
  })
  .refine(
    (data) => {
      if (data.pipelineDescription && data.pipelineDescription.trim()) {
        return data.pipelineDescription.trim().length > 0;
      }
      return true;
    },
    {
      message: "Pipeline description is required",
      path: ["pipelineDescription"],
    },
  )
  .refine(
    (data) => {
      if (!data.pipelineDescription || !data.pipelineDescription.trim()) {
        return data.templateId && data.templateId.trim().length > 0;
      }
      return true;
    },
    {
      message: "Please select a template",
      path: ["templateId"],
    },
  )
  .refine(
    (data) => {
      if (data.templateId && data.templateId.trim()) {
        return data.sourceFileName && data.sourceFileName.trim().length > 0;
      }
      return true;
    },
    {
      message: "Source filename is required",
      path: ["sourceFileName"],
    },
  )
  .refine(
    (data) => {
      if (data.templateId && data.templateId.trim()) {
        return data.detectionModel && data.detectionModel.trim().length > 0;
      }
      return true;
    },
    {
      message: "Detection model is required",
      path: ["detectionModel"],
    },
  )
  .refine(
    (data) => {
      if (data.templateId?.toLowerCase() === "detect-classify") {
        return (
          data.classificationModel && data.classificationModel.trim().length > 0
        );
      }
      return true;
    },
    {
      message: "Classification model is required",
      path: ["classificationModel"],
    },
  );

export const newVariantSchema = z.object({
  name: variantNameSchema,
});

export type PipelineMetadataFormData = z.infer<typeof pipelineMetadataSchema>;
export type CreatePipelineFormData = z.infer<typeof createPipelineSchema>;
export type NewVariantFormData = z.infer<typeof newVariantSchema>;
