// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { I18nextProvider } from 'react-i18next';

import PopupModal from '../components/PopupModal/PopupModal.tsx';
import i18n from '../utils/i18n';

describe('PopupModal Component test suite', () => {
  const defaultProps = {
    open: true,
    onSubmit: vi.fn(),
    onClose: vi.fn(),
  };

  const renderComponent = () =>
    render(
      <I18nextProvider i18n={i18n}>
        <PopupModal
          onOpen={vi.fn()}
          onSubmit={defaultProps.onSubmit}
          onClose={defaultProps.onClose}
          open={defaultProps.open}
        >
          <div data-testid='modal-content'>Modal Content</div>
        </PopupModal>
        ,
      </I18nextProvider>,
    );

  beforeEach(() => {
    vi.clearAllMocks();
    renderComponent();
  });

  it('should render the component correctly', () => {
    expect(screen.getByTestId('modal-content')).toBeInTheDocument();
    expect(screen.getByTestId('popup-modal')).toBeInTheDocument();
  });

  it('should call onSubmit when the primary button is clicked', () => {
    const primaryButton = screen.getByText(new RegExp(i18n.t('confirm'), 'i'));

    fireEvent.click(primaryButton);
    expect(defaultProps.onSubmit).toHaveBeenCalled();
  });

  it('should call onClose when the modal is closed', () => {
    const closeButton = screen.getByText(new RegExp(i18n.t('cancel'), 'i'));

    fireEvent.click(closeButton);
    expect(defaultProps.onClose).toHaveBeenCalled();
  });
});
