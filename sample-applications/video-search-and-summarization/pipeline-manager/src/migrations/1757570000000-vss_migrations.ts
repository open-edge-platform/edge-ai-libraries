// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { MigrationInterface, QueryRunner, TableColumn } from 'typeorm';

export class VssMigrations1757570000000 implements MigrationInterface {
  public async up(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.addColumns('search', [
      new TableColumn({
        name: 'timeFilterValue',
        type: 'int',
        isNullable: true,
      }),
      new TableColumn({
        name: 'timeFilterUnit',
        type: 'text',
        isNullable: true,
      }),
      new TableColumn({
        name: 'timeFilterStart',
        type: 'text',
        isNullable: true,
      }),
      new TableColumn({
        name: 'timeFilterEnd',
        type: 'text',
        isNullable: true,
      }),
    ]);
  }

  public async down(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.dropColumn('search', 'timeFilterEnd');
    await queryRunner.dropColumn('search', 'timeFilterStart');
    await queryRunner.dropColumn('search', 'timeFilterValue');
    await queryRunner.dropColumn('search', 'timeFilterUnit');
  }
}
