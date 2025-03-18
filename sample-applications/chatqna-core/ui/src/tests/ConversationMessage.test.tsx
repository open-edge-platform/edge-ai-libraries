// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import '@testing-library/jest-dom/vitest';

import ConversationMessage from '../components/Conversation/ConversationMessage.tsx';
import i18n from '../utils/i18n';

describe('ConversationMessage Component test suite', () => {
  const message = 'Hello, this is a test message.';
  const date = Date.now();

  it('should render the component correctly with a human message', () => {
    render(<ConversationMessage human={true} message={message} date={date} />);
    expect(screen.getByText(message)).toBeInTheDocument();
    expect(
      screen.getByText(new RegExp(i18n.t('question'), 'i')),
    ).toBeInTheDocument();
  });

  it('should render the component correctly with a non-human message', () => {
    render(<ConversationMessage human={false} message={message} date={date} />);
    expect(screen.getByText(message)).toBeInTheDocument();
    expect(
      screen.getByText(new RegExp(i18n.t('response'), 'i')),
    ).toBeInTheDocument();
  });

  it('should render the component correctly with isGenerating set to true', () => {
    render(
      <ConversationMessage
        human={true}
        message={message}
        date={date}
        isGenerating={true}
      />,
    );
    expect(screen.getByText(message)).toBeInTheDocument();
    expect(
      screen.getByText(new RegExp(i18n.t('question'), 'i')),
    ).toBeInTheDocument();
    expect(screen.getByTestId('circle')).toBeInTheDocument();
  });
});
