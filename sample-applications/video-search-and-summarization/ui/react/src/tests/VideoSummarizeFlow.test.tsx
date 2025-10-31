// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import React from 'react';
import { describe, it, expect, vi, beforeAll, beforeEach, afterEach, afterAll } from 'vitest';
import type { Mock } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const MOCK_APP_URL = 'http://localhost/api';

vi.stubEnv('VITE_BACKEND_SERVICE_ENDPOINT', MOCK_APP_URL);
vi.stubEnv('VITE_ASSETS_ENDPOINT', 'http://localhost/assets');
vi.stubEnv('VITE_SOCKET_APPEND', '/socket');
vi.stubEnv('VITE_FEATURE_SUMMARY', 'on');
vi.stubEnv('VITE_FEATURE_SEARCH', 'on');
vi.stubEnv('VITE_FEATURE_MUX', 'on');

vi.mock('axios', () => {
  const post = vi.fn();
  const get = vi.fn();
  const axiosMock = {
    post,
    get,
    isAxiosError: (error: unknown): error is { isAxiosError?: boolean } => Boolean(error && (error as { isAxiosError?: boolean }).isAxiosError),
  };
  return { default: axiosMock, __esModule: true };
});

import axios from 'axios';
const axiosMockInstance = axios as unknown as { get: Mock; post: Mock; isAxiosError: (error: unknown) => boolean };

const dispatchMock = vi.fn();
const addSummaryActionMock = vi.fn();
const selectSummaryActionMock = vi.fn();
const setSelectedSummaryMock = vi.fn();
const selectFrameSummaryMock = vi.fn();
const closePromptActionMock = vi.fn();
const setMuxActionMock = vi.fn();
const videosLoadMock = vi.fn();

const mockState = {
  search: {
    searchQueries: [],
    suggestedTags: ['tag-alpha', 'tag-beta'],
    unreads: [],
    selectedQuery: null,
    triggerLoad: false,
  },
};

const mockSystemConfig = {
  multiFrame: 16,
  framePrompt: 'frame prompt',
  summaryMapPrompt: 'map prompt',
  summaryReducePrompt: 'reduce prompt',
  summarySinglePrompt: 'single prompt',
  evamPipeline: 'pipeline-a',
  meta: {
    evamPipelines: [{ name: 'Pipeline A', value: 'pipeline-a' }],
    defaultAudioModel: 'audio-model-1',
    audioModels: [{ display_name: 'Audio Model', model_id: 'audio-model-1' }],
  },
};

const summaryUiState = {
  stateId: 'state-123',
  summary: 'Summary content',
  userInputs: {},
  chunkingStatus: 'complete',
  videoSummaryStatus: 'complete',
  inferenceConfig: {},
  chunks: [],
  frames: [],
  frameSummaries: [],
  frameSummaryStatus: {},
  systemConfig: mockSystemConfig,
  videoId: 'video-123',
  title: 'custom-summary',
};

vi.mock('styled-components', () => {
  const createStyled = (tag: React.ElementType) =>
    React.forwardRef<any, any>(({ children, ...rest }, ref) =>
      React.createElement(tag, { ref, ...rest }, children),
    );

  const styledFactory: any = new Proxy(() => {}, {
    apply: (_target, _thisArg, [tag]: [React.ElementType]) =>
      (..._styles: TemplateStringsArray[]) => createStyled(tag),
    get: (_target, prop: string | symbol) => {
      if (prop === 'default') {
        return styledFactory;
      }
      if (prop === '__esModule') {
        return true;
      }
      const tag = typeof prop === 'string' ? prop : String(prop);
      return (..._styles: TemplateStringsArray[]) => createStyled(tag as React.ElementType);
    },
  });

  return {
    default: styledFactory,
    css: () => '',
    ThemeProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  };
});

vi.mock('@carbon/icons-react', () => ({
  Information: () => <span data-testid="info-icon" />,
}));

vi.mock('@carbon/react', () => {
  const createSimple = (tag: string) =>
    React.forwardRef<HTMLElement, any>(({ children, ...props }, ref) =>
      React.createElement(tag, { ref, ...props }, children),
    );

  const Button = createSimple('button');
  const ModalBody = createSimple('div');
  const ModalFooter = createSimple('div');
  const ProgressBar = ({ label, helperText }: { label?: string; helperText?: string }) => (
    <div data-testid="progress">
      {label}
      {helperText}
    </div>
  );
  const TextInput = React.forwardRef<HTMLInputElement, any>(({ id, labelText, value = '', onChange, ...rest }, ref) => (
    <label htmlFor={id} style={{ display: 'block' }}>
      {typeof labelText === 'string' ? labelText : null}
      <input
        ref={ref}
        id={id}
        value={value}
        onChange={(event) => onChange?.(event)}
        {...rest}
      />
    </label>
  ));
  const NumberInput = ({ id, value = 0, onChange, label, labelText }: any) => (
    <label htmlFor={id} style={{ display: 'block' }}>
      {labelText ?? label}
      <input
        id={id}
        type="number"
        value={value}
        onChange={(event) => onChange?.(event, { value: event.target.value })}
      />
    </label>
  );
  const MultiSelect = ({ items = [], id, label }: any) => (
    <div id={id} aria-label={label} role="listbox">
      {items.map((item: string) => (
        <div key={item}>{item}</div>
      ))}
    </div>
  );
  const Checkbox = ({ id, labelText, defaultChecked = false, onChange }: any) => {
    const [checked, setChecked] = React.useState(defaultChecked);
    return (
      <label htmlFor={id} style={{ display: 'block' }}>
        <input
          id={id}
          type="checkbox"
          checked={checked}
          onChange={(event) => {
            setChecked(event.target.checked);
            onChange?.(event, { checked: event.target.checked });
          }}
        />
        {labelText}
      </label>
    );
  };
  const Select = React.forwardRef<HTMLSelectElement, any>(({ id, labelText, children, onChange, ...rest }, ref) => (
    <label htmlFor={id} style={{ display: 'block' }}>
      {labelText}
      <select ref={ref} id={id} onChange={(event) => onChange?.(event)} {...rest}>
        {children}
      </select>
    </label>
  ));
  const SelectItem = ({ value, text }: { value: string; text: string }) => <option value={value}>{text}</option>;
  const Accordion = ({ children }: { children: React.ReactNode }) => <div>{children}</div>;
  const AccordionItem = ({ title, children, onHeadingClick }: any) => (
    <div>
      <button type="button" onClick={() => onHeadingClick?.()}>
        {title}
      </button>
      <div>{children}</div>
    </div>
  );
  const Toggletip = ({ children }: { children: React.ReactNode }) => <span>{children}</span>;
  const ToggletipButton = ({ children, ...rest }: any) => <button {...rest}>{children}</button>;
  const ToggletipContent = ({ children }: { children: React.ReactNode }) => <span>{children}</span>;

  return {
    Button,
    ModalBody,
    ModalFooter,
    MultiSelect,
    NumberInput,
    ProgressBar,
    Select,
    SelectItem,
    TextInput,
    Checkbox,
    Accordion,
    AccordionItem,
    Toggletip,
    ToggletipButton,
    ToggletipContent,
  };
});

vi.mock('../redux/store', () => ({
  useAppDispatch: () => dispatchMock,
  useAppSelector: (selector: (state: typeof mockState) => unknown) => selector(mockState as never),
}));

vi.mock('../redux/search/searchSlice', () => ({
  SearchSelector: (state: typeof mockState) => ({
    queries: [],
    selectedQueryId: null,
    unreads: [],
    triggerLoad: false,
    selectedQuery: null,
    suggestedTags: state.search.suggestedTags,
    queriesInProgress: [],
    queriesWithErrors: [],
    isSelectedInProgress: false,
    isSelectedHasError: false,
    selectedResults: [],
  }),
}));

vi.mock('../redux/summary/summarySlice', () => ({
  SummaryActions: {
    addSummary: addSummaryActionMock,
    selectSummary: selectSummaryActionMock,
  },
}));

vi.mock('../redux/summary/videoChunkSlice', () => ({
  VideoChunkActions: { setSelectedSummary: setSelectedSummaryMock },
}));

vi.mock('../redux/summary/videoFrameSlice', () => ({
  VideoFramesAction: { selectSummary: selectFrameSummaryMock },
}));

vi.mock('../redux/ui/ui.slice', () => ({
  UIActions: {
    closePrompt: closePromptActionMock,
    setMux: setMuxActionMock,
  },
}));

vi.mock('../redux/ui/ui.model', () => ({
  MuxFeatures: { SUMMARY: 'SUMMARY' },
}));

vi.mock('../redux/video/videoSlice', () => ({
  videosLoad: videosLoadMock,
}));

vi.mock('../components/Prompts/PromptInput', () => ({
  PromptInput: ({ label }: { label: string }) => <div data-testid={`prompt-${label}`} />,
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, defaultOrOptions?: unknown) => {
      if (typeof defaultOrOptions === 'string') {
        return defaultOrOptions;
      }
      if (defaultOrOptions && typeof defaultOrOptions === 'object' && 'frames' in defaultOrOptions && 'interval' in defaultOrOptions) {
        const opts = defaultOrOptions as { frames: number; interval: number };
        return `${key}:${opts.frames}/${opts.interval}`;
      }
      return key;
    },
  }),
}));

const loadComponent = async () => (await import('../components/VideoActions/VideoSummarizeFlow')).default;

beforeAll(() => {
  global.URL.createObjectURL = vi.fn(() => 'blob:mock-url');
  global.URL.revokeObjectURL = vi.fn();
});

beforeEach(() => {
  vi.clearAllMocks();
  mockState.search.suggestedTags = ['tag-alpha', 'tag-beta'];
  addSummaryActionMock.mockImplementation((payload) => ({ type: 'summary/addSummary', payload }));
  selectSummaryActionMock.mockImplementation((id: string) => ({ type: 'summary/selectSummary', payload: id }));
  setSelectedSummaryMock.mockImplementation((id: string) => ({ type: 'videoChunk/setSelectedSummary', payload: id }));
  selectFrameSummaryMock.mockImplementation((id: string) => ({ type: 'videoFrame/selectSummary', payload: id }));
  closePromptActionMock.mockImplementation(() => ({ type: 'ui/closePrompt' }));
  setMuxActionMock.mockImplementation((feature: string) => ({ type: 'ui/setMux', payload: feature }));
  videosLoadMock.mockImplementation(() => ({ type: 'videos/load' }));
  axiosMockInstance.get.mockReset();
  axiosMockInstance.post.mockReset();
  axiosMockInstance.get.mockImplementation((url: string) => {
    if (url === `${MOCK_APP_URL}/app/config`) {
      return Promise.resolve({ data: mockSystemConfig });
    }
    if (url.startsWith(`${MOCK_APP_URL}/states/`)) {
      return Promise.resolve({ data: summaryUiState });
    }
    return Promise.resolve({ data: {} });
  });
  axiosMockInstance.post.mockResolvedValue({ data: {} });
});

afterEach(() => {
  cleanup();
});

afterAll(() => {
  vi.unstubAllEnvs();
});

describe('VideoSummarizeFlow integration', () => {
  it('allows a user to configure summary options and review them', async () => {
    const VideoSummarizeFlow = await loadComponent();
    const onClose = vi.fn();
    render(<VideoSummarizeFlow onClose={onClose} />);

    await waitFor(() => expect(axiosMockInstance.get).toHaveBeenCalledWith(`${MOCK_APP_URL}/app/config`));

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    expect(fileInput).toBeTruthy();

    const sampleFile = new File(['sample'], 'sample.mp4', { type: 'video/mp4' });
    fireEvent.change(fileInput, { target: { files: [sampleFile] } });

    const user = userEvent.setup();
    const nextButton = screen.getByRole('button', { name: /Next/i });
    expect(nextButton).toBeEnabled();

    await user.click(nextButton);
    await waitFor(() => expect(document.getElementById('summaryname')).toBeTruthy());

    const summaryInput = document.getElementById('summaryname') as HTMLInputElement;
    expect(summaryInput.value).toBe('sample');
    await user.clear(summaryInput);
    await user.type(summaryInput, 'custom-summary');

    const customTagsInput = document.getElementById('videoTags') as HTMLInputElement;
    await user.type(customTagsInput, 'tag-one,tag-two');

    await user.click(screen.getByRole('button', { name: /Next/i }));
    await waitFor(() => expect(screen.getByText(/summaryTitle/i)).toBeInTheDocument());

    expect(screen.getByText('custom-summary')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Back/i })).toBeInTheDocument();
  });

  it('calls onClose and revokes preview when cancel is clicked', async () => {
    const VideoSummarizeFlow = await loadComponent();
    const onClose = vi.fn();
    render(<VideoSummarizeFlow onClose={onClose} />);

    await waitFor(() => expect(axiosMockInstance.get).toHaveBeenCalled());

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    const sampleFile = new File(['cancel'], 'cancel.mp4', { type: 'video/mp4' });
    fireEvent.change(fileInput, { target: { files: [sampleFile] } });
    expect(global.URL.createObjectURL).toHaveBeenCalledTimes(1);

    const cancelButton = screen.getByRole('button', { name: /cancel/i });
    fireEvent.click(cancelButton);

    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
    expect(global.URL.revokeObjectURL).toHaveBeenCalledTimes(1);
    expect(closePromptActionMock).toHaveBeenCalledTimes(1);
    expect(dispatchMock).toHaveBeenCalledWith(expect.objectContaining({ type: 'ui/closePrompt' }));
  });

  it('uploads a video and dispatches summary actions when creating a summary', async () => {
    const VideoSummarizeFlow = await loadComponent();
    const onClose = vi.fn();

    axiosMockInstance.post
      .mockImplementationOnce(() => Promise.resolve({ data: { videoId: 'video-123' } }))
      .mockImplementationOnce(() => Promise.resolve({ data: { stateId: 'state-123' } }));

    render(<VideoSummarizeFlow onClose={onClose} />);

    await waitFor(() => expect(axiosMockInstance.get).toHaveBeenCalledWith(`${MOCK_APP_URL}/app/config`));

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    const sampleFile = new File(['workflow'], 'workflow.mp4', { type: 'video/mp4' });
    fireEvent.change(fileInput, { target: { files: [sampleFile] } });

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /Next/i }));
    await waitFor(() => expect(document.getElementById('summaryname')).toBeTruthy());
    await user.click(screen.getByRole('button', { name: /Next/i }));

    await waitFor(() => expect(screen.getByText(/summaryTitle/i)).toBeInTheDocument());

    const createButton = screen.getByRole('button', { name: /CreateSummary/i });
    await user.click(createButton);

    await waitFor(() => expect(axiosMockInstance.post).toHaveBeenCalledTimes(2));
    expect(axiosMockInstance.post.mock.calls[0][0]).toBe(`${MOCK_APP_URL}/videos`);
    expect(axiosMockInstance.post.mock.calls[1][0]).toBe(`${MOCK_APP_URL}/summary`);

    await waitFor(() => expect(addSummaryActionMock).toHaveBeenCalledWith(expect.objectContaining({ stateId: 'state-123' })));
    expect(selectSummaryActionMock).toHaveBeenCalledWith('state-123');
    expect(setSelectedSummaryMock).toHaveBeenCalledWith('state-123');
    expect(selectFrameSummaryMock).toHaveBeenCalledWith('state-123');
    expect(videosLoadMock).toHaveBeenCalledTimes(1);
    expect(setMuxActionMock).toHaveBeenCalledWith('SUMMARY');
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
  });

  it('shows an error message when the upload response is missing a video identifier', async () => {
    const VideoSummarizeFlow = await loadComponent();
    const onClose = vi.fn();
    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    try {
      axiosMockInstance.post.mockImplementationOnce(() => Promise.resolve({ data: {} }));

      render(<VideoSummarizeFlow onClose={onClose} />);

      await waitFor(() => expect(axiosMockInstance.get).toHaveBeenCalledWith(`${MOCK_APP_URL}/app/config`));

      const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
      const sampleFile = new File(['missing'], 'missing-id.mp4', { type: 'video/mp4' });
      fireEvent.change(fileInput, { target: { files: [sampleFile] } });

      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: /Next/i }));
      await waitFor(() => expect(document.getElementById('summaryname')).toBeTruthy());
      await user.click(screen.getByRole('button', { name: /Next/i }));

      const createButton = screen.getByRole('button', { name: /CreateSummary/i });
      await user.click(createButton);

      expect(axiosMockInstance.post).toHaveBeenCalledTimes(1);
      expect(addSummaryActionMock).not.toHaveBeenCalled();
      expect(onClose).not.toHaveBeenCalled();
      await waitFor(() =>
        expect(consoleErrorSpy).toHaveBeenCalledWith(
          'Unable to resolve video identifier from upload response:',
          expect.anything(),
        ),
      );
    } finally {
      consoleErrorSpy.mockRestore();
    }
  });
});
