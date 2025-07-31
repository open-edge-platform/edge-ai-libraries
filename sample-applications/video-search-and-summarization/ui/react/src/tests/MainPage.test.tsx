// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { I18nextProvider } from 'react-i18next';

import MainPage from '../components/MainPage/MainPage.tsx';
import i18n from '../utils/i18n';

vi.mock('../components/Conversation/ConversationSideBar.tsx', () => ({
  default: () => (
    <div data-testid='conversation-sidebar'>ConversationSideBar</div>
  ),
}));

vi.mock('../components/Conversation/Conversation.tsx', () => ({
  default: () => <div data-testid='conversation'>Conversation</div>,
}));

interface Props {
  message: string;
  isNoticeVisible: boolean;
  setIsNoticeVisible: (visible: boolean) => void;
}

vi.mock('../components/Notice/Notice.tsx', () => {
  return {
    default: ({ message, isNoticeVisible, setIsNoticeVisible }: Props) =>
      isNoticeVisible ? (
        <div data-testid='notice'>
          {message}
          <button
            data-testid='close-notice'
            onClick={() => setIsNoticeVisible(false)}
          >
            Close
          </button>
        </div>
      ) : null,
  };
});

vi.mock('../components/Navbar/Navbar.tsx', () => ({
  default: () => <div data-testid='navbar'>Navbar</div>,
}));

describe('MainPage Component test suite', () => {
  const renderComponent = () =>
    render(
      <I18nextProvider i18n={i18n}>
        <MainPage />
      </I18nextProvider>,
    );

  beforeEach(() => {
    vi.clearAllMocks();
    renderComponent();
  });

  it('should render the component correctly', () => {
    expect(screen.getByTestId('navbar')).toBeInTheDocument();
    expect(screen.getByTestId('conversation-sidebar')).toBeInTheDocument();
    expect(screen.getByTestId('conversation')).toBeInTheDocument();
  });

  it('should render the Notice component when isNoticeVisible is true', () => {
    const toggleButton = screen.getByTestId('toggle-notice');
    fireEvent.click(toggleButton);
    expect(screen.getByTestId('notice')).toBeInTheDocument();
  });

  it('should hide the Notice component when the close button is clicked', () => {
    const toggleButton = screen.getByTestId('toggle-notice');
    fireEvent.click(toggleButton);
    const noticeButton = screen.getByTestId('close-notice');
    fireEvent.click(noticeButton);
    expect(screen.queryByTestId('notice')).not.toBeInTheDocument();
  });
});
