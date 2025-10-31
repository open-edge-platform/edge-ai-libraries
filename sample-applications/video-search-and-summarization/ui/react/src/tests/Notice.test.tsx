// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { I18nextProvider } from 'react-i18next';
import '../index.scss';

import Notice from '../components/Notice/Notice.tsx';
import i18n from '../utils/i18n';
import { NoticeKind } from '../components/Notice/NoticeProps.ts';

describe('Notice Component test suite', () => {
  const mockSetIsNoticeVisible = vi.fn();

  const renderComponent = (props = {}) =>
    render(
      <I18nextProvider i18n={i18n}>
        <Notice
          message='Test Message'
          kind={NoticeKind.INFO}
          isNoticeVisible={true}
          setIsNoticeVisible={mockSetIsNoticeVisible}
          {...props}
        />
      </I18nextProvider>,
    );

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should render the component correctly with a message', () => {
    renderComponent();

    expect(screen.getByTestId('notice-container')).toBeInTheDocument();
    expect(screen.getByText('Test Message')).toBeInTheDocument();
  });

  it('should not render the component when message is not provided', () => {
    renderComponent({ message: null });

    expect(screen.queryByTestId('notice-container')).not.toBeInTheDocument();
  });

  it('should not render the component when isNoticeVisible is false', () => {
    renderComponent({ isNoticeVisible: false });

    expect(screen.queryByTestId('notice-container')).not.toBeInTheDocument();
  });

  it('should call setIsNoticeVisible and close the notice when the close button is clicked', () => {
    renderComponent();

    const closeButton = screen.getByTestId('close-button');
    fireEvent.click(closeButton);
    expect(mockSetIsNoticeVisible).toHaveBeenCalledWith(false);
  });
});
