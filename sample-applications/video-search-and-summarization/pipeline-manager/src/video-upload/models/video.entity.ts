// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Column, Entity, PrimaryGeneratedColumn } from 'typeorm';
import { VideoDatastoreInfo } from './video.model';

@Entity('video')
export class VideoEntity {
  @PrimaryGeneratedColumn()
  dbId?: number;

  @Column({ unique: true })
  videoId: string;

  @Column({ type: 'text', nullable: false })
  name: string;

  @Column({ type: 'text', nullable: false })
  url: string;

  @Column({ type: 'text', array: true })
  tags: string[];

  @Column({ type: 'text' })
  createdAt: string;

  @Column({ type: 'text' })
  updatedAt: string;

  @Column({ nullable: true })
  summaryId?: string;

  @Column({ nullable: true })
  textEmbeddings?: boolean;

  @Column({ nullable: true })
  videoEmbeddings?: boolean;

  @Column({ nullable: true })
  searchEmbeddings?: boolean;

  @Column('jsonb', { nullable: true })
  dataStore?: VideoDatastoreInfo;
}
