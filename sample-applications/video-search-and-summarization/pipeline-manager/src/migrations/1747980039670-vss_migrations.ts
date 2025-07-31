// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { MigrationInterface, QueryRunner, Table } from 'typeorm';

export class VssMigrations1747980039670 implements MigrationInterface {
  public async up(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.createTable(
      new Table({
        name: 'search',
        columns: [
          {
            name: 'dbId',
            type: 'int',
            isPrimary: true,
            isGenerated: true,
            generationStrategy: 'increment',
          },
          { name: 'queryId', type: 'varchar', isUnique: true },
          { name: 'query', type: 'text' },
          { name: 'watch', type: 'boolean', default: false },
          { name: 'tags', type: 'text', isArray: true, default: [] },
          { name: 'results', type: 'jsonb', isNullable: true },
          { name: 'createdAt', type: 'text' },
          { name: 'updatedAt', type: 'text' },
        ],
      }),
      true,
    );
  }

  public async down(queryRunner: QueryRunner): Promise<void> {}
}
