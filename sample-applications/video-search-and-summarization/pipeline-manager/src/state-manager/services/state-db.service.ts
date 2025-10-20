// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { StateEntity } from '../models/state.entity';
import { Repository } from 'typeorm';

@Injectable()
export class StateDbService {
  constructor(
    @InjectRepository(StateEntity) private stateRepo: Repository<StateEntity>,
  ) {}

  async getAllStates(): Promise<StateEntity[]> {
    return this.stateRepo.find();
  }

  async addState(state: StateEntity): Promise<StateEntity> {
    const newState = this.stateRepo.create(state);
    return this.stateRepo.save(newState);
  }

  async getState(stateId: string): Promise<StateEntity | null> {
    const state = await this.stateRepo.findOne({
      where: { stateId },
    });
    return state ?? null;
  }

  async removeState(stateId: string): Promise<boolean> {
    const result = await this.stateRepo.delete({ stateId });
    return result.affected !== 0;
  }

  async updateState(
    stateId: string,
    state: Partial<StateEntity>,
  ): Promise<StateEntity | null> {
    const existingState = await this.getState(stateId);
    if (!existingState) {
      return null;
    }
    Object.assign(existingState, state);
    return this.stateRepo.save(existingState);
  }
}
