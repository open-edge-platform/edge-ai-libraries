// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Injectable } from '@nestjs/common';
import { readFile } from 'fs/promises';

@Injectable()
export class VideoValidatorService {
  private findAtom(buffer: Buffer, atomType: string) {
    for (let i = 0; i < buffer.length - 4; i++) {
      if (
        buffer[i] === atomType.charCodeAt(0) &&
        buffer[i + 1] === atomType.charCodeAt(1) &&
        buffer[i + 2] === atomType.charCodeAt(2) &&
        buffer[i + 3] === atomType.charCodeAt(3)
      ) {
        return i;
      }
    }
    return -1;
  }

  async isStreamable(filePath: string): Promise<boolean> {
    try {
      const fileBuffer = await readFile(filePath);

      const moovIndex = this.findAtom(fileBuffer, 'moov');
      const mdatIndex = this.findAtom(fileBuffer, 'mdat');

  // If either atom is missing, treat as not streamable
  if (moovIndex === -1 || mdatIndex === -1) return false;

  return moovIndex < mdatIndex;
    } catch (error) {
      console.log(error);
  throw error;
    }
  }
}
