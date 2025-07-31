// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Injectable } from '@nestjs/common';
import { AudioService } from 'src/audio/services/audio.service';
import { StateService } from '../services/state.service';
import { EventEmitter2, OnEvent } from '@nestjs/event-emitter';
import { PipelineEvents } from 'src/events/Pipeline.events';
import { AudioDevice, AudioTranscriptDTO } from 'src/audio/models/audio.model';
import { ConfigService } from '@nestjs/config';
import { AppEvents } from 'src/events/app.events';

export interface AudioQueueItem {
  stateId: string;
}

@Injectable()
export class AudioQueueService {
  audioProcessing: Set<string> = new Set<string>();

  constructor(
    private $state: StateService,
    private $audio: AudioService,
    private $emitter: EventEmitter2,
    private $config: ConfigService,
  ) {}

  @OnEvent(PipelineEvents.AUDIO_COMPLETE)
  async audioComplete({
    stateId,
    transcriptPath,
  }: {
    stateId: string;
    transcriptPath: string;
  }) {
    const state = this.$state.fetch(stateId);
    if (state) {
      const fileName = transcriptPath.split('/').pop()!;
      const minioPath = [state.video.videoId, fileName].join('/');
      try {
        const transcripts = await this.$audio.parseTranscript(minioPath);
        this.$state.audioComplete(stateId, { transcriptPath, transcripts });
        this.$emitter.emit(PipelineEvents.CHECK_QUEUE_STATUS, [stateId]);
      } catch (error) {
        console.log('TRANSCRIPT ERROR', error);
      }
    }
  }

  @OnEvent(AppEvents.SUMMARY_REMOVED)
  removeAudioProcessing(stateId: string) {
    this.audioProcessing.delete(stateId);
  }

  @OnEvent(PipelineEvents.AUDIO_TRIGGERED)
  startAudioProcessing(stateId: string) {
    this.audioProcessing.add(stateId);

    const state = this.$state.fetch(stateId);

    if (state && state.systemConfig.audioModel && state.video.dataStore) {
      const device = this.$config.get<AudioDevice>('audio.device')!;
      const minio_bucket = this.$config.get<string>('datastore.bucketName')!;

      const model_name = state.systemConfig.audioModel;

      const transcriptDTO: AudioTranscriptDTO = {
        device,
        include_timestamps: true,
        minio_bucket,
        model_name,
        video_id: state.video.dataStore.objectName,
        video_name: state.video.dataStore.fileName,
      };

      console.log('AUDIO CALL', transcriptDTO);

      this.$state.audioTrigger(stateId, transcriptDTO);
      this.$audio.generateTranscript(transcriptDTO).subscribe({
        next: (res) => {
          if (res) {
            console.log('AUDIO RESPONSE', res.status, res.data);
            this.audioProcessing.delete(stateId);
            this.$emitter.emit(PipelineEvents.AUDIO_COMPLETE, {
              stateId,
              transcriptPath: res.data.transcript_path,
            });
            this.$emitter.emit(PipelineEvents.CHUNKING_STATUS, [stateId]);
          }
        },
        error: (err) => {
          console.log('AUDIO ERROR', err.data);
          this.audioProcessing.delete(stateId);
          this.$emitter.emit(PipelineEvents.AUDIO_ERROR, stateId);
          this.$emitter.emit(PipelineEvents.CHECK_QUEUE_STATUS, [stateId]);
        },
      });
    }
  }

  isAudioProcessing(stateId: string): boolean {
    return this.audioProcessing.has(stateId);
  }
}
