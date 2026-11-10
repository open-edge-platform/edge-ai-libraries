// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { BaseEdge, ExtensionCategory, register } from "@antv/g6";
import type { BaseEdgeStyleProps } from "@antv/g6";
import type { PathArray } from "@antv/util";

interface TokenBranchStyleProps extends BaseEdgeStyleProps {
  branchX: number;
}

class TokenBranchEdge extends BaseEdge {
  protected getKeyPath(attributes: Required<TokenBranchStyleProps>): PathArray {
    const [source, target] = this.getEndpoints(attributes);
    const { branchX } = attributes;
    const controlX = (source[0] + branchX) / 2;

    return [
      ["M", source[0], source[1]],
      [
        "C",
        controlX,
        source[1],
        controlX,
        target[1],
        branchX,
        target[1],
      ],
      ["L", target[0], target[1]],
    ];
  }
}

register(ExtensionCategory.EDGE, "token-branch", TokenBranchEdge);
