#
# Apache v2 license
# Copyright (C) 2024-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

"""Connexion apiKey security handler (SDL438/SDL304 - threat model T-001).

Fixes: all REST endpoints were previously reachable by any network peer with
no authentication. Wired into src/rest_api/pipeline-server.yaml via the
ApiKeyAuth securityScheme's x-apikeyInfoFunc.
"""

import os

from src.common.log import get_logger

logger = get_logger('REST API Auth')

_WARNED_NO_KEY_CONFIGURED = False


def apikey_auth(api_key, required_scopes=None):  # noqa: E501
    """Validate the X-Api-Key header against the REST_API_KEY env var.

    Returns a token_info dict on success (per Connexion's apiKey contract),
    or None to reject the request with 401 Unauthorized.

    Fails closed by design: if REST_API_KEY is not configured, every request
    is rejected rather than silently allowing unauthenticated access.
    """
    global _WARNED_NO_KEY_CONFIGURED
    expected = os.environ.get('REST_API_KEY', '')

    if not expected:
        if not _WARNED_NO_KEY_CONFIGURED:
            logger.warning(
                'REST_API_KEY is not set - all REST API requests will be rejected. '
                'Set REST_API_KEY to a strong, unique value to enable access.'
            )
            _WARNED_NO_KEY_CONFIGURED = True
        return None

    if api_key == expected:
        return {'sub': 'api-client'}

    return None
