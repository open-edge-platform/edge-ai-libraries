// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Tag } from '@carbon/react';
import { FC } from 'react';
import { useTranslation } from 'react-i18next';
import { LiveStreamState } from '../../redux/streams/streams';

/**
 * Carbon tag colour and label for each lifecycle state.
 *
 * Every one of the seven backend states is mapped. An unmapped state would
 * render a blank badge, which looks like a UI fault rather than a camera one.
 */
const STATE_PRESENTATION: Record<
  LiveStreamState,
  { type: string; labelKey: string }
> = {
  [LiveStreamState.RUNNING]: { type: 'green', labelKey: 'streamStateRunning' },
  [LiveStreamState.STARTING]: { type: 'blue', labelKey: 'streamStateStarting' },
  [LiveStreamState.PENDING]: { type: 'blue', labelKey: 'streamStatePending' },
  [LiveStreamState.PAUSED]: { type: 'gray', labelKey: 'streamStatePaused' },
  [LiveStreamState.RECONNECTING]: {
    type: 'warm-gray',
    labelKey: 'streamStateReconnecting',
  },
  [LiveStreamState.ERROR]: { type: 'red', labelKey: 'streamStateError' },
  [LiveStreamState.STOPPED]: {
    type: 'cool-gray',
    labelKey: 'streamStateStopped',
  },
};

export interface StreamStateTagProps {
  state: LiveStreamState;
}

const StreamStateTag: FC<StreamStateTagProps> = ({ state }) => {
  const { t } = useTranslation();
  const presentation = STATE_PRESENTATION[state];

  // Defensive: a backend that adds an eighth state should still render
  // something readable rather than an empty tag.
  if (!presentation) {
    return (
      <Tag type='outline' size='sm'>
        {state}
      </Tag>
    );
  }

  return (
    <Tag type={presentation.type as never} size='sm' data-testid={`state-${state}`}>
      {t(presentation.labelKey)}
    </Tag>
  );
};

export default StreamStateTag;
