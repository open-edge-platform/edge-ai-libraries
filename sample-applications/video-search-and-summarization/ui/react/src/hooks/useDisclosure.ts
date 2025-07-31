// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { useCallback, useState } from 'react';

interface DisclosureCallbacks {
  onOpen?: () => void;
  onClose?: () => void;
}

export const useDisclosure = (
  initialState: boolean = false,
  callbacks?: DisclosureCallbacks,
) => {
  const { onOpen, onClose } = callbacks || {};
  const [isOpen, setIsOpen] = useState(initialState);

  const open = useCallback(() => {
    setIsOpen((isOpened) => {
      if (!isOpened) {
        onOpen?.();
        return true;
      }
      return isOpened;
    });
  }, [onOpen]);

  const close = useCallback(() => {
    setIsOpen((prevIsOpen) => {
      if (prevIsOpen) {
        onClose?.();
        return false;
      }
      return prevIsOpen;
    });
  }, [onClose]);

  const toggle = useCallback(() => {
    if (isOpen) close();
    else open();
  }, [close, open, isOpen]);

  return [isOpen, { open, close, toggle }] as const;
};
