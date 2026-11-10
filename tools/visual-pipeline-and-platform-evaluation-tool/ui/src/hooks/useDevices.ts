import { useEffect, useState } from "react";
import { useGetDevicesQuery } from "@/api/api.generated";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import { setDevices, selectDeviceByName } from "@/store/reducers/devices";

const DEVICES_RETRY_INTERVAL_MS = 2000;

/**
 * Hook to ensure devices are loaded in the store.
 * Call this in the root layout or main component.
 */
export const useDevicesLoader = () => {
  const dispatch = useAppDispatch();
  const [loaded, setLoaded] = useState(false);
  // The backend serves the device list only once its initialization ends,
  // so keep asking until the first list arrives.
  const { data: devices } = useGetDevicesQuery(undefined, {
    pollingInterval: loaded ? 0 : DEVICES_RETRY_INTERVAL_MS,
  });

  useEffect(() => {
    if (devices) {
      dispatch(setDevices(devices));
      setLoaded(true);
    }
  }, [devices, dispatch]);
};

/**
 * Hook to get a device by name from the store.
 * Returns undefined if device is not found.
 */
export const useDeviceByName = (deviceName: string) => {
  return useAppSelector((state) => selectDeviceByName(state, deviceName));
};
