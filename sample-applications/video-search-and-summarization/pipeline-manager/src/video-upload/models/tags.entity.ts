// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import {
  Column,
  CreateDateColumn,
  Entity,
  PrimaryGeneratedColumn,
} from 'typeorm';

@Entity('tag')
export class TagEntity {
  @PrimaryGeneratedColumn()
  dbId?: number;

  @Column({ type: 'text', nullable: false })
  tag: string;

  @CreateDateColumn()
  createdAt: string;
}
