# Video Summarizer CLI Configuration Guide. 

This document explains the YAML configuration used by the Video Analysis & Summarization CLI (`./cli`) and how to adjust each field for different use cases or videos. It includes key field definitions, the effect each has on accuracy and performance, tuning tips, and example profiles (generic, retail, traffic).

## Table of contents
- [Quick summary](#quick-summary)
- [How the CLI uses the YAML](#how-the-cli-uses-the-yaml)
- [All configuration fields](#all-configuration-fields)
- [Example profiles](#example-profiles)
- [Troubleshooting and measuring impact](#troubleshooting-and-measuring-impact)

## Quick summary

The CLI reads all runtime parameters from a YAML file (default: `./config/generic.yaml`). The YAML config controls:
- Video chunking, frame sampling, and overlap.
- Prompts for map/reduce summarization.
- Video Ingestion Pipeline selection.
- Audio transcription model configuration.
- Miscellaneous runtime flags like `debug` and `backendEndpoint`.

## How the CLI uses the YAML

At startup the CLI loads the YAML and uses the values to override default values in the Video Summmary backend.

- Split the input video into fixed-length chunks (`chunkDuration`) and determine how frames are sampled inside each chunk (`samplingFrame`)
- Choose which video ingestion pipeline to run (e.g., `object_detection`, `video_ingestion`).
- Provide  prompts that guide frame-level, map-level and reduce-level summarization.
- Define the Video summarization backend endpoint (`backendEndpoint`) and logging verbosity (`debug`).

The backend exposes its configuration, including all supported audio models, default values, and video ingestion pipelines, at the following endpoint: `http://<backendEndpoint>/manager/app/config`. You can use this to see the available options for your specific backend deployment.

## Configuration fields

### `chunkDuration`
- **Type**: `integer` (seconds)
- **Default**: `20`
- **Meaning**: Length of each video chunk processed independently by the pipeline.
- **Accuracy Impact**: Shorter chunk durations create more, smaller chunks. That can increase contextual granularity (better local accuracy for temporally short events) but may reduce ability to form cohesive long-term summaries.
- **Performance Impact**: Shorter chunks increase total pipeline overhead (more chunk boundaries, more API/VLM calls) and can increase memory/CPU usage due to more parallel tasks.
- **Tuning Tips**: For short-event detection (e.g., retail interactions, micro-actions) prefer 5–15s. For long scenes (presentations, lectures) use 30–60s.

### `samplingFrame`
- **Type**: `integer` (frames)
- **Default**: `5`
- **Meaning**: Sample uniformly N frames inside a chunk to analyze.
- **Accuracy Impact**: Higher values (more frequent sampling) improve detection of short-duration events and small object motion but increase redundancy and processing cost. Higher values may miss short events.
- **Performance Impact**: Linear scaling with number of frames analyzed. Doubling the `samplingFrame` roughly doubles frame processing time.
- **Tuning Tips**: For high-motion or dense scenes (traffic, retail) use 8-15. For slow scenes use 3-8.
- **Derived Setting**: The multi-frame window sent to the backend is automatically computed as `samplingFrame + overlapOverride`.

### `overlapOverride`
- **Type**: `integer` (frames)
- **Default**: `0`
- **Meaning**: Overlap (in frames) between consecutive chunks. Overlap helps avoid missing events that straddle chunk boundaries.
- **Accuracy Impact**: Small positive overlap (1–5s worth of frames) reduces boundary artifacts and missed short events.
- **Performance Impact**: Overlap increases total frames processed (duplicated across chunk boundaries).
- **Tuning Tips**: Use 0–2s overlap for most cases. For unpredictable short events that happen near cuts, use 3–5s.

### `framePromptOverride`
- **Type**: `string`
- **Meaning**: Used to generate the individual caption(summary) for multi-frame batches using VLM (Vision Language Model).
- **Accuracy Impact**: Precise prompts encourage models to focus on relevant attributes (e.g., "count people and identify vehicles"), which improves useful outputs; vague prompts can produce verbose but unfocused descriptions.
- **Performance Impact**: No direct impact on runtime, but complex prompts may produce longer text responses which cost more.
- **Tuning Tips**: Make prompts explicit for the task. For retail: "identify customer interactions with shelf items, detect product touches". For traffic: "count vehicles, detect accidents or stopped vehicles".

### `mapPromptOverride`
- **Type**: `string`
- **Meaning**: Used to generate the final summary of the individual multi-batch summaries using VLM model or LLM model (depending on application setup).
- **Accuracy Impact**: Precise prompts encourage models to focus on relevant attributes for creating summary of summaries.
- **Performance Impact**: Similar to `framePromptOverride` - more words -> possibly more tokens -> higher cost.
- **Tuning Tips**: Emphasize the key aggregation you want (e.g., counts, anomalies, timeline/sequence of events).

### `reducePromptOverride`
- **Type**: `string`
- **Meaning**: Used to reduce the size of input for the final summary generation. This is used only in case the total length of input for final summary is greater than the model input size. In this case the multi-frame summaries are batched together in smaller batches and sent using this prompt to reduce the length, and then the resultant list of summaries is sent for final summary creation.
- **Accuracy Impact**: A focused reduce prompt yields concise, task-specific summaries.
- **Performance Impact**: Similar to other prompts.

### `singlePromptOverride`
- **Type**: `string`
- **Meaning**:Used to reduce the size of a single caption. This is used only in case the size of even a single input is greater than the model input size. Size of each input is reduced such that at least 2 summaries can be batched together in map-reduce chain.

### `ingestionPipelineOverride`
- **Type**: `string`
- **Default**: `"object_detection"`
- **Meaning**: Selects which video ingestion pipeline to execute. Supported values are:
  - `object_detection`: "Ingestion with Object Detection". While chunking the video pipeline also processes for object detection.
  - `video_ingestion`: "Simple ingestion". Plain and simple video ingestion.
- **Accuracy Impact**: Choose the pipeline that matches the task. Using `video_ingestion` for a video with lot of objects will give poor results.
- **Performance Impact**: `object_detection` requires more compute.
- **Tuning Tips**: Start with `video_ingestion` for general-purpose analytics. For object-focused tasks (retail, traffic) use `object_detection`.

### `audioModelOverride`
- **Type**: `string`
- **Default**: `"small.en"`
- **Meaning**: Audio transcription model for speech-to-text. Values depend on the backend. Supported models include:
  - `tiny.en`: "Tiny (English)". English only version of tiny whisper model. Significantly less accuracy, extremely fast inference.
  - `small.en`: "Small (English)". English only version of small whisper Model. Good accuracy. Fast inference.
  - `medium.en`: "Medium (English)". English only version of Medium whisper Model. Very good accuracy. Longer inference time.
- **Accuracy Impact**: Larger models or language-specific models improve transcription accuracy, especially in noisy videos.
- **Performance Impact**: Larger STT models take longer and use more memory.
- **Tuning Tips**: For short videos where speech matters, prefer higher-accuracy models. For large volumes, use streaming or lightweight models.

### `videoPath`
- **Type**: `string`
- **Meaning**: Local path to the video file to upload and analyze.
- **Tuning Tips**: Provide a trimmed video for focused analysis and faster iteration.

### `backendEndpoint`
- **Type**: `string`
- **Meaning**: HTTP endpoint for the Video Summary backend that performs analysis and summarization.

### `debug`
- **Type**: `boolean`
- **Meaning**: Enable verbose logging.
- **Impact**: Uses more disk and log verbosity; useful for tuning and spotting missed events.

## Example profiles

The following [example YAML configurations](./config/) illustrate how to set parameters for different use cases.

## Tuning and measuring impact

- Start from the profile that best matches your use case. Run a representative test video and measure:
  - End-to-end runtime (wall-clock).
  - CPU/GPU utilization on backend.
  - Qualitative accuracy (did the summary miss events?).

- Change one parameter at a time (e.g., `samplingFrame`, `overlap`, `chunkDuration`) and rerun. Keep a small table with results to discover trade-offs.
- On the Application side you can also change the LLM/VLM models used for summarization to see their impact on accuracy and cost. The API Configuration will change `http://<backendEndpoint>/manager/app/config` to reflect the new models.

