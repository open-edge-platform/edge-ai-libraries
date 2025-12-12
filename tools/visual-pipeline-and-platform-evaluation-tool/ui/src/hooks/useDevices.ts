import { useEffect } from "react";
import { useGetDevicesQuery } from "@/api/api.generated";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import { setDevices, selectDeviceByName } from "@/store/reducers/devices";

/**
 * Hook to ensure devices are loaded in the store.
 * Call this in the root layout or main component.
 */
export const useDevicesLoader = () => {
  const dispatch = useAppDispatch();
  const { data: devices } = useGetDevicesQuery();

  useEffect(() => {
    if (devices) {
      dispatch(setDevices(devices));
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
