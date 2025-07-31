// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { MigrationInterface, QueryRunner, TableColumn } from 'typeorm';

export class VssMigrations1750138985555 implements MigrationInterface {
  public async up(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.addColumn(
      'state',
      new TableColumn({
        name: 'title',
        type: 'varchar',
        isNullable: false,
        default: '',
      }),
    );
    await queryRunner.addColumn(
      'query',
      new TableColumn({
        name: 'queryStatus',
        type: 'text',
        isNullable: false,
        default: 'idle', // Default status can be 'idle' or 'running'
      }),
    );
  }

  public async down(): Promise<void> {}
}
