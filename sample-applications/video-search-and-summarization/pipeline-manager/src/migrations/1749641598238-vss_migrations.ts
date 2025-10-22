// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { MigrationInterface, QueryRunner, Table } from 'typeorm';

export class VssMigrations1749641598238 implements MigrationInterface {
  public async up(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.createTable(
      new Table({
        name: 'tags',
        columns: [
          {
            name: 'dbId',
            type: 'int',
            isPrimary: true,
            isGenerated: true,
            generationStrategy: 'increment',
          },
          { name: 'tag', type: 'varchar', isUnique: true },
          {
            name: 'createdAt',
            type: 'timestamp',
            default: 'CURRENT_TIMESTAMP',
          },
        ],
      }),
    );
  }

  public async down(queryRunner: QueryRunner): Promise<void> {}
}
