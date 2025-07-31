// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { SystemConfig } from 'src/video-upload/models/upload.model';
import {
  Entity,
  PrimaryGeneratedColumn,
  Column,
  CreateDateColumn,
  UpdateDateColumn,
} from 'typeorm';
import {
  FrameSummary,
  InferenceConfig,
  StateActionStatus,
  StateAudio,
  StateChunk,
  StateChunkFrame,
} from './state.model';
import { SummaryPipelineSampling } from 'src/summary/models/summary-pipeline.model';

@Entity('state')
export class StateEntity {
  @PrimaryGeneratedColumn()
  dbId?: number;

  @Column({ unique: true })
  stateId: string;

  @CreateDateColumn()
  createdAt: string;

  @UpdateDateColumn()
  updatedAt: string;

  @Column({ nullable: true, default: '' })
  title: string;

  @Column('jsonb')
  userInputs: SummaryPipelineSampling;

  @Column('jsonb')
  chunks: Record<string, StateChunk>;

  @Column('jsonb')
  frames: Record<string, StateChunkFrame>;

  @Column('jsonb')
  frameSummaries: Record<string, FrameSummary>;

  @Column('jsonb')
  systemConfig: SystemConfig;

  @Column({ nullable: true })
  evamProcessId?: string;

  @Column({ nullable: true })
  summary?: string;

  @Column('jsonb', { nullable: true })
  inferenceConfig?: InferenceConfig;

  @Column('jsonb', { nullable: true })
  audio?: StateAudio;

  @Column({ nullable: false })
  videoId: string;

  @Column('jsonb')
  status: {
    dataStoreUpload: StateActionStatus;
    summarizing: StateActionStatus;
    chunking: StateActionStatus;
  };
}
