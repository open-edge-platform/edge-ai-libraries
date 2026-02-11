// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Column, Entity, PrimaryGeneratedColumn } from 'typeorm';
import { SearchQueryStatus, SearchResult } from './search.model';

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

  @Column({
    type: 'enum',
    default: SearchQueryStatus.IDLE,
    enum: SearchQueryStatus,
  })
  queryStatus: SearchQueryStatus; // This can be 'idle', 'running', or 'error'

  @Column({ type: 'text', array: true, default: [] })
  tags: string[];

  @Column({ type: 'int', nullable: true })
  timeFilterValue?: number | null;

  @Column({ type: 'text', nullable: true })
  timeFilterUnit?: string | null;

  @Column({ type: 'text', nullable: true })
  timeFilterStart?: string | null;

  @Column({ type: 'text', nullable: true })
  timeFilterEnd?: string | null;

  @Column('jsonb', { nullable: true })
  results: SearchResult[];

  @Column({ type: 'text' })
  createdAt: string;

  @Column({ type: 'text' })
  updatedAt: string;

  @Column({ type: 'text', nullable: true })
  errorMessage?: string;
}
