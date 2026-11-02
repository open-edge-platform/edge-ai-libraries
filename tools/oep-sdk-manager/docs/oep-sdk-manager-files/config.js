// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// Self-contained, no fetch: CONFIG is embedded here.
const CONFIG = {
  title: "Install Selector",
  shareKeys: [
    "VERSION",
    "OP_SYSTEM",
    "SDK"
  ],

  categories: [
    {
      key: "OP_SYSTEM",
      label: "Operating System",
      type: "single",
      options: [
        {
          label: "Ubuntu 24.04 / 26.04 LTS",
          value: "UBUNTU"
        }
      ]
    },
    {
      key: "SDK",
      label: "SDK",
      type: "single",
      options: [
        {
          label: "Metro Vision AI SDK",
          value: "OEP_VISION"
        },
        {
          label: "Metro Gen AI SDK",
          value: "OEP_GENAI"
        },
        {
          label: "Metro Visual AI Demo Kit",
          value: "VISUAL_AI_DEMO"
        },
        {
          label: "UAV Mission Compute SDK",
          value: "UAV_MISSION_COMPUTE",
          // Limit which options in other categories are compatible with this SDK.
          // Buttons for values not listed here will be greyed out when this SDK is selected.
          supports: {
            VERSION: ["latest", "2026.2"]
          }
        }
      ]
    },
    {
      key: "VERSION",
      label: "Version",
      type: "single",
      options: [
        {
          label: "latest",
          value: "latest"
        },
        {
          label: "2026.2",
          value: "2026.2"
        },
        {
          label: "2026.1",
          value: "2026.1"
        }
      ]
    }
  ],
  outputs: [
    {
      id: "components",
      label: "Installed Components",
      fallback: "Select options to see installed components…",
      rules: [
        {
          when: {
            SDK: "OEP_VISION",
            OP_SYSTEM: "UBUNTU",
            VERSION: "2026.2"
          },
          components: [
            "DL Streamer",
            "DL Streamer Pipeline Server",
            "OpenVINO",
            "OpenVINO Model Server",
            "Scenescape Manager",
            "Scenescape Controller",
            "Scenescape Autocalibration",
            "Edge AI Libraries - Repo",
            "Edge AI Suites - Repo",
            "Scenescape - Repo"
          ]
        },
        {
          when: {
            SDK: "OEP_GENAI",
            OP_SYSTEM: "UBUNTU",
            VERSION: "2026.2"
          },
          components: [
            "Audio Analyzer Microservice",
            "Document Ingestion (pgvector)",
            "Multimodal Embedding Serving",
            "Multimodal Data Preparation",
            "Model Download",
            "Chat Q&A Core",
            "Edge AI Libraries - Repo",
            "Edge AI Suites - Repo"
          ]
        },
        {
          when: {
            SDK: "VISUAL_AI_DEMO",
            OP_SYSTEM: "UBUNTU",
            VERSION: "2026.2"
          },
          components: [
            "DL Streamer Pipeline Server",
            "Node Red",
            "Grafana",
            "MediaMTX",
            "MQTT Broker",
            "Edge AI Suites - Repo"
          ]
        },
        {
          when: {
            SDK: "OEP_VISION",
            OP_SYSTEM: "UBUNTU",
            VERSION: "2026.1"
          },
          components: [
            "DL Streamer",
            "DL Streamer Pipeline Server",
            "OpenVINO",
            "OpenVINO Model Server",
            "Scenescape Manager",
            "Scenescape Controller",
            "Scenescape Autocalibration",
            "Edge AI Libraries - Repo",
            "Edge AI Suites - Repo",
            "Scenescape - Repo"
          ]
        },
        {
          when: {
            SDK: "OEP_GENAI",
            OP_SYSTEM: "UBUNTU",
            VERSION: "2026.1"
          },
          components: [
            "Audio Analyzer Microservice",
            "Document Ingestion (pgvector)",
            "Multimodal Embedding Serving",
            "Visual Data Preparation For Retrieval",
            "VLM OpenVINO Serving",
            "Chat Q&A",
            "Chat Q&A Core",
            "Edge AI Libraries - Repo",
            "Edge AI Suites - Repo"
          ]
        },
        {
          when: {
            SDK: "VISUAL_AI_DEMO",
            OP_SYSTEM: "UBUNTU",
            VERSION: "2026.1"
          },
          components: [
            "DL Streamer Pipeline Server",
            "Node Red",
            "Grafana",
            "MediaMTX",
            "MQTT Broker",
            "Edge AI Suites - Repo"
          ]
        },
        {
          when: {
            SDK: "OEP_VISION",
            OP_SYSTEM: "UBUNTU",
            VERSION: "latest"
          },
          components: [
            "DL Streamer",
            "DL Streamer Pipeline Server",
            "OpenVINO",
            "OpenVINO Model Server",
            "Scenescape Manager",
            "Scenescape Controller",
            "Scenescape Autocalibration",
            "Edge AI Libraries - Repo",
            "Metro AI Suite - Repo",
            "Scenescape - Repo"
          ]
        },
        {
          when: {
            SDK: "OEP_GENAI",
            OP_SYSTEM: "UBUNTU",
            VERSION: "latest"
          },
          components: [
            "Audio Analyzer Microservice",
            "Document Ingestion (pgvector)",
            "Multimodal Embedding Serving",
            "Multimodal Data Preparation",
            "Model Download",
            "Chat Q&A Core",
            "Edge AI Libraries - Repo",
            "Metro AI Suite - Repo"
          ]
        },
        {
          when: {
            SDK: "VISUAL_AI_DEMO",
            OP_SYSTEM: "UBUNTU",
            VERSION: "latest"
          },
          components: [
            "DL Streamer Pipeline Server",
            "Node Red",
            "Grafana",
            "MediaMTX",
            "MQTT Broker",
            "Metro AI Suite - Repo"
          ]
        },
        {
          when: {
            SDK: "UAV_MISSION_COMPUTE",
            OP_SYSTEM: "UBUNTU",
            VERSION: "2026.2"
          },
          components: [
            "OpenVINO",
            "PX4",
            "Gazebo",
            "MediaMTX",
            "MQTT Broker",
            "Grafana",
            "Edge AI Libraries - Repo",
            "Edge AI Suites - Repo"
          ]
        },
        {
          when: {
            SDK: "UAV_MISSION_COMPUTE",
            OP_SYSTEM: "UBUNTU",
            VERSION: "latest"
          },
          components: [
            "OpenVINO",
            "PX4",
            "Gazebo",
            "MediaMTX",
            "MQTT Broker",
            "Grafana",
            "Federal and Aerospace AI Suite - Repo"
          ]
        }
      ]
    },
    {
      id: "install",
      label: "Install",
      fallback: "Select options to see a command…",
      rules: [
        {
          when: {
            SDK: "OEP_VISION",
            OP_SYSTEM: "UBUNTU",
            VERSION: "2026.2"
          },
          text: `curl -fsS https://raw.githubusercontent.com/open-edge-platform/edge-ai-suites/refs/heads/release-2026.2.0/metro-ai-suite/metro-sdk-manager/scripts/oep-vision-ai-sdk.sh | bash`
        },

        {
          when: {
            SDK: "OEP_GENAI",
            OP_SYSTEM: "UBUNTU",
            VERSION: "2026.2"
          },
          text: `curl -fsS https://raw.githubusercontent.com/open-edge-platform/edge-ai-suites/refs/heads/release-2026.2.0/metro-ai-suite/metro-sdk-manager/scripts/oep-gen-ai-sdk.sh | bash`
        },

        {
          when: {
            SDK: "VISUAL_AI_DEMO",
            OP_SYSTEM: "UBUNTU",
            VERSION: "2026.2"
          },
          text: `curl -fsS https://raw.githubusercontent.com/open-edge-platform/edge-ai-suites/refs/heads/release-2026.2.0/metro-ai-suite/metro-sdk-manager/scripts/visual-ai-demo-kit.sh | bash`
        },
        {
          when: {
            SDK: "OEP_VISION",
            OP_SYSTEM: "UBUNTU",
            VERSION: "2026.1"
          },
          text: `curl -fsS https://raw.githubusercontent.com/open-edge-platform/edge-ai-suites/refs/heads/release-2026.1.0/metro-ai-suite/metro-sdk-manager/scripts/oep-vision-ai-sdk.sh | bash`
        },

        {
          when: {
            SDK: "OEP_GENAI",
            OP_SYSTEM: "UBUNTU",
            VERSION: "2026.1"
          },
          text: `curl -fsS https://raw.githubusercontent.com/open-edge-platform/edge-ai-suites/refs/heads/release-2026.1.0/metro-ai-suite/metro-sdk-manager/scripts/oep-gen-ai-sdk.sh | bash`
        },

        {
          when: {
            SDK: "VISUAL_AI_DEMO",
            OP_SYSTEM: "UBUNTU",
            VERSION: "2026.1"
          },
          text: `curl -fsS https://raw.githubusercontent.com/open-edge-platform/edge-ai-suites/refs/heads/release-2026.1.0/metro-ai-suite/metro-sdk-manager/scripts/visual-ai-demo-kit.sh | bash`
        },
        {
          when: {
            SDK: "OEP_VISION",
            OP_SYSTEM: "UBUNTU",
            VERSION: "latest"
          },
          text: `curl -fsS https://raw.githubusercontent.com/open-edge-platform/edge-ai-libraries/refs/heads/main/tools/oep-sdk-manager/scripts/metro-vision-ai-sdk.sh | bash`
        },

        {
          when: {
            SDK: "OEP_GENAI",
            OP_SYSTEM: "UBUNTU",
            VERSION: "latest"
          },
          text: `curl -fsS https://raw.githubusercontent.com/open-edge-platform/edge-ai-libraries/refs/heads/main/tools/oep-sdk-manager/scripts/metro-gen-ai-sdk.sh | bash`
        },

        {
          when: {
            SDK: "VISUAL_AI_DEMO",
            OP_SYSTEM: "UBUNTU",
            VERSION: "latest"
          },
          text: `curl -fsS https://raw.githubusercontent.com/open-edge-platform/edge-ai-libraries/refs/heads/main/tools/oep-sdk-manager/scripts/metro-visual-ai-demo-kit.sh | bash`
        },
        {
          when: {
            SDK: "UAV_MISSION_COMPUTE",
            OP_SYSTEM: "UBUNTU",
            VERSION: "2026.2"
          },
          text: `curl -fsS https://raw.githubusercontent.com/open-edge-platform/edge-ai-suites/refs/heads/release-2026.2.0/metro-ai-suite/metro-sdk-manager/scripts/uav-mission-compute-sdk.sh | bash`
        },
        {
          when: {
            SDK: "UAV_MISSION_COMPUTE",
            OP_SYSTEM: "UBUNTU",
            VERSION: "latest"
          },
          text: `curl -fsS https://raw.githubusercontent.com/open-edge-platform/edge-ai-libraries/refs/heads/main/tools/oep-sdk-manager/scripts/uav-mission-compute-sdk.sh | bash`
        }

      ]
    },
    {
      id: "nextsteps",
      label: "Next Steps",
      fallback: "Select options to see next steps…",
      rules: [
        {
          when: {
            SDK: "OEP_VISION",
            OP_SYSTEM: "UBUNTU",
            VERSION: "2026.2"
          },
          text: `Get Started`,
          link: `https://docs.openedgeplatform.intel.com/dev/OEP-articles/oep-sdk-manager/metro-vision-ai-sdk/get-started.html`
        },
        {
          when: {
            SDK: "OEP_GENAI",
            OP_SYSTEM: "UBUNTU",
            VERSION: "2026.2"
          },
          text: `Get Started`,
          link: `https://docs.openedgeplatform.intel.com/dev/OEP-articles/oep-sdk-manager/metro-gen-ai-sdk/get-started.html`
        },
        {
          when: {
            SDK: "VISUAL_AI_DEMO",
            OP_SYSTEM: "UBUNTU",
            VERSION: "2026.2"
          },
          text: `Get Started`,
          link: `https://docs.openedgeplatform.intel.com/dev/OEP-articles/oep-sdk-manager/metro-visual-ai-demo-kit/get-started.html`
        },
        {
          when: {
            SDK: "OEP_VISION",
            OP_SYSTEM: "UBUNTU",
            VERSION: "2026.1"
          },
          text: `Get Started`,
          link: `https://docs.openedgeplatform.intel.com/dev/OEP-articles/oep-sdk-manager/metro-vision-ai-sdk/get-started.html`
        },
        {
          when: {
            SDK: "OEP_GENAI",
            OP_SYSTEM: "UBUNTU",
            VERSION: "2026.1"
          },
          text: `Get Started`,
          link: `https://docs.openedgeplatform.intel.com/dev/OEP-articles/oep-sdk-manager/metro-gen-ai-sdk/get-started.html`
        },
        {
          when: {
            SDK: "VISUAL_AI_DEMO",
            OP_SYSTEM: "UBUNTU",
            VERSION: "2026.1"
          },
          text: `Get Started`,
          link: `https://docs.openedgeplatform.intel.com/dev/OEP-articles/oep-sdk-manager/metro-visual-ai-demo-kit/get-started.html`
        },
        {
          when: {
            SDK: "OEP_VISION",
            OP_SYSTEM: "UBUNTU",
            VERSION: "latest"
          },
          text: `Get Started`,
          link: `https://docs.openedgeplatform.intel.com/dev/OEP-articles/oep-sdk-manager/metro-vision-ai-sdk/get-started.html`
        },
        {
          when: {
            SDK: "OEP_GENAI",
            OP_SYSTEM: "UBUNTU",
            VERSION: "latest"
          },
          text: `Get Started`,
          link: `https://docs.openedgeplatform.intel.com/dev/OEP-articles/oep-sdk-manager/metro-gen-ai-sdk/get-started.html`
        },
        {
          when: {
            SDK: "VISUAL_AI_DEMO",
            OP_SYSTEM: "UBUNTU",
            VERSION: "latest"
          },
          text: `Get Started`,
          link: `https://docs.openedgeplatform.intel.com/dev/OEP-articles/oep-sdk-manager/metro-visual-ai-demo-kit/get-started.html`
        },
        {
          when: {
            SDK: "UAV_MISSION_COMPUTE",
            OP_SYSTEM: "UBUNTU",
            VERSION: "2026.2"
          },
          text: `Get Started`,
          link: `https://docs.openedgeplatform.intel.com/dev/OEP-articles/oep-sdk-manager/uav-mission-compute-sdk/get-started.html`
        },
        {
          when: {
            SDK: "UAV_MISSION_COMPUTE",
            OP_SYSTEM: "UBUNTU",
            VERSION: "latest"
          },
          text: `Get Started`,
          link: `https://docs.openedgeplatform.intel.com/dev/OEP-articles/oep-sdk-manager/uav-mission-compute-sdk/get-started.html`
        }
      ]
    },
    {
      id: "resources",
      label: "Resources",
      fallback: "Select options to see resources…",
      rules: [
        {
          when: {
            SDK: "OEP_VISION",
            OP_SYSTEM: "UBUNTU",
            VERSION: "2026.2"
          },
          links: [
            { text: "DL Streamer", url: "http://docs.openedgeplatform.intel.com/2026.2/edge-ai-libraries/dl-streamer/index.html" },
            { text: "DL Streamer Pipeline Server", url: "https://docs.openedgeplatform.intel.com/2026.2/edge-ai-libraries/dlstreamer-pipeline-server/index.html" },
            { text: "OpenVINO", url: "https://docs.openvino.ai/2026/get-started.html" },
            { text: "OpenVINO Model Server", url: "https://docs.openvino.ai/2026/model-server/ovms_what_is_openvino_model_server.html" },
            { text: "Scenescape", url: "https://github.com/open-edge-platform/scenescape" },
            { text: "Edge AI Libraries", url: "https://docs.openedgeplatform.intel.com/2026.2/ai-libraries.html"},
            { text: "Metro AI Suite", url: "https://docs.openedgeplatform.intel.com/2026.2/ai-suite-metro.html"}
          ]
        },
        {
          when: {
            SDK: "OEP_GENAI",
            OP_SYSTEM: "UBUNTU",
            VERSION: "2026.2"
          },
          links: [
            { text: "Audio Analyzer", url: "https://docs.openedgeplatform.intel.com/2026.2/edge-ai-libraries/audio-analyzer/index.html" },
            { text: "Document Ingestion - pgvector", url: "https://docs.openedgeplatform.intel.com/2026.2/edge-ai-libraries/pgvector/index.html" },
            { text: "Multimodal Embedding Serving", url: "https://docs.openedgeplatform.intel.com/2026.2/edge-ai-libraries/multimodal-embedding-serving/index.html" },
            { text: "Multimodal Data Preparation", url: "https://github.com/open-edge-platform/edge-ai-libraries/blob/release-2026.2.0/microservices/visual-data-preparation-for-retrieval/multimodal-dataprep/docs/user-guide/index.md" },
            { text: "Chat Q&A Core", url: "http://docs.openedgeplatform.intel.com/2026.2/edge-ai-libraries/chat-question-and-answer-core/index.html" },
            { text: "Edge AI Libraries", url: "https://docs.openedgeplatform.intel.com/2026.2/ai-libraries.html"},
            { text: "Metro AI Suite", url: "https://docs.openedgeplatform.intel.com/2026.2/ai-suite-metro.html"}
          ]
        },
        {
          when: {
            SDK: "VISUAL_AI_DEMO",
            OP_SYSTEM: "UBUNTU",
            VERSION: "2026.2"
          },
          links: [
            { text: "DL Streamer", url: "http://docs.openedgeplatform.intel.com/2026.2/edge-ai-libraries/dl-streamer/index.html" },
            { text: "DL Streamer Pipeline Server", url: "https://docs.openedgeplatform.intel.com/2026.2/edge-ai-libraries/dlstreamer-pipeline-server/index.html" },
            { text: "Edge AI Libraries", url: "https://docs.openedgeplatform.intel.com/2026.2/ai-libraries.html"},
            { text: "Metro AI Suite", url: "https://docs.openedgeplatform.intel.com/2026.2/ai-suite-metro.html"}
          ]
        },
        {
          when: {
            SDK: "OEP_VISION",
            OP_SYSTEM: "UBUNTU",
            VERSION: "2026.1"
          },
          links: [
            { text: "DL Streamer", url: "http://docs.openedgeplatform.intel.com/2026.1/edge-ai-libraries/dl-streamer/index.html" },
            { text: "DL Streamer Pipeline Server", url: "https://docs.openedgeplatform.intel.com/2026.1/edge-ai-libraries/dlstreamer-pipeline-server/index.html" },
            { text: "OpenVINO", url: "https://docs.openvino.ai/2026/get-started.html" },
            { text: "OpenVINO Model Server", url: "https://docs.openvino.ai/2026/model-server/ovms_what_is_openvino_model_server.html" },
            { text: "Scenescape", url: "https://github.com/open-edge-platform/scenescape" },
            { text: "Edge AI Libraries", url: "https://docs.openedgeplatform.intel.com/2026.1/ai-libraries.html"},
            { text: "Metro AI Suite", url: "https://docs.openedgeplatform.intel.com/2026.1/ai-suite-metro.html"}
          ]
        },
        {
          when: {
            SDK: "OEP_GENAI",
            OP_SYSTEM: "UBUNTU",
            VERSION: "2026.1"
          },
          links: [
            { text: "Audio Analyzer", url: "https://docs.openedgeplatform.intel.com/2026.1/edge-ai-libraries/audio-analyzer/index.html" },
            { text: "Document Ingestion - pgvector", url: "https://docs.openedgeplatform.intel.com/2026.1/edge-ai-libraries/pgvector/index.html" },
            { text: "Multimodal Embedding Serving", url: "https://docs.openedgeplatform.intel.com/2026.1/edge-ai-libraries/multimodal-embedding-serving/index.html" },
            { text: "Visual Data Preparation For Retrieval", url: "https://github.com/open-edge-platform/edge-ai-libraries/blob/release-2026.1.0/microservices/visual-data-preparation-for-retrieval/vdms/docs/user-guide/Overview.md" },
            { text: "VLM OpenVINO Serving", url: "https://github.com/open-edge-platform/edge-ai-libraries/blob/release-2026.1.0/microservices/vlm-openvino-serving/docs/user-guide/Overview.md" },
            { text: "Chat Q&A", url: "http://docs.openedgeplatform.intel.com/2026.1/edge-ai-libraries/chat-question-and-answer/index.html" },
            { text: "Chat Q&A Core", url: "http://docs.openedgeplatform.intel.com/2026.1/edge-ai-libraries/chat-question-and-answer-core/index.html" },
            { text: "Edge AI Libraries", url: "https://docs.openedgeplatform.intel.com/2026.1/ai-libraries.html"},
            { text: "Metro AI Suite", url: "https://docs.openedgeplatform.intel.com/2026.1/ai-suite-metro.html"}
          ]
        },
        {
          when: {
            SDK: "VISUAL_AI_DEMO",
            OP_SYSTEM: "UBUNTU",
            VERSION: "2026.1"
          },
          links: [
            { text: "DL Streamer", url: "http://docs.openedgeplatform.intel.com/2026.1/edge-ai-libraries/dl-streamer/index.html" },
            { text: "DL Streamer Pipeline Server", url: "https://docs.openedgeplatform.intel.com/2026.1/edge-ai-libraries/dlstreamer-pipeline-server/index.html" },
            { text: "Edge AI Libraries", url: "https://docs.openedgeplatform.intel.com/2026.1/ai-libraries.html"},
            { text: "Metro AI Suite", url: "https://docs.openedgeplatform.intel.com/2026.1/ai-suite-metro.html"}
          ]
        },
        {
          when: {
            SDK: "OEP_VISION",
            OP_SYSTEM: "UBUNTU",
            VERSION: "latest"
          },
          links: [
            { text: "DL Streamer", url: "http://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/dl-streamer/index.html" },
            { text: "DL Streamer Pipeline Server", url: "https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/dlstreamer-pipeline-server/index.html" },
            { text: "OpenVINO", url: "https://docs.openvino.ai/2026/get-started.html" },
            { text: "OpenVINO Model Server", url: "https://docs.openvino.ai/2026/model-server/ovms_what_is_openvino_model_server.html" },
            { text: "Scenescape", url: "https://github.com/open-edge-platform/scenescape" },
            { text: "Edge AI Libraries", url: "https://docs.openedgeplatform.intel.com/dev/ai-libraries.html"},
            { text: "Metro AI Suite", url: "https://docs.openedgeplatform.intel.com/dev/ai-suite-metro.html"}
          ]
        },
        {
          when: {
            SDK: "OEP_GENAI",
            OP_SYSTEM: "UBUNTU",
            VERSION: "latest"
          },
          links: [
            { text: "Audio Analyzer", url: "https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/audio-analyzer/index.html" },
            { text: "Document Ingestion - pgvector", url: "https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/pgvector/index.html" },
            { text: "Multimodal Embedding Serving", url: "https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/multimodal-embedding-serving/index.html" },
            { text: "Visual Data Preparation For Retrieval", url: "https://github.com/open-edge-platform/edge-ai-libraries/blob/main/microservices/visual-data-preparation-for-retrieval/multimodal-dataprep/docs/user-guide/index.md" },
            { text: "Chat Q&A Core", url: "http://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/chat-question-and-answer-core/index.html" },
            { text: "Edge AI Libraries", url: "https://docs.openedgeplatform.intel.com/dev/ai-libraries.html"},
            { text: "Metro AI Suite", url: "https://docs.openedgeplatform.intel.com/dev/ai-suite-metro.html"}
          ]
        },
        {
          when: {
            SDK: "VISUAL_AI_DEMO",
            OP_SYSTEM: "UBUNTU",
            VERSION: "latest"
          },
          links: [
            { text: "DL Streamer", url: "http://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/dl-streamer/index.html" },
            { text: "DL Streamer Pipeline Server", url: "https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/dlstreamer-pipeline-server/index.html" },
            { text: "Edge AI Libraries", url: "https://docs.openedgeplatform.intel.com/dev/ai-libraries.html"},
            { text: "Metro AI Suite", url: "https://docs.openedgeplatform.intel.com/dev/ai-suite-metro.html"}
          ]
        },
        {
          when: {
            SDK: "UAV_MISSION_COMPUTE",
            OP_SYSTEM: "UBUNTU",
            VERSION: "2026.2"
          },
          links: [
            { text: "OpenVINO", url: "https://docs.openvino.ai/2026/get-started.html" },
            { text: "Edge AI Libraries", url: "https://docs.openedgeplatform.intel.com/2026.2/ai-libraries.html"},
            { text: "Federal and Aerospace AI Suite", url: "https://github.com/open-edge-platform/federal-and-aerospace-ai-suite"}
          ]
        },
        {
          when: {
            SDK: "UAV_MISSION_COMPUTE",
            OP_SYSTEM: "UBUNTU",
            VERSION: "latest"
          },
          links: [
            { text: "OpenVINO", url: "https://docs.openvino.ai/2026/get-started.html" },
            { text: "Edge AI Libraries", url: "https://docs.openedgeplatform.intel.com/dev/ai-libraries.html"},
            { text: "Federal and Aerospace AI Suite", url: "https://github.com/open-edge-platform/federal-and-aerospace-ai-suite"}
          ]
        }
      ]
    }
  ]
};

// --- small helpers ---
const $ = (sel, root = document) => root.querySelector(sel);
const el = (tag, cls, txt) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (txt != null) n.textContent = txt;
  return n;
};

const parseQuery = (keys) => {
  const qs = new URLSearchParams(location.search);
  const out = {};
  for (const k of keys) {
    const v = qs.get(k);
    if (v) out[k] = v;
  }
  return out;
};

const writeQuery = (state, keys) => {
  const qs = new URLSearchParams();
  keys.forEach((k) => {
    const v = state[k];
    if (v != null && v !== "") qs.set(k, String(v));
  });
  const q = `?${qs.toString()}`;
  history.replaceState({}, "", q);
  return location.origin + location.pathname + q;
};

// {{KEY}} or {{KEY|dotver}}
const interpolate = (text, sel) =>
  text.replace(/\{\{\s*([A-Z0-9_]+)(?:\|([a-z]+))?\s*\}\}/g, (_, key, filter) => {
    let v = sel[key] ?? "";
    if (filter === "dotver") v = v.startsWith("v_") ? v.slice(2).replaceAll("_", ".") : v;
    return String(v);
  });

const firstMatch = (rules, sel) => {
  for (const r of rules || []) {
    const cond = r.when || {};
    const ok = Object.keys(cond).every((k) => String(sel[k] ?? "") === String(cond[k]));
    if (ok) return r;
  }
  return null;
};

// --- UI rendering ---
let STATE = {};

function init() {
  $("#app-title").textContent = CONFIG.title || "Selector";

  // defaults: first option per category
  const defaults = {};
  (CONFIG.categories || []).forEach((cat) => {
    const first = cat.options?.[0]?.value;
    if (first != null) defaults[cat.key] = first;
  });

  // state from URL (shareable)
  STATE = { ...defaults, ...parseQuery(CONFIG.shareKeys || []) };
  repairState(STATE);

  renderCategories();
  updateOutputsAndUrl();
  hookCopyButtons();
}

function renderCategories() {
  const host = $("#categories");
  host.innerHTML = "";

  (CONFIG.categories || []).forEach((cat) => {
    const sec = el("section", "st-section st-section-accent");
    const title = el("div", "st-section-title", cat.label);
    const content = el("div", "st-section-content");
    const row = el("div", "st-section-content-row");

    const group = el("div", "spark-button-group option-button-group");
    (cat.options || []).forEach((opt) => {
      const btn = el("button", "spark-button spark-button-size-l spark-button-ghost");
      const inner = el("span", "spark-button-content");
      inner.append(el("span", "", opt.label));
      if (opt.subtitle) inner.append(el("span", "subtitle", opt.subtitle));
      btn.append(inner);

      const isActive = STATE[cat.key] === opt.value;
      if (isActive) btn.classList.add("spark-toggle-button-clicked-ghost", "pill-active");

      const available = isOptionAvailable(cat, opt, STATE);
      if (!available) {
        btn.disabled = true;
        btn.setAttribute("aria-disabled", "true");
        btn.title = "Not available for the current selection";
        btn.classList.add("pill-disabled");
      }

      btn.addEventListener("click", () => {
        if (btn.disabled) return;
        STATE[cat.key] = opt.value;
        repairState(STATE);
        // Re-render everything
        renderCategories();
        updateOutputsAndUrl();
      });

      group.append(btn);
    });

    row.append(group);
    content.append(row);
    sec.append(title, content);
    host.append(sec);
  });
}

// Return true if `opt` in category `cat` is compatible with the rest of `state`.
function isOptionAvailable(cat, opt, state) {
  // Check constraints declared by other selected options against `opt`.
  for (const other of CONFIG.categories || []) {
    if (other.key === cat.key) continue;
    const selectedValue = state[other.key];
    if (selectedValue == null) continue;
    const selectedOpt = (other.options || []).find((o) => o.value === selectedValue);
    const allowed = selectedOpt && selectedOpt.supports && selectedOpt.supports[cat.key];
    if (Array.isArray(allowed) && !allowed.includes(opt.value)) {
      return false;
    }
  }

  // Check constraints declared by `opt` against currently selected values in other categories.
  if (opt.supports) {
    for (const otherKey of Object.keys(opt.supports)) {
      const allowed = opt.supports[otherKey];
      const selectedValue = state[otherKey];
      if (Array.isArray(allowed) && selectedValue != null && !allowed.includes(selectedValue)) {
        return false;
      }
    }
  }

  return true;
}

// If the current selection in any category is no longer available given the
// rest of `state`, replace it with the first available option in that category.
function repairState(state) {
  (CONFIG.categories || []).forEach((cat) => {
    const currentValue = state[cat.key];
    const currentOpt = (cat.options || []).find((o) => o.value === currentValue);
    if (currentOpt && isOptionAvailable(cat, currentOpt, state)) return;
    const firstAvailable = (cat.options || []).find((o) => isOptionAvailable(cat, o, state));
    if (firstAvailable) state[cat.key] = firstAvailable.value;
    else delete state[cat.key];
  });
}

function updateOutputsAndUrl() {
  // keep URL in sync
  const shareUrl = writeQuery(STATE, CONFIG.shareKeys || []);

  // compute outputs
  (CONFIG.outputs || []).forEach((o) => {
    const matched = firstMatch(o.rules, STATE);

    if (o.id === "components") {
      const container = $("#componentsText");
      if (matched?.components && Array.isArray(matched.components)) {
        container.innerHTML = "";

        // Create a compact list container
        const list = document.createElement("ul");
        list.style.margin = "0.5rem 0 0 0";
        list.style.padding = "0";
        list.style.listStyle = "none";
        list.style.display = "flex";
        list.style.flexWrap = "wrap";
        list.style.gap = "0.5rem";

        matched.components.forEach((component) => {
          // Create small component badge
          const listItem = document.createElement("li");
          listItem.style.display = "inline-flex";
          listItem.style.alignItems = "center";
          listItem.style.padding = "0.25rem 0.5rem";
          listItem.style.backgroundColor = "var(--spark-color-theme-light-gray100, #f8f9fa)";
          listItem.style.border = "1px solid var(--spark-color-theme-light-gray300, #dee2e6)";
          listItem.style.borderRadius = "0.25rem";
          listItem.style.fontSize = "0.75rem";
          listItem.style.fontWeight = "500";
          listItem.style.color = "var(--spark-color-theme-light-gray700, #495057)";
          listItem.style.whiteSpace = "nowrap";

          // Add small checkmark icon
          const icon = document.createElement("span");
          icon.innerHTML = "✓";
          icon.style.color = "#28a745";
          icon.style.fontWeight = "bold";
          icon.style.marginRight = "0.375rem";
          icon.style.fontSize = "0.75rem";

          // Add component text
          const text = document.createElement("span");
          text.textContent = component;

          listItem.appendChild(icon);
          listItem.appendChild(text);
          list.appendChild(listItem);
        });

        container.appendChild(list);
      } else {
        container.textContent = o.fallback ?? "";
      }
    }

    if (o.id === "install") {
      const finalText = matched?.text ? interpolate(String(matched.text), STATE) : (o.fallback ?? "");
      $("#installText").textContent = finalText;
      $("#copyCmd").disabled = !matched?.text;
    }

    if (o.id === "nextsteps") {
      const container = $("#nextStepsText");
      if (matched?.text && matched?.link) {
        const link = document.createElement("a");
        link.href = matched.link;
        link.target = "_blank";
        link.className = "spark-hyperlink spark-hyperlink-primary";
        link.textContent = matched.text;
        container.innerHTML = "";
        container.appendChild(link);
      } else {
        container.textContent = o.fallback ?? "";
      }
    }

    if (o.id === "resources") {
      const container = $("#resourcesText");
      if (matched?.links && Array.isArray(matched.links)) {
        container.innerHTML = "";
        matched.links.forEach((linkObj, index) => {
          const link = document.createElement("a");
          link.href = linkObj.url;
          link.target = "_blank";
          link.className = "spark-hyperlink spark-hyperlink-primary";
          link.textContent = linkObj.text;
          container.appendChild(link);
          if (index < matched.links.length - 1) {
            container.appendChild(document.createElement("br"));
          }
        });
      } else {
        container.textContent = o.fallback ?? "";
      }
    }
  });
}

function copyToClipboard(text) {
  // Try modern clipboard API first if available and in secure context
  if (navigator.clipboard && navigator.clipboard.writeText) {
    return navigator.clipboard.writeText(text).catch(err => {
      console.warn('Clipboard API failed, falling back to legacy method:', err);
      return copyToClipboardFallback(text);
    });
  }

  // Fallback for older browsers or non-secure contexts
  return copyToClipboardFallback(text);
}

function copyToClipboardFallback(text) {
  return new Promise((resolve, reject) => {
    const textArea = document.createElement('textarea');
    textArea.value = text;

    // Ensure the textarea is visible and properly positioned
    textArea.style.position = 'absolute';
    textArea.style.left = '0';
    textArea.style.top = '0';
    textArea.style.opacity = '0';
    textArea.style.pointerEvents = 'none';
    textArea.style.zIndex = '-1';

    // Make it readable
    textArea.setAttribute('readonly', '');
    textArea.style.border = 'none';
    textArea.style.outline = 'none';
    textArea.style.boxShadow = 'none';
    textArea.style.background = 'transparent';

    document.body.appendChild(textArea);

    try {
      // Focus and select
      textArea.focus();
      textArea.select();
      textArea.setSelectionRange(0, textArea.value.length);

      // Try execCommand
      const successful = document.execCommand('copy');
      document.body.removeChild(textArea);

      if (successful) {
        resolve();
      } else {
        reject(new Error('Copy failed'));
      }
    } catch (err) {
      document.body.removeChild(textArea);
      reject(err);
    }
  });
}



function hookCopyButtons() {
  const copyCmd = $("#copyCmd");
  if (copyCmd) {
    copyCmd.addEventListener("click", async () => {
    const text = $("#installText").textContent.trim();
    if (!text || text === "Select options to see a command…") {
      alert("No command to copy. Please select your options first.");
      return;
    }

    const btn = $("#copyCmd");

    try {
      btn.disabled = true;
      await copyToClipboard(text);
      btn.disabled = false;
      flashCopied("#copyCmd");
    } catch (err) {
      console.error('Copy failed:', err);
      btn.disabled = false;
      alert("Copy failed. Please try manually selecting the text and pressing Ctrl+C (or Cmd+C on Mac).");
    }
    });
  }






}

function flashCopied(sel) {
  const btn = document.querySelector(sel);
  if (!btn) return; // Guard against missing elements

  const old = btn.textContent;
  btn.textContent = "Copied!";
  setTimeout(() => {
    // Only reset if the button text hasn't changed (to avoid conflicts)
    if (btn.textContent === "Copied!") {
      btn.textContent = old;
    }
  }, 900);
}

document.addEventListener("DOMContentLoaded", init);
