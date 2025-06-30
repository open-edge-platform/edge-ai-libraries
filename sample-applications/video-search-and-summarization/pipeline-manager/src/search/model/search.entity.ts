// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { Column, Entity, PrimaryGeneratedColumn } from 'typeorm';
import { SearchResult } from './search.model';

@Entity('search')
export class SearchEntity {
  @PrimaryGeneratedColumn()
  dbId?: number;

  @Column({ unique: true })
  queryId: string;

  @Column({ type: 'text', nullable: false })
  query: string;

  @Column({ type: 'boolean', default: false })
  watch: boolean;

  @Column({ type: 'text', array: true, default: [] })
  tags: string[];

  @Column('jsonb', { nullable: true })
  results: SearchResult[];

  @Column({ type: 'text' })
  createdAt: string;

  @Column({ type: 'text' })
  updatedAt: string;
}
