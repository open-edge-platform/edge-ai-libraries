// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import {
  Injectable,
  Logger,
  NotFoundException,
  OnModuleDestroy,
  UnprocessableEntityException,
} from '@nestjs/common';
import { OnEvent } from '@nestjs/event-emitter';
import { AxiosResponse, isAxiosError } from 'axios';
import {
  VideoEmbeddingKind,
  VideoEmbeddingsStatusEvent,
  VideoEvents,
} from 'src/events/Pipeline.events';
import { Video, VideoDTO } from '../models/video.model';
import { VideoValidatorService } from './video-validator.service';
import { DatastoreService } from 'src/datastore/services/datastore.service';
import { v4 as uuidv4 } from 'uuid';
import { unlink } from 'fs';
import { VideoDbService } from './video-db.service';
import { lastValueFrom } from 'rxjs';
import { TagsService } from './tags.service';
import { DataPrepShimService } from 'src/data-prep/services/data-prep-shim.service';
import {
  DataPrepBatchJobStatusRO,
  DataPrepBatchProcessDTO,
  DataPrepBatchSubmitRO,
  DataPrepMinioDTO,
  DataPrepMinioRO,
} from 'src/data-prep/models/data-prep.models';

@Injectable()
export class VideoService implements OnModuleDestroy {
  // Matches the data-prep duplicate-content rejection message
  // (Strings.duplicate_upload: "A video with identical content already exists").
  private static readonly DUPLICATE_CONTENT_PATTERN =
    /identical content|duplicate/i;

  // Data-prep batch job states after which no item changes any more.
  private static readonly TERMINAL_BATCH_STATES = new Set([
    'completed',
    'completed_with_errors',
    'failed',
    'cancelled',
  ]);

  // A submitted batch job is followed server-side until it finishes so the
  // per-video embedding status is persisted even when no client polls it.
  static readonly BATCH_TRACK_INTERVAL_MS = 5000;
  static readonly BATCH_TRACK_MAX_MS = 6 * 60 * 60 * 1000;

  private videoMap: Map<string, Video> = new Map();

  private batchTrackers: Map<string, NodeJS.Timeout> = new Map();

  constructor(
    private $validator: VideoValidatorService,
    private $datastore: DatastoreService,
    private $videoDb: VideoDbService,
    private $dataprep: DataPrepShimService,
    private $tags: TagsService,
  ) {}

  private normalizeTags(tags: string[] = []): string[] {
    return Array.from(
      new Set(
        tags
          .map((tag) => tag.trim())
          .filter((tag) => tag.length > 0),
      ),
    );
  }

  isStreamable(videoPath: string) {
    return this.$validator.isStreamable(videoPath);
  }

  // Resolve a video, merge any new tags, and build the data-prep request DTO.
  // Shared by the single-video and batch embedding paths so tag-merge + DTO
  // construction stays consistent.
  private async prepareVideoForEmbedding(
    videoId: string,
    tagsToMerge: string[] = [],
  ): Promise<DataPrepMinioDTO> {
    let video = await this.getVideo(videoId);

    if (!video) {
      throw new NotFoundException('Video not found');
    }

    if (!video.dataStore) {
      throw new UnprocessableEntityException(
        'Video not available in object store',
      );
    }
    const dataStore = video.dataStore;

    const normalizedTagsToMerge = this.normalizeTags(tagsToMerge);
    if (normalizedTagsToMerge.length > 0) {
      const currentTags = this.normalizeTags(video.tags || []);
      const mergedTags = Array.from(new Set([...currentTags, ...normalizedTagsToMerge]));

      if (mergedTags.length !== currentTags.length) {
        const updatedVideo = await this.$videoDb.update(videoId, { tags: mergedTags });
        if (!updatedVideo) {
          throw new UnprocessableEntityException('Failed to update video tags');
        }
        video = updatedVideo;
        this.videoMap.set(videoId, updatedVideo);
      }

      await this.$tags.addTags(normalizedTagsToMerge);
    }

    return {
      bucket_name: dataStore.bucket,
      video_id: dataStore.objectName,
      video_name: dataStore.fileName || video.name,
      tags: video.tags || [],
    };
  }

  onModuleDestroy() {
    for (const timer of this.batchTrackers.values()) {
      clearTimeout(timer);
    }
    this.batchTrackers.clear();
  }

  /**
   * Persist whether a video's embeddings of `kind` exist. Never downgrades a
   * `true`: a failed re-run does not remove embeddings already in the index.
   * Best-effort -- status bookkeeping must never fail the embedding request.
   */
  async setEmbeddingStatus(
    videoId: string,
    kind: VideoEmbeddingKind,
    created: boolean,
  ): Promise<void> {
    try {
      const video = await this.getVideo(videoId);
      if (!video) {
        return;
      }
      if (video[kind] === created || (video[kind] === true && !created)) {
        return;
      }
      const updated = await this.$videoDb.setEmbeddingFlags(videoId, {
        [kind]: created,
      });
      if (updated) {
        this.videoMap.set(videoId, updated);
      }
    } catch (error) {
      Logger.warn(
        `Could not record ${kind}=${created} for video ${videoId}: ${String(error)}`,
        VideoService.name,
      );
    }
  }

  @OnEvent(VideoEvents.EMBEDDINGS_STATUS)
  async onEmbeddingsStatus(event: VideoEmbeddingsStatusEvent) {
    await this.setEmbeddingStatus(event.videoId, event.kind, event.created);
  }

  async createSearchEmbeddings(videoId: string, tagsToMerge: string[] = []) {
    const videoData = await this.prepareVideoForEmbedding(videoId, tagsToMerge);

    let response: AxiosResponse<DataPrepMinioRO>;
    try {
      response = await lastValueFrom(
        this.$dataprep.createEmbeddings(videoData),
      );
    } catch (error) {
      // Only a definitive answer from data-prep means "not embedded". A
      // client-side timeout or connection drop leaves data-prep possibly
      // still working, so the status stays as it was.
      if (isAxiosError(error) && error.response) {
        await this.setEmbeddingStatus(videoId, 'searchEmbeddings', false);
      }
      throw error;
    }

    await this.setEmbeddingStatus(
      videoId,
      'searchEmbeddings',
      response.data?.status === 'success',
    );
    return response;
  }

  // Remove a video row/object that was just uploaded but failed embedding due to
  // duplicate-content rejection in data-prep. Best-effort cleanup.
  async cleanupFailedDuplicateVideo(videoId: string): Promise<void> {
    const video = await this.getVideo(videoId);
    if (!video) {
      return;
    }

    if (video.dataStore?.objectName) {
      try {
        await this.$datastore.deleteObject(video.dataStore.objectName);
      } catch (error) {
        Logger.warn(
          `Best-effort object cleanup failed for duplicate video ${videoId}: ${String(error)}`,
        );
      }
    }

    try {
      await this.$videoDb.remove(videoId);
      this.videoMap.delete(videoId);
    } catch (error) {
      Logger.warn(
        `Best-effort DB cleanup failed for duplicate video ${videoId}: ${String(error)}`,
      );
    }
  }

  // Submit an async batch job to create search embeddings for several videos in
  // a single data-prep request. Returns { job_id, accepted } immediately; the
  // caller polls getSearchEmbeddingsJobStatus() until the job reaches a terminal
  // state.
  async createSearchEmbeddingsBatch(
    videoIds: string[],
    tagsToMerge: string[] = [],
  ): Promise<DataPrepBatchSubmitRO> {
    const items: DataPrepMinioDTO[] = [];
    for (const videoId of videoIds) {
      items.push(await this.prepareVideoForEmbedding(videoId, tagsToMerge));
    }

    const payload: DataPrepBatchProcessDTO = { items };
    const response = await lastValueFrom(
      this.$dataprep.createEmbeddingsBatch(payload),
    );
    if (response.data?.job_id) {
      this.trackBatchJob(response.data.job_id);
    }
    return response.data;
  }

  async getSearchEmbeddingsJobStatus(
    jobId: string,
  ): Promise<DataPrepBatchJobStatusRO> {
    const response = await lastValueFrom(
      this.$dataprep.getBatchJobStatus(jobId),
    );
    const status = response.data;

    // The batch job answers 202 up-front, so a duplicate-content rejection can
    // only surface here as a per-item failure. Mirror what the single-video path
    // does on a synchronous 409: drop the row/object we optimistically created,
    // otherwise the rejected video lingers as an orphan the UI can never play.
    // cleanupFailedDuplicateVideo is idempotent, so repeated polling is safe.
    await this.cleanupDuplicateBatchFailures(status);
    await this.recordBatchEmbeddingStatus(status);

    return status;
  }

  // Persist searchEmbeddings for every finished item. Idempotent, so it is
  // safe on every poll from the UI and from the server-side tracker.
  private async recordBatchEmbeddingStatus(
    status: DataPrepBatchJobStatusRO,
  ): Promise<void> {
    for (const item of status?.items ?? []) {
      if (!item.video_id) {
        continue;
      }
      if (item.status === 'success') {
        await this.setEmbeddingStatus(item.video_id, 'searchEmbeddings', true);
      } else if (
        item.status === 'error' &&
        !VideoService.DUPLICATE_CONTENT_PATTERN.test(item.message ?? '')
      ) {
        await this.setEmbeddingStatus(item.video_id, 'searchEmbeddings', false);
      }
    }
  }

  // Follow a batch job until it reaches a terminal state (or is evicted, or
  // the time budget runs out), so its results reach the video rows even if
  // the submitting client goes away.
  private trackBatchJob(jobId: string): void {
    if (this.batchTrackers.has(jobId)) {
      return;
    }
    const deadline = Date.now() + VideoService.BATCH_TRACK_MAX_MS;

    const schedule = () => {
      const timer = setTimeout(
        () => void tick(),
        VideoService.BATCH_TRACK_INTERVAL_MS,
      );
      timer.unref?.();
      this.batchTrackers.set(jobId, timer);
    };

    const tick = async () => {
      let done = Date.now() >= deadline;
      try {
        const status = await this.getSearchEmbeddingsJobStatus(jobId);
        done ||= VideoService.TERMINAL_BATCH_STATES.has(status?.state);
      } catch (error) {
        if (isAxiosError(error) && error.response?.status === 404) {
          done = true;
        } else {
          Logger.warn(
            `Batch embeddings job ${jobId} status poll failed: ${String(error)}`,
            VideoService.name,
          );
        }
      }
      if (done || !this.batchTrackers.has(jobId)) {
        this.batchTrackers.delete(jobId);
        return;
      }
      schedule();
    };

    schedule();
  }

  // Best-effort cleanup of items a batch job rejected as duplicate content.
  // Never throws: polling must keep working even if cleanup fails.
  private async cleanupDuplicateBatchFailures(
    status: DataPrepBatchJobStatusRO,
  ): Promise<void> {
    for (const item of status?.items ?? []) {
      if (item.status !== 'error' || !item.video_id) {
        continue;
      }
      if (!VideoService.DUPLICATE_CONTENT_PATTERN.test(item.message ?? '')) {
        continue;
      }
      try {
        await this.cleanupFailedDuplicateVideo(item.video_id);
      } catch (error) {
        Logger.warn(
          `Best-effort cleanup failed for duplicate batch item ${item.video_id}: ${String(error)}`,
        );
      }
    }
  }

  async uploadVideo(
    videoFilePath: string,
    videoFileName: string,
    videoData: VideoDTO,
  ): Promise<string> {
    Logger.log('Uploading video', videoFilePath, videoFileName, videoData);
    const safeVideoFilePath = this.$validator.resolveSafeUploadPath(videoFilePath);

    const videoId = uuidv4();

    const { objectPath } = this.$datastore.getObjectName(
      videoId,
      videoFileName,
    );

    try {
      await this.$datastore.uploadFile(objectPath, safeVideoFilePath);
    } catch (error) {
      Logger.error('Error uploading video file to object storage', error);
      throw new UnprocessableEntityException(
        'Error uploading video file to object storage',
      );
    }

    unlink(safeVideoFilePath, (err) => {
      if (err) {
        Logger.error('Error deleting file', err);
      }
    });

    const video: Video = {
      name: videoFileName,
      tags: [],
      dataStore: {
        bucket: this.$datastore.bucket,
        fileName: videoFileName,
        objectName: videoId,
      },
      videoId,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      url: objectPath,
    };

    let tagsToAdd: string[] = [];

    if (videoData.tagsArray && videoData.tagsArray.length > 0) {
      video.tags = videoData.tagsArray;
      tagsToAdd = videoData.tagsArray;
    }

    if (videoData.name) {
      video.name = videoData.name;
    }

    try {
      const videoDB = await this.$videoDb.create(video);
      if (tagsToAdd.length > 0) {
        Logger.log('Adding video tags', tagsToAdd);
        await this.$tags.addTags(tagsToAdd);
      }
      this.videoMap.set(video.videoId, videoDB);
    } catch (error) {
      Logger.error('Error saving video to database', error);
      throw new UnprocessableEntityException('Error saving video to database');
    }

    return videoId;
  }

  /**
   * Add an existing video again as a new, independent video, as if its file
   * were uploaded again: the stored file is copied server-side to a new id and
   * a new record is created with the same name. Embeddings and summaries are
   * not carried over; callers create them for the returned id.
   */
  async copyVideo(
    sourceVideoId: string,
    tagsToMerge: string[] = [],
  ): Promise<string> {
    const source = await this.getVideo(sourceVideoId);

    if (!source) {
      throw new NotFoundException('Video not found');
    }

    if (!source.dataStore || !source.url) {
      throw new UnprocessableEntityException(
        'Video not available in object store',
      );
    }

    const videoId = uuidv4();
    const fileName = source.dataStore.fileName || source.name;
    const { objectPath } = this.$datastore.getObjectName(videoId, fileName);

    try {
      await this.$datastore.copyObject(source.url, objectPath);
    } catch (error) {
      Logger.error('Error copying video in object storage', error);
      throw new UnprocessableEntityException(
        'Error copying video in object storage',
      );
    }

    const tags = this.normalizeTags([...(source.tags || []), ...tagsToMerge]);
    const now = new Date().toISOString();
    const video: Video = {
      name: source.name,
      tags,
      dataStore: {
        bucket: this.$datastore.bucket,
        fileName,
        objectName: videoId,
      },
      videoId,
      createdAt: now,
      updatedAt: now,
      url: objectPath,
    };

    let videoDB: Video;
    try {
      videoDB = await this.$videoDb.create(video);
    } catch (error) {
      Logger.error('Error saving video copy to database', error);
      try {
        await this.$datastore.deleteObject(objectPath);
      } catch (cleanupError) {
        Logger.warn(
          `Best-effort cleanup failed for copied object ${objectPath}: ${String(cleanupError)}`,
        );
      }
      throw new UnprocessableEntityException('Error saving video to database');
    }
    this.videoMap.set(videoId, videoDB);

    if (tags.length > 0) {
      try {
        await this.$tags.addTags(tags);
      } catch (error) {
        Logger.warn(
          `Could not register tags for video copy ${videoId}: ${String(error)}`,
        );
      }
    }

    return videoId;
  }

  async getVideos(): Promise<Video[]> {
    const videoList = await this.$videoDb.readAll();

    for (const video of videoList) {
      this.videoMap.set(video.videoId, video);
    }

    return videoList ?? [];
  }

  async getVideo(videoId: string): Promise<Video | null> {
    if (this.videoMap.has(videoId)) {
      return this.videoMap.get(videoId) ?? null;
    }
    const video = await this.$videoDb.read(videoId);

    if (video) {
      this.videoMap.set(videoId, video);
    }

    return video ?? null;
  }
}
