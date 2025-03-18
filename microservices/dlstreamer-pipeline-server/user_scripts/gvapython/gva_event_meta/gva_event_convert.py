#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import json
import gva_event_meta
from src.server.common.utils import logging

logger = logging.get_logger('gva_event_convert', is_static=True)

def process_frame(frame):
    try:
        add_events_message(frame)
    except Exception as error:
        logger.error(error)
        return False
    return True

def add_events_message(frame):
    events = gva_event_meta.events(frame)
    if not events:
        return
    gva_event_meta.remove_events(frame)
    for message in frame.messages():
        message_obj = json.loads(message)
        if "objects" in message_obj:
            frame.remove_message(message)
            message_obj['events'] = events
            frame.add_message(json.dumps(message_obj, separators=(',', ':')))
            break
