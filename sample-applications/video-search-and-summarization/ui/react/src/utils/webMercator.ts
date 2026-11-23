// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

/** Maximum latitude represented by the standard Web Mercator tile grid. */
export const WEB_MERCATOR_MAX_LATITUDE = 85.0511287798066;

export const clampWebMercatorLatitude = (latitude: number): number =>
  Math.min(Math.max(latitude, -WEB_MERCATOR_MAX_LATITUDE), WEB_MERCATOR_MAX_LATITUDE);
