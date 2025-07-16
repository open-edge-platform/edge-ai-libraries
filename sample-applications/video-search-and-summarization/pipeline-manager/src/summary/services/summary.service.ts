import { Injectable } from '@nestjs/common';
import { StateService } from 'src/state-manager/services/state.service';

@Injectable()
export class SummaryService {
  constructor(private $state: StateService) {}

  async removeSummary(stateId: string): Promise<boolean> {
    await this.$state.remove(stateId);
    return true; // Return true if removal was successful
  }
}
