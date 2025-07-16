import type {
  Dispatch,
  SetStateAction,
  ReactNode,
  SyntheticEvent,
} from 'react';

interface PopupModalPropsBase {
  open: boolean;
  headingMsg?: string;
  labelMsg?: string;
  primaryButtonText?: string;
  secondaryButtonText?: string;
  onOpen: Dispatch<SetStateAction<boolean>>;
  onClose?: () => void;
  children?: ReactNode;
  size?: 'sm' | 'md' | 'lg';
  preventCloseOnClickOutside?: boolean;
  primaryButtonDisabled?: boolean;
}

interface PassiveModalProps extends PopupModalPropsBase {
  passiveModal: true;
  onSubmit: (event: SyntheticEvent) => void;
}

interface NonPassiveModalProps extends PopupModalPropsBase {
  passiveModal?: false;
  onSubmit?: (event: SyntheticEvent) => void;
}

export type PopupModalProps = PassiveModalProps | NonPassiveModalProps;
