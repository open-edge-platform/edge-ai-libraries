// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import {
  BadGatewayException,
  BadRequestException,
  Controller,
  Get,
  Logger,
  NotFoundException,
  Query,
  RequestTimeoutException,
  Res,
  ServiceUnavailableException,
  UsePipes,
  ValidationPipe,
} from '@nestjs/common';
import { ApiOperation, ApiResponse, ApiTags } from '@nestjs/swagger';
import { isAxiosError } from 'axios';
import { Response } from 'express';
import { FrameQueryDto } from '../models/frame.model';
import { FrameShimService } from '../services/frame-shim.service';

/**
 * On-demand single-frame retrieval, proxied to multimodal-dataprep.
 *
 * No global route prefix is set in `main.ts` — nginx supplies `/manager` — so
 * this resolves to `GET /manager/frames` from the browser.
 *
 * Intended consumer: a downstream agent (or the UI) that has a search result's
 * `best_frame_info` and wants the actual pixels of that peak-scoring frame to
 * hand to a VLM. dataprep decodes the frame on demand and never persists it.
 *
 * `ValidationPipe` is applied here only (not globally): `media_path` and
 * `crop_bbox` are caller-supplied and reach a decoder upstream, so
 * `forbidNonWhitelisted` makes a malformed request a visible 400.
 */
@ApiTags('Frames')
@Controller('frames')
@UsePipes(
  new ValidationPipe({
    whitelist: true,
    forbidNonWhitelisted: true,
    transform: true,
  }),
)
export class FrameController {
  private readonly logger = new Logger(FrameController.name);

  constructor(private readonly $shim: FrameShimService) {}

  /** Best-effort extraction of an upstream error detail from an axios error. */
  private detailOf(error: unknown): string | undefined {
    if (!isAxiosError(error)) return undefined;
    const data = error.response?.data;
    // responseType is arraybuffer, so an error body arrives as bytes.
    if (data instanceof Buffer || data instanceof ArrayBuffer) {
      try {
        const parsed = JSON.parse(Buffer.from(data as ArrayBuffer).toString('utf8'));
        return parsed?.detail ?? parsed?.message;
      } catch {
        return undefined;
      }
    }
    return (
      (data as { detail?: string } | undefined)?.detail ??
      (data as { message?: string } | undefined)?.message
    );
  }

  private fail(error: unknown): never {
    if (!this.$shim.isConfigured) {
      throw new ServiceUnavailableException(
        'Frame retrieval is not available: no dataprep endpoint is configured.',
      );
    }

    if (isAxiosError(error)) {
      const status = error.response?.status;
      const detail = this.detailOf(error);

      if (error.code === 'ECONNABORTED' || error.code === 'ETIMEDOUT') {
        throw new RequestTimeoutException('Frame service did not respond in time.');
      }

      switch (status) {
        case 400:
          throw new BadRequestException(detail ?? 'Invalid frame request.');
        case 404:
          throw new NotFoundException(detail ?? 'Media or frame not found.');
        default:
          break;
      }
    }

    this.logger.error(
      `Frame retrieval failed: ${error instanceof Error ? error.message : 'unknown error'}`,
    );
    throw new BadGatewayException('Frame service error.');
  }

  @Get()
  @ApiOperation({
    summary:
      'Extract one frame of stored media (full frame or detected-crop region) by location + time.',
  })
  @ApiResponse({
    status: 200,
    description:
      'Raw image/jpeg bytes by default, or a JSON object (base64 image + metadata) when format=json.',
  })
  async getFrame(
    @Query() query: FrameQueryDto,
    @Res() res: Response,
  ): Promise<void> {
    try {
      const { body, contentType, frameHeaders } =
        await this.$shim.getFrame(query);
      res.set({ ...frameHeaders, 'Content-Type': contentType });
      res.send(body);
    } catch (error) {
      this.fail(error);
    }
  }
}
