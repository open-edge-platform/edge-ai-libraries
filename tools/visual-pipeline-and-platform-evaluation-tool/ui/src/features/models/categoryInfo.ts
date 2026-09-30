import type { ModelCategory } from "@/api/api.generated.ts";

export const CATEGORY_INFO: Record<
  ModelCategory,
  { label: string; description: string }
> = {
  object_detection: {
    label: "Object Detection",
    description:
      "Object detection involves identifying and locating objects within an image or video using rectangular bounding boxes.",
  },
  image_segmentation: {
    label: "Image Segmentation",
    description:
      "Instance segmentation provides pixel-level boundaries (polygons) for individual objects to capture their exact shape.",
  },
  pose_estimation: {
    label: "Pose Estimation",
    description:
      "Pose estimation locates keypoints (joints) on individual subjects to capture their skeletal structure and posture.",
  },
  image_classification: {
    label: "Image Classification",
    description:
      "Pose estimation locates keypoints (joints) on individual subjects to capture their skeletal structure and posture.",
  },
  vision_language_models: {
    label: "Vision Language Models (VLMs)",
    description:
      "Vision-language models combine image understanding with natural language to answer questions about visual content.",
  },
  large_language_models: {
    label: "Large Language Models (LLMs)",
    description:
      "Large language models generate and reason over text to interpret instructions and produce natural language responses.",
  },
  automatic_speech_recognition: {
    label: "Automatic Speech Recognition (ASR)",
    description:
      "Automatic speech recognition transcribes spoken audio into written text to capture what was said.",
  },
  text_to_speech: {
    label: "Text to Speech (TTS)",
    description:
      "Text-to-speech synthesizes written text into spoken audio to deliver natural-sounding voice output.",
  },
};
