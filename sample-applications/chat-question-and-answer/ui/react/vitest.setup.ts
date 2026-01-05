import { afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';
import '@testing-library/jest-dom';

// Clean up the DOM after each test
afterEach(() => {
  cleanup();
});
