// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Body, Controller, Post, Res } from '@nestjs/common';
import { LlmService } from '../services/llm.service';
import { TemplateService } from '../services/template.service';
import { Subject } from 'rxjs';
import { Response } from 'express';
import { ApiExcludeController } from '@nestjs/swagger';

@Controller('llm')
@ApiExcludeController()
export class LlmController {
  constructor(
    private $llm: LlmService,
    private $template: TemplateService,
  ) {}

  @Post('')
  async textInference(@Body('texts') texts: string[], @Res() res: Response) {
    try {
      console.log('Received texts:', texts);
      const streamer = new Subject<string>();

      res.setHeader('Content-Type', 'application/json');
      res.setHeader('Transfer-Encoding', 'chunked');
      console.log('Setting up streamer subscription');
      let response: string = '';
      streamer.subscribe({
        next: (data) => {
          console.log(data);
          response = response + data;
          res.write(data);
        },
        error: (err: Error) => {
          console.error('Streaming error:', err);
          res.status(500).send(err.message);
        },
        complete: () => {
          console.log(response);
          res.end();
        },
      });
      console.log('Streamer subscription set up');

      await this.$llm.summarizeMapReduce(
        texts,
        this.$template.getCaptionsSummarizeTemplate(),
        this.$template.getCaptionsReduceTemplate(),
        this.$template.getCaptionsReduceSingleTextTemplate(),
        streamer,
      );
    } catch (error) {
      console.error('Error in textInference:', error);
      res.status(500).send(error);
    }
  }
}
