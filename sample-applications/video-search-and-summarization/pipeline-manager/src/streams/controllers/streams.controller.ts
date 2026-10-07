// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import {
  BadGatewayException,
  BadRequestException,
  Body,
  Controller,
  Delete,
  Get,
  HttpCode,
  HttpStatus,
  Logger,
  NotFoundException,
  Param,
  Patch,
  Post,
  Query,
  RequestTimeoutException,
  ServiceUnavailableException,
  UsePipes,
  ValidationPipe,
} from '@nestjs/common';
import { EventEmitter2 } from '@nestjs/event-emitter';
import { ApiOperation, ApiResponse, ApiTags } from '@nestjs/swagger';
import { isAxiosError } from 'axios';
import { SearchEvents } from 'src/events/Pipeline.events';
import {
  LiveStreamBatchCreateDto,
  LiveStreamBatchDeleteDto,
  LiveStreamBatchRO,
  LiveStreamCreateDto,
  LiveStreamDeleteRO,
  LiveStreamListQueryDto,
  LiveStreamListRO,
  LiveStreamPurgeQueryDto,
  LiveStreamRO,
  LiveStreamState,
  LiveStreamUpdateDto,
} from '../models/stream.model';
import { StreamPollerService } from '../services/stream-poller.service';
import { StreamShimService } from '../services/stream-shim.service';

/**
 * Live (RTSP) stream CRUD, proxied to multimodal-dataprep.
 *
 * No global route prefix is set in `main.ts` — nginx supplies `/manager` — so
 * these resolve to `/manager/streams/**` from the browser.
 *
 * The `ValidationPipe` is applied **here only**, not globally. A global pipe
 * would retroactively enforce every existing DTO in the application, which is
 * a change with an unbounded blast radius and belongs in its own PR. This
 * controller needs it because `stream_url` is attacker-influenced input that
 * is handed to a decoder, and because `forbidNonWhitelisted` is what makes an
 * attempt to PATCH `stream_url` a visible 400 rather than a silent no-op.
 */
@ApiTags('Live Streams')
@Controller('streams')
@UsePipes(
  new ValidationPipe({
    whitelist: true,
    forbidNonWhitelisted: true,
    transform: true,
    transformOptions: { enableImplicitConversion: false },
  }),
)
export class StreamsController {
  private readonly logger = new Logger(StreamsController.name);

  constructor(
    private readonly $shim: StreamShimService,
    private readonly $poller: StreamPollerService,
    private readonly $emitter: EventEmitter2,
  ) {}

  /**
   * Mark the search index dirty after a delete that purged live embeddings.
   *
   * The poll loop only emits EMBEDDINGS_UPDATE when the aggregate embedding
   * count *grows*, so a purge (which shrinks it, or removes the stream from the
   * list entirely) would never trigger a watched-query refresh. Without this,
   * "checkmarked" queries keep showing results that point at segments whose
   * embeddings and media have just been deleted. Emitting here re-uses the same
   * bounded-rate refresh scheduler as ingestion, so the watched queries re-run
   * and drop the now-dangling references.
   */
  private notifyEmbeddingsPurged(): void {
    this.$emitter.emit(SearchEvents.EMBEDDINGS_UPDATE);
  }

  /**
   * Translate an upstream failure into the matching Nest exception.
   *
   * Never includes the request body in a message: on the create path that body
   * holds the RTSP credential.
   */
  private fail(error: unknown, context: string): never {
    if (!this.$shim.isConfigured) {
      throw new ServiceUnavailableException(
        'Live stream ingestion is not available: no dataprep endpoint is configured.',
      );
    }

    if (isAxiosError(error)) {
      const status = error.response?.status;
      const detail =
        (error.response?.data as { detail?: string } | undefined)?.detail ??
        (error.response?.data as { message?: string } | undefined)?.message;

      if (error.code === 'ECONNABORTED' || error.code === 'ETIMEDOUT') {
        throw new RequestTimeoutException(
          `Live stream service did not respond in time (${context}).`,
        );
      }

      switch (status) {
        case HttpStatus.BAD_REQUEST:
          throw new BadRequestException(detail ?? 'Invalid live stream request.');
        case HttpStatus.NOT_FOUND:
          throw new NotFoundException(detail ?? 'Live stream not found.');
        case HttpStatus.SERVICE_UNAVAILABLE:
          // dataprep returns this at its concurrency cap. Surface the upstream
          // text so the user is told to pause or remove a stream, rather than
          // seeing a generic failure.
          throw new ServiceUnavailableException(
            detail ??
              'The maximum number of concurrent live streams is already running.',
          );
        default:
          break;
      }
    }

    this.logger.error(
      `Live stream ${context} failed: ${
        error instanceof Error ? error.message : 'unknown error'
      }`,
    );
    throw new BadGatewayException(`Live stream service error (${context}).`);
  }

  @Post()
  @HttpCode(HttpStatus.ACCEPTED)
  @ApiOperation({ summary: 'Register and start one RTSP stream.' })
  @ApiResponse({ status: 202, description: 'Stream registered.' })
  async create(@Body() body: LiveStreamCreateDto): Promise<LiveStreamRO> {
    try {
      const result = await this.$shim.create(body);
      // Kick the poller so watched-query refresh works during live ingestion
      // even if nobody has the Live Streams view open.
      this.$poller.ensurePolling();
      return result;
    } catch (error) {
      this.fail(error, 'create');
    }
  }

  @Post('batch')
  @HttpCode(HttpStatus.ACCEPTED)
  @ApiOperation({ summary: 'Register several RTSP streams in one call.' })
  async createBatch(
    @Body() body: LiveStreamBatchCreateDto,
  ): Promise<LiveStreamBatchRO> {
    try {
      const result = await this.$shim.createBatch(body);
      this.$poller.ensurePolling();
      return result;
    } catch (error) {
      this.fail(error, 'batch create');
    }
  }

  @Get()
  @ApiOperation({ summary: 'List registered live streams.' })
  async list(
    @Query() query: LiveStreamListQueryDto,
  ): Promise<LiveStreamListRO> {
    try {
      return await this.$shim.list(query);
    } catch (error) {
      this.fail(error, 'list');
    }
  }

  @Get(':streamId')
  @ApiOperation({ summary: 'Get one live stream.' })
  async get(@Param('streamId') streamId: string): Promise<LiveStreamRO> {
    try {
      return await this.$shim.get(streamId);
    } catch (error) {
      this.fail(error, 'get');
    }
  }

  @Patch(':streamId')
  @ApiOperation({
    summary: 'Update a live stream, or pause/resume it via `state`.',
  })
  async update(
    @Param('streamId') streamId: string,
    @Body() body: LiveStreamUpdateDto,
  ): Promise<LiveStreamRO> {
    try {
      const result = await this.$shim.update(streamId, body);
      // Resuming a paused stream must restart the poll loop if it had idled.
      if (body.state === LiveStreamState.RUNNING) {
        this.$poller.ensurePolling();
      }
      return result;
    } catch (error) {
      this.fail(error, 'update');
    }
  }

  @Delete(':streamId')
  @ApiOperation({
    summary:
      'Stop and deregister a live stream. Captured footage is retained ' +
      'unless the purge flags are set.',
  })
  async remove(
    @Param('streamId') streamId: string,
    @Query() purge: LiveStreamPurgeQueryDto,
  ): Promise<LiveStreamDeleteRO> {
    try {
      const result = await this.$shim.remove(streamId, purge);
      // A purge removes vectors behind existing search hits; re-run watched
      // queries so they stop referencing the deleted segments.
      if ((result.embeddings_purged ?? 0) > 0) {
        this.notifyEmbeddingsPurged();
      }
      return result;
    } catch (error) {
      this.fail(error, 'delete');
    }
  }

  @Delete()
  @ApiOperation({ summary: 'Stop and deregister several live streams.' })
  async removeBatch(
    @Body() body: LiveStreamBatchDeleteDto,
    @Query() purge: LiveStreamPurgeQueryDto,
  ): Promise<LiveStreamBatchRO> {
    try {
      const result = await this.$shim.removeBatch(body, purge);
      // The batch response carries no purge counts, so fall back to intent: if
      // embeddings were requested to be purged and at least one stream was
      // deleted, some vectors are gone and watched queries must be re-run.
      if (purge.purge_embeddings && result.accepted > 0) {
        this.notifyEmbeddingsPurged();
      }
      return result;
    } catch (error) {
      this.fail(error, 'batch delete');
    }
  }
}
