import {
  Injectable,
  Logger,
  NotFoundException,
  UnprocessableEntityException,
} from '@nestjs/common';
import { Video, VideoDTO } from '../models/video.model';
import { VideoValidatorService } from './video-validator.service';
import { DatastoreService } from 'src/datastore/services/datastore.service';
import { v4 as uuidv4 } from 'uuid';
import { unlink } from 'fs';
import { VideoDbService } from './video-db.service';
import { SearchDataPrepShimService } from 'src/search/services/search-data-prep-shim.service';
import { DataPrepMinioDTO } from 'src/search/model/search.model';
import { lastValueFrom } from 'rxjs';

@Injectable()
export class VideoService {
  private videoMap: Map<string, Video> = new Map();

  constructor(
    private $validator: VideoValidatorService,
    private $datastore: DatastoreService,
    private $videoDb: VideoDbService,
    private $dataprep: SearchDataPrepShimService,
  ) {}

  isStreamable(videoPath: string) {
    return this.$validator.isStreamable(videoPath);
  }

  async createSearchEmbeddings(videoId: string) {
    const video = await this.getVideo(videoId);

    if (!video) {
      throw new NotFoundException('Video not found');
    }

    if (!video.dataStore) {
      throw new UnprocessableEntityException(
        'Video not available in object store',
      );
    }

    const videoData: DataPrepMinioDTO = {
      bucket_name: video.dataStore.bucket,
      video_id: video.dataStore?.objectName,
      video_name: video.dataStore?.fileName,
    };

    return await lastValueFrom(this.$dataprep.createEmbeddings(videoData));
  }

  async uploadVideo(
    videoFilePath: string,
    videoFileName: string,
    videoData: VideoDTO,
  ): Promise<string> {
    Logger.log('Uploading video', videoFilePath, videoFileName, videoData);

    const videoId = uuidv4();

    const { objectPath } = this.$datastore.getObjectName(
      videoId,
      videoFileName,
    );

    try {
      await this.$datastore.uploadFile(objectPath, videoFilePath);
    } catch (error) {
      Logger.error('Error uploading video file to object storage', error);
      throw new UnprocessableEntityException(
        'Error uploading video file to object storage',
      );
    }

    unlink(videoFilePath, (err) => {
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

    if (videoData.tagsArray) {
      video.tags = videoData.tagsArray;
    }

    if (videoData.name) {
      video.name = videoData.name;
    }

    try {
      const videoDB = await this.$videoDb.create(video);
      this.videoMap.set(video.videoId, videoDB);
    } catch (error) {
      Logger.error('Error saving video to database', error);
      throw new UnprocessableEntityException('Error saving video to database');
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
