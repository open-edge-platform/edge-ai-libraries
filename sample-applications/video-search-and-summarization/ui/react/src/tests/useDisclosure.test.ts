// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { renderHook, act } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';

import { useDisclosure } from '../hooks/useDisclosure.ts';

describe('useDisclosure hook test suite', () => {
  it('should return the initial state correctly', () => {
    const { result } = renderHook(() => useDisclosure());
    const [isOpen] = result.current;
    expect(isOpen).toBe(false);
  });

  it('should open the disclosure state and call onOpen callback', () => {
    const onOpen = vi.fn();
    const { result } = renderHook(() => useDisclosure(false, { onOpen }));

    act(() => {
      const [, { open }] = result.current;
      open();
    });

    const [isOpen] = result.current;
    expect(isOpen).toBe(true);
    expect(onOpen).toHaveBeenCalled();
  });

  it('should close the disclosure state and call onClose callback', () => {
    const onClose = vi.fn();
    const { result } = renderHook(() => useDisclosure(true, { onClose }));

    act(() => {
      const [, { close }] = result.current;
      close();
    });

    const [isOpen] = result.current;
    expect(isOpen).toBe(false);
    expect(onClose).toHaveBeenCalled();
  });

  it('should not call onOpen when already open', () => {
    const onOpen = vi.fn();
    const { result } = renderHook(() => useDisclosure(true, { onOpen }));

    act(() => {
      const [, { open }] = result.current;
      open();
    });

    const [isOpen] = result.current;
    expect(isOpen).toBe(true);
    expect(onOpen).not.toHaveBeenCalled();
  });

  it('should not call onClose when already closed', () => {
    const onClose = vi.fn();
    const { result } = renderHook(() => useDisclosure(false, { onClose }));

    act(() => {
      const [, { close }] = result.current;
      close();
    });

    const [isOpen] = result.current;
    expect(isOpen).toBe(false);
    expect(onClose).not.toHaveBeenCalled();
  });

  it('should toggle the disclosure state correctly', () => {
    const { result } = renderHook(() => useDisclosure());

    act(() => {
      const [, { toggle }] = result.current;
      toggle();
    });

    let [isOpen] = result.current;
    expect(isOpen).toBe(true);

    act(() => {
      const [, { toggle }] = result.current;
      toggle();
    });

    [isOpen] = result.current;
    expect(isOpen).toBe(false);
  });
});
