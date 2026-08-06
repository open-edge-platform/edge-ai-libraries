// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';

const notifyMock = vi.fn();
const dispatchMock = vi.fn();
const videosLoadMock = vi.fn();
const loadTagsMock = vi.fn();
const axiosPostMock = vi.fn();
const axiosGetMock = vi.fn();
let suggestedTagsMock = ['tag1', 'tag2'];

let VideoEmbeddingFlow: React.ComponentType<{ onClose?: () => void }>;

const notificationSeverity = {
  SUCCESS: 'success',
  ERROR: 'error',
} as const;

vi.mock('@carbon/react', () => ({
  Button: ({ children, disabled, onClick, ...rest }: any) => (
    <button disabled={disabled} onClick={onClick} {...rest}>
      {children}
    </button>
  ),
  ModalBody: ({ children, ...rest }: any) => (
    <div data-testid="modal-body" {...rest}>
      {children}
    </div>
  ),
  ModalFooter: ({ children, ...rest }: any) => (
    <div data-testid="modal-footer" {...rest}>
      {children}
    </div>
  ),
  MultiSelect: ({
    items = [],
    onChange,
    itemToString: _itemToString,
    initialSelectedItems: _initial,
    sortItems: _sort,
    labelText: _label,
    ...rest
  }: any) => (
    <select
      data-testid="multi-select"
      onChange={(event) => {
        const value = event.target.value;
        onChange?.({ selectedItems: value ? [value] : [] });
      }}
      {...rest}
    >
      <option value="" />
      {items.map((item: string) => (
        <option key={item} value={item}>
          {item}
        </option>
      ))}
    </select>
  ),
  ProgressBar: ({ label, helperText, value }: any) => (
    <div data-testid="progress-bar">
      <span>{label}</span>
      <span>{helperText}</span>
      <span>{value}</span>
    </div>
  ),
  TextInput: ({ value, onChange, id, ...rest }: any) => (
    <input id={id} value={value} onChange={onChange} {...rest} />
  ),
  Toggletip: ({ children }: any) => <div>{children}</div>,
  ToggletipButton: ({ children, ...rest }: any) => <button {...rest}>{children}</button>,
  ToggletipContent: ({ children }: any) => <div>{children}</div>,
}));

vi.mock('@carbon/icons-react', () => ({
  Information: 'span',
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('../components/Notification/notify', () => ({
  notify: (...args: any[]) => notifyMock(...args),
  NotificationSeverity: notificationSeverity,
}));

vi.mock('../redux/video/videoSlice', () => ({
  videosLoad: (...args: any[]) => videosLoadMock(...args),
  videosSelector: (state: any) => state.video,
}));

vi.mock('../redux/search/searchSlice', () => ({
  SearchSelector: (state: any) => state.search,
  LoadTags: (...args: unknown[]) => loadTagsMock(...args),
}));

vi.mock('../redux/store', () => ({
  useAppDispatch: () => dispatchMock,
  useAppSelector: (selector: (state: any) => unknown) =>
    selector({
      search: {
        suggestedTags: suggestedTagsMock,
      },
      video: {
        videos: [],
      },
    }),
}));

vi.mock('../config', () => ({
  APP_URL: 'http://localhost:3000',
  ASSETS_ENDPOINT: 'http://localhost/assets',
}));

vi.mock('axios', () => ({
  default: {
    post: (...args: any[]) => axiosPostMock(...args),
    get: (...args: any[]) => axiosGetMock(...args),
    isAxiosError: (error: any) => Boolean(error?.isAxiosError),
  },
  post: (...args: any[]) => axiosPostMock(...args),
  get: (...args: any[]) => axiosGetMock(...args),
  isAxiosError: (error: any) => Boolean(error?.isAxiosError),
}));

describe('VideoEmbeddingFlow', () => {
  const createObjectURLSpy = vi.fn(() => 'blob:http://localhost/mock');
  const revokeObjectURLSpy = vi.fn();
  const streamableMp4Buffer = new TextEncoder().encode('ftypmoovmdatfree').buffer;

  const renderFlow = (props: Record<string, unknown> = {}) => {
    return render(<VideoEmbeddingFlow onClose={vi.fn()} {...props} />);
  };

  beforeEach(async () => {
    vi.resetModules();
    suggestedTagsMock = ['tag1', 'tag2'];
    notifyMock.mockClear();
    dispatchMock.mockClear();
    videosLoadMock.mockReset();
    loadTagsMock.mockReset();
    axiosPostMock.mockReset();
    axiosGetMock.mockReset();
    createObjectURLSpy.mockClear();
    revokeObjectURLSpy.mockClear();
    videosLoadMock.mockReturnValue({ type: 'videos/load' });
    loadTagsMock.mockReturnValue({ type: 'search/loadTags' });
    global.URL.createObjectURL = createObjectURLSpy as unknown as typeof URL.createObjectURL;
    global.URL.revokeObjectURL = revokeObjectURLSpy as unknown as typeof URL.revokeObjectURL;
    File.prototype.arrayBuffer = vi.fn(async function () {
      return streamableMp4Buffer;
    });
    VideoEmbeddingFlow = (await import('../components/VideoActions/VideoEmbeddingFlow')).default;
  });

  it('renders step 0 and disables Next without a file', () => {
    renderFlow();
    expect(screen.getAllByText('SelectVideo').length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled();
  });

  it('advances to review step after selecting a file and entering tags', async () => {
    renderFlow();
    const file = new File(['dummy'], 'sample.mp4', { type: 'video/mp4' });
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement | null;
    expect(fileInput).toBeTruthy();
    fireEvent.change(fileInput as HTMLInputElement, { target: { files: [file] } });

    await waitFor(() => expect(screen.getByRole('button', { name: 'Next' })).not.toBeDisabled());

    await userEvent.click(screen.getByRole('button', { name: 'Next' }));
    const tagsInput = document.getElementById('videoTags') as HTMLInputElement;
    expect(tagsInput).toBeInTheDocument();

    fireEvent.change(tagsInput, { target: { value: 'customA, customB' } });
    const multiSelect = screen.getByTestId('multi-select');
    fireEvent.change(multiSelect, { target: { value: suggestedTagsMock[0] } });

    await userEvent.click(screen.getByRole('button', { name: 'Next' }));

    await waitFor(() => {
      expect(screen.getAllByText(/videoNameLabel/).length).toBeGreaterThan(0);
    });
    expect(screen.getByText(/sample/i)).toBeInTheDocument();
    expect(createObjectURLSpy).toHaveBeenCalledWith(file);
  });

  it('calls onClose from cancel button and resets state', async () => {
    const onClose = vi.fn();
    renderFlow({ onClose });
    const cancelButton = screen.getByRole('button', { name: 'cancel' });
    await userEvent.click(cancelButton);
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(revokeObjectURLSpy).not.toHaveBeenCalled();
  });

  it('uploads video and triggers embedding on success', async () => {
    const onClose = vi.fn();
    axiosPostMock
      .mockImplementationOnce((_url: string, formData: FormData, config?: { onUploadProgress?: (evt: any) => void }) => {
        config?.onUploadProgress?.({ progress: 0.6 });
        expect(formData.get('video')).toBeInstanceOf(File);
        expect(formData.get('tags')).toBe('customTag,tag1');
        return Promise.resolve({ data: { videoId: 'vid-123' } });
      })
      .mockResolvedValueOnce({ data: { status: 'success', message: 'done' } });

    renderFlow({ onClose });

    const file = new File(['dummy'], 'upload.mp4', { type: 'video/mp4' });
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(fileInput, { target: { files: [file] } });

    await userEvent.click(screen.getByRole('button', { name: 'Next' }));
    const tagsInput = document.getElementById('videoTags') as HTMLInputElement;
    fireEvent.change(tagsInput, { target: { value: 'customTag' } });
    fireEvent.change(screen.getByTestId('multi-select'), { target: { value: 'tag1' } });

    await userEvent.click(screen.getByRole('button', { name: 'Next' }));
    const createButton = screen.getByRole('button', { name: 'CreateVideoEmbedding' });
    await userEvent.click(createButton);

    await waitFor(() => {
      expect(axiosPostMock).toHaveBeenCalledTimes(2);
    });

    expect(videosLoadMock).toHaveBeenCalled();
    expect(dispatchMock).toHaveBeenCalledWith({ type: 'videos/load' });
    expect(notifyMock).toHaveBeenCalledWith('CreatingEmbeddings success', notificationSeverity.SUCCESS);
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(revokeObjectURLSpy).toHaveBeenCalled();
  });

  it('uploads multiple selected files then embeds them via a single batch job', async () => {
    const onClose = vi.fn();
    const uploadedNames: string[] = [];
    let batchSubmitBody: unknown = null;
    axiosPostMock.mockImplementation((url: string, payload: unknown) => {
      if (payload instanceof FormData) {
        const uploaded = payload.get('video');
        if (uploaded instanceof File) {
          uploadedNames.push(uploaded.name);
        }
        return Promise.resolve({ data: { videoId: `vid-${uploadedNames.length}` } });
      }
      // Batch submit call (JSON body to search-embeddings-batch).
      if (url.includes('search-embeddings-batch')) {
        batchSubmitBody = payload;
        return Promise.resolve({ data: { job_id: 'job-1', accepted: 2 } });
      }
      return Promise.resolve({ data: { status: 'success', message: 'done' } });
    });
    axiosGetMock.mockResolvedValue({
      data: {
        job_id: 'job-1',
        state: 'completed',
        total: 2,
        completed: 2,
        failed: 0,
        items: [],
      },
    });

    renderFlow({ onClose });

    const fileA = new File(['a'], 'first.mp4', { type: 'video/mp4' });
    const fileB = new File(['b'], 'second.mp4', { type: 'video/mp4' });
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(fileInput, { target: { files: [fileA, fileB] } });

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Next' })).not.toBeDisabled(),
    );

    await userEvent.click(screen.getByRole('button', { name: 'Next' }));
    await userEvent.click(screen.getByRole('button', { name: 'Next' }));
    await userEvent.click(screen.getByRole('button', { name: 'CreateVideoEmbedding' }));

    // Two files => two uploads + ONE batch submit (true batch, not per-file).
    await waitFor(() => {
      expect(axiosPostMock).toHaveBeenCalledTimes(3);
    });
    await waitFor(() => {
      expect(axiosGetMock).toHaveBeenCalled();
    });

    expect(uploadedNames).toEqual(['first.mp4', 'second.mp4']);
    expect(batchSubmitBody).toMatchObject({ videoIds: ['vid-1', 'vid-2'] });
    expect(notifyMock).toHaveBeenCalledWith(
      'CreatingEmbeddings success',
      notificationSeverity.SUCCESS,
    );
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('notifies error when upload response lacks videoId', async () => {
    axiosPostMock.mockResolvedValueOnce({ data: {} });

    renderFlow();

    const file = new File(['dummy'], 'missing-id.mp4', { type: 'video/mp4' });
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(fileInput, { target: { files: [file] } });
    await userEvent.click(screen.getByRole('button', { name: 'Next' }));
    await userEvent.click(screen.getByRole('button', { name: 'Next' }));
    await userEvent.click(screen.getByRole('button', { name: 'CreateVideoEmbedding' }));

    await waitFor(() => {
      expect(notifyMock).toHaveBeenCalledWith('serverError', notificationSeverity.ERROR);
    });

    expect(dispatchMock).toHaveBeenCalledWith({ type: 'videos/load' });
    expect(axiosPostMock).toHaveBeenCalledTimes(1);
  });

  it('surfaces axios error messages to notifications', async () => {
    axiosPostMock.mockRejectedValueOnce({
      isAxiosError: true,
      response: { data: { message: 'Upload unreachable' } },
    });

    renderFlow();

    const file = new File(['dummy'], 'error.mp4', { type: 'video/mp4' });
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(fileInput, { target: { files: [file] } });
    await userEvent.click(screen.getByRole('button', { name: 'Next' }));
    await userEvent.click(screen.getByRole('button', { name: 'Next' }));
    await userEvent.click(screen.getByRole('button', { name: 'CreateVideoEmbedding' }));

    await waitFor(() => {
      expect(notifyMock).toHaveBeenCalledWith(
        'Video upload failed: Upload unreachable',
        notificationSeverity.ERROR
      );
    });

    // Upload failed, so embedding creation must not have been attempted and no
    // success notification should be shown. (The list refresh via videosLoad on
    // mount is expected and intentional.)
    expect(axiosPostMock).toHaveBeenCalledTimes(1);
    expect(loadTagsMock).not.toHaveBeenCalled();
    expect(notifyMock).not.toHaveBeenCalledWith(
      'CreatingEmbeddings success',
      notificationSeverity.SUCCESS,
    );
  });

  it('revokes object URLs on unmount', async () => {
    const { unmount } = renderFlow();
    const file = new File(['dummy'], 'cleanup.mp4', { type: 'video/mp4' });
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(fileInput, { target: { files: [file] } });

    await waitFor(() => expect(createObjectURLSpy).toHaveBeenCalled());
    unmount();
    expect(revokeObjectURLSpy).toHaveBeenCalledWith('blob:http://localhost/mock');
  });
});
