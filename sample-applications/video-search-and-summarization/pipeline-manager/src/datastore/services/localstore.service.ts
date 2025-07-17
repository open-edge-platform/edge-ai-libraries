// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Injectable } from '@nestjs/common';
import { existsSync, mkdirSync, writeFileSync } from 'fs';

export interface VideoWriteDTO {
  stateId: string;
  summary?: string;
}

export interface ChunkWrtieDTO extends VideoWriteDTO {
  chunkId: string;
}

export interface FrameWriteDTO extends ChunkWrtieDTO {
  frameId: string;
  caption?: string;
}

@Injectable()
export class LocalstoreService {
  dataPath = 'data';

  private createStateDir(stateId: string) {
    const statePath = [this.dataPath, stateId].join('/');
    if (!existsSync(statePath)) {
      mkdirSync(statePath, { recursive: true });
    }
  }

  private getSummaryPath(stateId: string, postFix: boolean = false): string {
    const statePath = [this.dataPath, stateId];

    if (postFix) {
      statePath.push('summary.txt');
    }

    return statePath.join('/');
  }

  private getFramePath(
    stateId: string,
    chunkId: string,
    frameId: string,
  ): string {
    const prefixPath = this.getSummaryPath(stateId);
    return [prefixPath, `chunk_${chunkId}_frame_${frameId}.txt`].join('/');
  }

  private createPath(filePath: string) {
    if (!existsSync(filePath)) {
      writeFileSync(filePath, '', { mode: 'w+' });
    }
  }

  writeFrameCaption(data: FrameWriteDTO) {
    const { stateId, frameId, chunkId, caption } = data;

    this.createStateDir(stateId);

    let filePath: string | null = null;

    if (caption) {
      filePath = this.getFramePath(stateId, chunkId, frameId);
      writeFileSync(filePath, caption, { flag: 'w+' });
    }
    return filePath;
  }
}
