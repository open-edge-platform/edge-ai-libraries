// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Controller, Get, Param } from '@nestjs/common';
import { StateService } from './services/state.service';
import { UiService } from './services/ui.service';
import { ApiExcludeController } from '@nestjs/swagger';

@Controller('states')
@ApiExcludeController()
export class StatesController {
  constructor(
    private $ui: UiService,
    private $state: StateService,
  ) {}

  @Get('raw/:stateId')
  getStateRaw(@Param() params: any) {
    const state = this.$state.fetch(params.stateId);
    return state;
  }

  @Get(':stateId')
  getState(@Param() params: any) {
    console.log('STATE', params.stateId);
    const state = this.$ui.getUiState(params.stateId);

    // console.log('UI STATE', state);

    return state;
  }
}
