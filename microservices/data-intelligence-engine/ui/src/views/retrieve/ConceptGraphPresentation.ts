// Copyright (C) 2026 Intel Corporation; SPDX-License-Identifier: Apache-2.0
export const graphLayoutNodeSpacing = (node?: {
  size?: number | number[];
  layoutSize?: number;
}) => {
  const size = Array.isArray(node?.size)
    ? Math.max(...node.size)
    : (node?.size ?? 58);
  return 18 + Math.max(0, (node?.layoutSize ?? size) - size);
};

export const graphLayout = {
  type: "gForce",
  preventOverlap: true,
  linkDistance: 135,
  nodeStrength: 1000,
  edgeStrength: 120,
  nodeSpacing: graphLayoutNodeSpacing,
  maxIteration: 320,
  minMovement: 0.8,
  animate: false,
};

export const graphLayerVariables = (hop: number) => {
  const prefix =
    hop === 0 ? "--graph-seed" : `--graph-hop-${Math.min(Math.max(hop, 1), 4)}`;
  return { fill: `${prefix}-fill`, stroke: `${prefix}-stroke` };
};

export const graphNodeSize = (score?: number, result = false) => {
  if (result) return 72;
  if (score === undefined || !Number.isFinite(score)) return 58;
  return [42, 50, 58, 66, 74][Math.min(Math.max(Math.floor(score), 0), 4)];
};

export const formatGraphLabel = (name: string) => {
  const normalized = name.trim().split("/").pop() || name.trim();
  const first = normalized.slice(0, 7);
  const rest = normalized.slice(7);
  const second = rest
    ? `${rest.slice(0, 6)}${rest.length >= 7 ? "\u2026" : ""}`
    : "";
  return second ? `${first}\n${second}` : first;
};

export const formatGraphScore = (score: number) =>
  (String(score).split(".")[1] || "").length > 3
    ? score.toFixed(3)
    : String(score);

const parseHexColor = (color: string) => {
  const match = /^#([\da-f]{2})([\da-f]{2})([\da-f]{2})$/i.exec(color.trim());
  return match ? match.slice(1).map((part) => parseInt(part, 16)) : undefined;
};

export const radialGraphFill = (color: string) => {
  const rgb = parseHexColor(color);
  const light = rgb
    ? `#${rgb
        .map((channel) =>
          Math.round(channel + (255 - channel) * 0.46)
            .toString(16)
            .padStart(2, "0"),
        )
        .join("")}`
    : color;
  return `r(0.5, 0.38, 0.72) 0:${light} 0.72:${color} 1:${color}`;
};

export const softGraphEdge = (color: string) => {
  const rgb = parseHexColor(color);
  return rgb ? `rgba(${rgb.join(", ")}, 0.68)` : color.trim();
};
