// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { MigrationInterface, QueryRunner, Table } from 'typeorm';

export class TableCreator1747303546691 implements MigrationInterface {
  public async up(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.createTable(
      new Table({
        name: 'state',
        columns: [
          {
            name: 'dbId',
            type: 'int',
            isPrimary: true,
            isGenerated: true,
            generationStrategy: 'increment',
          },
          {
            name: 'stateId',
            type: 'varchar',
            isUnique: true,
          },
          {
            name: 'createdAt',
            type: 'timestamp',
            default: 'CURRENT_TIMESTAMP',
          },
          {
            name: 'updatedAt',
            type: 'timestamp',
            default: 'CURRENT_TIMESTAMP',
            onUpdate: 'CURRENT_TIMESTAMP',
          },
          {
            name: 'userInputs',
            type: 'jsonb',
          },
          {
            name: 'chunks',
            type: 'jsonb',
          },
          {
            name: 'frames',
            type: 'jsonb',
          },
          {
            name: 'frameSummaries',
            type: 'jsonb',
          },
          {
            name: 'systemConfig',
            type: 'jsonb',
          },
          {
            name: 'evamProcessId',
            type: 'varchar',
            isNullable: true,
          },
          {
            name: 'summary',
            type: 'varchar',
            isNullable: true,
          },
          {
            name: 'inferenceConfig',
            type: 'jsonb',
            isNullable: true,
          },
          {
            name: 'audio',
            type: 'jsonb',
            isNullable: true,
          },
          {
            name: 'videoId',
            type: 'varchar',
            isNullable: false,
          },
          {
            name: 'status',
            type: 'jsonb',
          },
        ],
      }),
      true,
    );

    await queryRunner.createTable(
      new Table({
        name: 'video',
        columns: [
          {
            name: 'dbId',
            type: 'int',
            isPrimary: true,
            isGenerated: true,
            generationStrategy: 'increment',
          },
          {
            name: 'videoId',
            type: 'varchar',
            isUnique: true,
          },
          {
            name: 'name',
            type: 'varchar',
          },
          {
            name: 'url',
            type: 'varchar',
          },
          {
            name: 'tags',
            type: 'varchar',
            isArray: true,
          },
          {
            name: 'createdAt',
            type: 'varchar',
          },
          {
            name: 'updatedAt',
            type: 'varchar',
          },
          {
            name: 'summaryId',
            type: 'varchar',
            isNullable: true,
          },
          {
            name: 'textEmbeddings',
            type: 'boolean',
            default: false,
            isNullable: true,
          },
          {
            name: 'videoEmbeddings',
            type: 'boolean',
            default: false,
            isNullable: true,
          },
          {
            name: 'dataStore',
            type: 'jsonb',
            isNullable: true,
          },
        ],
      }),
      true,
    );
  }

  public async down(queryRunner: QueryRunner): Promise<void> {}
}
