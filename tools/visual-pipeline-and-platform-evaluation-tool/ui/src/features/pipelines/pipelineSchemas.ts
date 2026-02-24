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

export const createPipelineSchema = pipelineMetadataSchema.extend({
  variantName: z.union([variantNameSchema, z.literal("")]),
  pipelineDescription: z.string().min(1, "Pipeline description is required"),
});

export const newVariantSchema = z.object({
  name: variantNameSchema,
});

export type PipelineMetadataFormData = z.infer<typeof pipelineMetadataSchema>;
export type CreatePipelineFormData = z.infer<typeof createPipelineSchema>;
export type NewVariantFormData = z.infer<typeof newVariantSchema>;
