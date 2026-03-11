// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Button, Checkbox, Modal, ModalBody, ModalFooter } from '@carbon/react';
import axios from 'axios';
import { FC, useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import styled from 'styled-components';
import { NVR_API_BASE } from '../../config';
import { NotificationSeverity, notify } from '../Notification/notify';

type CameraResponse = Record<string, unknown> | string[];

const StyledModal = styled(Modal)`
  z-index: 8000 !important;

  & .cds--modal-container {
    z-index: 8000 !important;
  }
`;

const Description = styled.p`
  margin-bottom: 1rem;
`;

const CameraList = styled.div`
  max-height: 18rem;
  overflow-y: auto;
  border: 1px solid #e0e0e0;
  padding: 0.75rem;
  margin-bottom: 1rem;
`;

const CameraRow = styled.div`
  margin-bottom: 0.5rem;
`;

const ButtonRow = styled.div`
  display: flex;
  justify-content: flex-end;
  margin-bottom: 1rem;
`;

export interface CameraConfigModalProps {
  open: boolean;
  onClose: () => void;
}

const normalizeCameraList = (data: CameraResponse): string[] => {
  if (Array.isArray(data)) {
    return data.map((camera) => String(camera));
  }

  if (data && typeof data === 'object') {
    const record = data as Record<string, unknown>;

    if (record.cameras && typeof record.cameras === 'object') {
      if (Array.isArray(record.cameras)) {
        return record.cameras.map((camera) => String(camera));
      }
      return Object.keys(record.cameras as Record<string, unknown>);
    }

    return Object.keys(record);
  }

  return [];
};

const normalizeMapping = (data: unknown): Record<string, boolean> => {
  if (!data || typeof data !== 'object') {
    return {};
  }

  const record = data as Record<string, unknown>;
  const mappingSource = (record.mapping ?? record) as Record<string, unknown>;
  const mapping: Record<string, boolean> = {};

  Object.entries(mappingSource).forEach(([camera, enabled]) => {
    mapping[String(camera).trim()] = enabled === true;
  });

  return mapping;
};

const CameraConfigModal: FC<CameraConfigModalProps> = ({ open, onClose }) => {
  const { t } = useTranslation();
  const [cameras, setCameras] = useState<string[]>([]);
  const [selectedCameras, setSelectedCameras] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const camerasApi = useMemo(() => `${NVR_API_BASE}/cameras`, []);
  const mappingApi = useMemo(() => `${NVR_API_BASE}/watchers/mapping`, []);
  const watchersEnableApi = useMemo(() => `${NVR_API_BASE}/watchers/enable`, []);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [cameraRes, mappingRes] = await Promise.all([
        axios.get<CameraResponse>(camerasApi),
        axios.get(mappingApi),
      ]);

      const cameraList = normalizeCameraList(cameraRes.data);
      const mapping = normalizeMapping(mappingRes.data);

      setCameras(cameraList);
      setSelectedCameras(cameraList.filter((camera) => mapping[camera.trim()] === true));
    } catch {
      notify(t('cameraConfigSaveFailed'), NotificationSeverity.ERROR);
      setCameras([]);
      setSelectedCameras([]);
    } finally {
      setLoading(false);
    }
  }, [camerasApi, mappingApi, t]);

  useEffect(() => {
    if (open) {
      loadData();
    }
  }, [open, loadData]);

  const handleToggleCamera = (camera: string, checked: boolean) => {
    if (checked) {
      setSelectedCameras((prev) => (prev.includes(camera) ? prev : [...prev, camera]));
      return;
    }

    setSelectedCameras((prev) => prev.filter((item) => item !== camera));
  };

  const handleSubmit = async () => {
    setSubmitting(true);
    try {
      const payload = {
        cameras: cameras.map((camera) => ({ [camera]: selectedCameras.includes(camera) })),
      };

      await axios.post(watchersEnableApi, payload);
      notify(t('cameraConfigSaved'), NotificationSeverity.SUCCESS);
      onClose();
    } catch (error: unknown) {
      if (axios.isAxiosError(error)) {
        const detail = (error.response?.data as { detail?: string } | undefined)?.detail;
        notify(detail || t('cameraConfigSaveFailed'), NotificationSeverity.ERROR);
      } else {
        notify(t('cameraConfigSaveFailed'), NotificationSeverity.ERROR);
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <StyledModal
      open={open}
      onRequestClose={onClose}
      modalHeading={t('ConfigureCameras')}
      passiveModal={true}
    >
      <ModalBody>
        <Description>{t('configureCamerasDescription')}</Description>

        <ButtonRow>
          <Button kind='ghost' size='sm' disabled={loading || submitting} onClick={loadData}>
            {t('refreshCameras')}
          </Button>
        </ButtonRow>

        {loading ? (
          <Description>{t('loadingCameras')}</Description>
        ) : cameras.length === 0 ? (
          <Description>{t('noCamerasAvailable')}</Description>
        ) : (
          <CameraList>
            {cameras.map((camera) => (
              <CameraRow key={camera}>
                <Checkbox
                  id={`camera-${camera}`}
                  labelText={camera}
                  checked={selectedCameras.includes(camera)}
                  onChange={(_, { checked }) => handleToggleCamera(camera, checked)}
                />
              </CameraRow>
            ))}
          </CameraList>
        )}
      </ModalBody>

      <ModalFooter>
        <Button kind='secondary' disabled={submitting} onClick={onClose}>
          {t('cancel')}
        </Button>
        <Button kind='primary' disabled={loading || submitting || cameras.length === 0} onClick={handleSubmit}>
          {t('Submit')}
        </Button>
      </ModalFooter>
    </StyledModal>
  );
};

export default CameraConfigModal;