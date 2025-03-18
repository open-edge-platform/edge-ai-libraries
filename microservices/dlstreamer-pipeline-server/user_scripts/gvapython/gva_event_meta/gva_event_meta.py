#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import json
from src.server.common.utils import logging

logger = logging.get_logger('gva_event_meta', is_static=True)
'''
The gva_event_meta module is a set of APIs for developers to add, remove, and get events.
GVAJSONMeta (frame message) is utilized for storing events.
To avoid multiple "events" entries, already existing events are retrieved,
removed from frame, updated with the new event, and stored back to the frame.
'''

def add_event(frame, event_type, attributes):
    event = {'event-type': event_type}
    for key, value in attributes.items():
        event[key] = value
    existing_events = _get_events(frame)
    existing_events.append(event)
    remove_events(frame)
    events_message = {"events": existing_events}
    frame.add_message(json.dumps(events_message))

def remove_event(frame, event):
    events = _get_events(frame)
    if events:
        events.remove(event)
        remove_events(frame)
        events_message = {"events": events}
        frame.add_message(json.dumps(events_message))

def events(frame):
    return _get_events(frame)

def _get_events(frame):
    events = []
    for message in frame.messages():
        try:
            message_obj = json.loads(message)
            if "events" in message_obj:
                events = message_obj["events"]
                break
        except Exception as error:
            logger.error(error)
    return events

def remove_events(frame):
    messages = frame.messages()
    for message in messages:
        try:
            message_obj = json.loads(message)
            if "events" in message_obj.keys():
                frame.remove_message(message)
                return
        except Exception as error:
            logger.error(error)
