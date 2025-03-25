// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import { I18nextProvider } from 'react-i18next';
import { vi, it, expect, describe } from 'vitest';

import i18n from '../utils/i18n';
import PopupModal from '../components/PopupModal/PopupModal.tsx';
import { PopupModalProps } from '../components/PopupModal/PopupModalProps.ts';

const renderComponent = (props = {}) => {
  const defaultProps: PopupModalProps = {
    open: true,
    passiveModal: false,
    headingMsg: 'Test Heading',
    primaryButtonText: 'Confirm',
    secondaryButtonText: 'Cancel',
    size: 'sm',
    children: <div>Test Content</div>,
    onSubmit: vi.fn(),
    onClose: vi.fn(),
    onOpen: vi.fn(),
    preventCloseOnClickOutside: false,
    primaryButtonDisabled: false,
  };

  return render(
    <I18nextProvider i18n={i18n}>
      <PopupModal {...defaultProps} {...props} />
    </I18nextProvider>,
  );
};

describe('PopupModal Component test suite', () => {
  it('should render the modal with heading and content', () => {
    renderComponent();

    expect(screen.getByText('Test Heading')).toBeInTheDocument();
    expect(screen.getByText('Test Content')).toBeInTheDocument();
  });

  it('should call onClose when the close button is clicked', () => {
    const onClose = vi.fn();
    renderComponent({ onClose });

    fireEvent.click(screen.getByText('Cancel'));

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('should call onSubmit when the confirm button is clicked', () => {
    const onSubmit = vi.fn();
    renderComponent({ onSubmit });

    fireEvent.click(screen.getByText('Confirm'));

    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it('should not call onSubmit when the confirm button is disabled', () => {
    const onSubmit = vi.fn();
    renderComponent({ onSubmit, primaryButtonDisabled: true });

    fireEvent.click(screen.getByText('Confirm'));

    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('should render with default translations if headingMsg and primaryButtonText are not provided', () => {
    renderComponent();

    expect(screen.getByText('Test Heading')).toBeInTheDocument();
    expect(screen.getByText('Confirm')).toBeInTheDocument();
  });

  it('should render with custom size', () => {
    renderComponent({ size: 'lg' });

    expect(screen.getByRole('dialog')).toHaveClass('cds--modal-container--lg');
  });

  it('should render with passiveModal', () => {
    renderComponent({ passiveModal: true });

    expect(screen.getByRole('dialog')).toHaveClass('cds--modal-container');
  });

  it('should prevent close on click outside when preventCloseOnClickOutside is true', () => {
    const onClose = vi.fn();
    renderComponent({ onClose, preventCloseOnClickOutside: true });

    fireEvent.mouseDown(document.body);

    expect(onClose).not.toHaveBeenCalled();
  });
});
