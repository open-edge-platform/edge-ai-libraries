// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Column, Entity, PrimaryGeneratedColumn } from 'typeorm';
import { ExampleStatus } from './example.model';

@Entity('example')
export class ExampleEntity {
  @PrimaryGeneratedColumn()
  dbId?: number;

  @Column({ unique: true })
  exampleId: string;

  @Column({ type: 'text', nullable: false })
  title: string;

  @Column({ type: 'text', default: 'idle' })
  status: ExampleStatus;

  @Column('jsonb', { nullable: true })
  metadata?: Record<string, unknown>;

  @Column({ type: 'text' })
  createdAt: string;

  @Column({ type: 'text' })
  updatedAt: string;
}
