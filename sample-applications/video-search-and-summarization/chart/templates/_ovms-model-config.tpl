{{/*
Resolve the OVMS model-serving parameters that MUST agree between the OVMS
deployment (which registers the models in config.json) and the pipeline-manager
deployment (which tells the captioning/summarization service which OVMS model
names to call). This is the SINGLE SOURCE OF TRUTH — do not recompute any of
this logic inside templates, or the two deployments will drift and the consumer
will reference a model OVMS never registered.

Inputs (dict):
  global    -> .Values.global
  ovmsEnv   -> .Values.ovms.env   (chart-level weight-format overrides)
  parentEnv -> .Values.env        (parent-level overrides; takes precedence)

Returns (consume via `fromYaml`):
  vlmDevice, llmDevice              resolved target devices. The LLM mirrors the
                                    VLM (device + weight + key) when global.llmName
                                    is unset, so no phantom second model is created.
  vlmWeightFormat, llmWeightFormat  explicit override > auto-detect (GPU/NPU->int4, CPU->int8)
  vlmStorageName, llmStorageName    OVMS servable names: {sanitized_model}_{device}[_{format}]
                                    ('OpenVINO/' models are pre-converted -> no format suffix)
  effectiveLlmModel                 global.llmName if set, else global.vlmName
  splitModel                        true when a distinct LLM model/device/format is served
  llmConfigured                     true when global.llmName is set

Usage:
  {{- $ovms := include "vss.ovms.modelConfig" (dict "global" .Values.global "ovmsEnv" .Values.ovms.env "parentEnv" .Values.env) | fromYaml -}}
*/}}
{{- define "vss.ovms.modelConfig" -}}
{{- $global := .global -}}
{{- $ovmsEnv := default (dict) .ovmsEnv -}}
{{- $parentEnv := default (dict) .parentEnv -}}
{{- $vlmDevice := default "CPU" $global.devices.ovms.vlm.device -}}
{{- $llmConfigured := ne (default "" $global.llmName) "" -}}
{{- $llmDevice := ternary (default "CPU" $global.devices.ovms.llm.device) $vlmDevice $llmConfigured -}}
{{- $vlmWeightFormat := default (ternary "int4" "int8" (or (contains "GPU" $vlmDevice) (contains "NPU" $vlmDevice))) (default $ovmsEnv.VLM_WEIGHT_FORMAT $parentEnv.VLM_WEIGHT_FORMAT) -}}
{{- $llmWeightFormat := ternary (default (ternary "int4" "int8" (or (contains "GPU" $llmDevice) (contains "NPU" $llmDevice))) (default $ovmsEnv.LLM_WEIGHT_FORMAT $parentEnv.LLM_WEIGHT_FORMAT)) $vlmWeightFormat $llmConfigured -}}
{{- $vlmSanitized := $global.vlmName | replace "/" "_" | replace ":" "_" | replace " " "_" -}}
{{- $vlmIsOpenvino := hasPrefix "OpenVINO/" $global.vlmName -}}
{{- $vlmStorageName := ternary (printf "%s_%s" $vlmSanitized $vlmDevice) (printf "%s_%s_%s" $vlmSanitized $vlmDevice $vlmWeightFormat) $vlmIsOpenvino -}}
{{- $effectiveLlmModel := default $global.vlmName $global.llmName -}}
{{- $llmSanitized := $effectiveLlmModel | replace "/" "_" | replace ":" "_" | replace " " "_" -}}
{{- $llmIsOpenvino := hasPrefix "OpenVINO/" $effectiveLlmModel -}}
{{- $splitModel := or (ne $effectiveLlmModel $global.vlmName) (ne $llmDevice $vlmDevice) (ne $llmWeightFormat $vlmWeightFormat) -}}
{{- $llmStorageName := $vlmStorageName -}}
{{- if $splitModel -}}
{{- $llmStorageName = ternary (printf "%s_%s" $llmSanitized $llmDevice) (printf "%s_%s_%s" $llmSanitized $llmDevice $llmWeightFormat) $llmIsOpenvino -}}
{{- end -}}
vlmDevice: {{ $vlmDevice | quote }}
llmDevice: {{ $llmDevice | quote }}
vlmWeightFormat: {{ $vlmWeightFormat | quote }}
llmWeightFormat: {{ $llmWeightFormat | quote }}
vlmStorageName: {{ $vlmStorageName | quote }}
llmStorageName: {{ $llmStorageName | quote }}
effectiveLlmModel: {{ $effectiveLlmModel | quote }}
splitModel: {{ $splitModel }}
llmConfigured: {{ $llmConfigured }}
{{- end -}}
