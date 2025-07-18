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
