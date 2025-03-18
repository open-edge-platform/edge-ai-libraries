#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import json
from time import ctime, sleep

import ntplib
import requests


class NTPTimeStamp:

    def __init__(self, ntp_server):
        self.ntp_server = ntp_server
        self._client = ntplib.NTPClient()

        self._verify_connection(max_retries=10)

    def _verify_connection(self, max_retries=10):
        connected = False
        retries = 0
        while not connected:
            try:
                self._client.request(self.ntp_server)
                connected = True
            except requests.exceptions.ConnectionError:
                if retries > max_retries:
                    raise
                print('Falied to established Connection to NTP server at',
                      self.ntp_server, ', retrying')
                sleep(1)
                retries += 1
        print('Established Connection to NTP server at', self.ntp_server)

    def _get_timestamp(self):
        return ctime(self._client.request(self.ntp_server).tx_time)

    def process(self, frame):
        frame.add_message(json.dumps({'ntp_timestamp': self._get_timestamp()}))
        return True
