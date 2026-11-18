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
  vlmWeightFormat, llmWeightFormat  explicit override > auto-detect (GPU/NPU->int4, CPU->int8),
                                    then the precision in an 'OpenVINO/*-<fmt>-*' repo name
                                    wins, and NPU is forced to int4 (mirrors setup.sh)
  vlmStorageName, llmStorageName    OVMS servable names: {sanitized_model}_{device}[_{format}]
                                    ('OpenVINO/' models are pre-converted -> no format suffix)
  effectiveLlmModel                 global.llmName if set, else global.vlmName
  splitModel                        true when a distinct LLM model/device/format is served
  llmConfigured                     true when global.llmName is set
  llmOnNpu                          true when the OVMS LLM device is exactly NPU
  npuMaxPromptLen, npuMinResponseLen
                                    NPU LLM token limits written to graph.pbtxt
                                    plugin_config (OVMS_NPU_MAX_PROMPT_LEN, default
                                    8192 / OVMS_NPU_MIN_RESPONSE_LEN, default 1024)
  npuLlmContextChars                pipeline-manager LLM input budget in chars that
                                    fits npuMaxPromptLen: (tokens - 256) * 2
                                    (mirrors setup.sh apply_ovms_npu_llm_limits)

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
{{- $vlmRepoWeightFormat := include "vss.ovms.repoWeightFormat" $global.vlmName -}}
{{- if $vlmRepoWeightFormat -}}{{- $vlmWeightFormat = $vlmRepoWeightFormat -}}{{- end -}}
{{- if eq (upper $vlmDevice) "NPU" -}}{{- $vlmWeightFormat = "int4" -}}{{- end -}}
{{- $llmWeightFormat := $vlmWeightFormat -}}
{{- if $llmConfigured -}}
{{- $llmWeightFormat = default (ternary "int4" "int8" (or (contains "GPU" $llmDevice) (contains "NPU" $llmDevice))) (default $ovmsEnv.LLM_WEIGHT_FORMAT $parentEnv.LLM_WEIGHT_FORMAT) -}}
{{- $llmRepoWeightFormat := include "vss.ovms.repoWeightFormat" $global.llmName -}}
{{- if $llmRepoWeightFormat -}}{{- $llmWeightFormat = $llmRepoWeightFormat -}}{{- end -}}
{{- if eq (upper $llmDevice) "NPU" -}}{{- $llmWeightFormat = "int4" -}}{{- end -}}
{{- end -}}
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
{{- $npuMaxPromptLen := toString (default "8192" (default $ovmsEnv.OVMS_NPU_MAX_PROMPT_LEN $parentEnv.OVMS_NPU_MAX_PROMPT_LEN)) -}}
{{- if or (not (regexMatch "^[1-9][0-9]*$" $npuMaxPromptLen)) (le (atoi $npuMaxPromptLen) 512) -}}
{{- fail (printf "ovms.env.OVMS_NPU_MAX_PROMPT_LEN must be an integer greater than 512 (got '%s')" $npuMaxPromptLen) -}}
{{- end -}}
{{- $npuMinResponseLen := toString (default "1024" (default $ovmsEnv.OVMS_NPU_MIN_RESPONSE_LEN $parentEnv.OVMS_NPU_MIN_RESPONSE_LEN)) -}}
{{- if not (regexMatch "^[1-9][0-9]*$" $npuMinResponseLen) -}}
{{- fail (printf "ovms.env.OVMS_NPU_MIN_RESPONSE_LEN must be a positive integer (got '%s')" $npuMinResponseLen) -}}
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
llmOnNpu: {{ eq (upper $llmDevice) "NPU" }}
npuMaxPromptLen: {{ $npuMaxPromptLen | quote }}
npuMinResponseLen: {{ $npuMinResponseLen | quote }}
npuLlmContextChars: {{ mul (sub (atoi $npuMaxPromptLen) 256) 2 | toString | quote }}
{{- end -}}


{{/*
Precision baked into a pre-converted OpenVINO/* repo name (e.g.
OpenVINO/<model>-int8-ov -> int8, OpenVINO/<model>-int4-cw-ov -> int4).
model-download pulls these repos by that token and cannot re-quantize them, so
it overrides the device default / user override. Returns "" for other models.
Fails on nf4, which model-download cannot fetch. Mirrors setup.sh
use_openvino_model_weight_format.
*/}}
{{- define "vss.ovms.repoWeightFormat" -}}
{{- if hasPrefix "OpenVINO/" . -}}
{{- $fmt := regexFind "-(int4|int8|fp16|fp32|nf4)(-|$)" (lower (base .)) | trimAll "-" -}}
{{- if eq $fmt "nf4" -}}
{{- fail (printf "%s is pre-converted as nf4, which model-download cannot fetch. Use an int4/int8/fp16 variant of this model." .) -}}
{{- end -}}
{{- $fmt -}}
{{- end -}}
{{- end -}}
