// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import {
  MigrationInterface,
  QueryRunner,
  TableColumn,
  TableIndex,
} from 'typeorm';

export class VssMigrations1758000000000 implements MigrationInterface {
  private static readonly WATCH_INDEX = 'IDX_search_watch';

  public async up(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.addColumns('search', [
      new TableColumn({
        name: 'lastRefreshedAt',
        type: 'text',
        isNullable: true,
      }),
      new TableColumn({
        name: 'resultsFingerprint',
        type: 'text',
        isNullable: true,
      }),
    ]);

    await queryRunner.createIndex(
      'search',
      new TableIndex({
        name: VssMigrations1758000000000.WATCH_INDEX,
        columnNames: ['watch'],
      }),
    );
  }

  public async down(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.dropIndex(
      'search',
      VssMigrations1758000000000.WATCH_INDEX,
    );
    await queryRunner.dropColumn('search', 'resultsFingerprint');
    await queryRunner.dropColumn('search', 'lastRefreshedAt');
  }
}
