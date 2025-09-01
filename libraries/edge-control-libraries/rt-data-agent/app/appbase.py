#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions
# and limitations under the License.

"""
Task template for Real Time Monitor Solutions.
"""
import os
import sys
import logging
import threading

LOG = logging.getLogger(__name__)

class BaseTask(threading.Thread):
    """
    Threading based Task.
    """

    _task_list = []

    def __init__(self, name=None, exec_func=None):
        threading.Thread.__init__(self)
        self._exec_func = exec_func
        self._event_loop = None
        self._is_task_stopping = False
        self._name = name
        if self not in BaseTask._task_list:
            BaseTask._task_list.append(self)

    @property
    def name(self):
        if self._name is None:
            self._name = self.__class__.__name__
        return self._name

    @classmethod
    def stop_all_tasks(cls):
        """
        Stops all tasks.
        """
        for task in BaseTask._task_list:
            if task.isAlive():
                task.stop()

    @classmethod
    def wait_all_tasks_end(cls):
        """
        Wait all task end.
        """
        for task in BaseTask._task_list:
            if task.isAlive():
                task.join()
        LOG.info("All task stopped! Bye~~~")

    def run(self):
        """
        Main entry for a task.
        """

        LOG.info("[Task-%s] starting!", self.name)
        try:
            if self._exec_func is not None:
                # pass task object to callback function
                self._exec_func(self)
            else:
                self.execute()
        except:
            LOG.error("[Task-%s] Failed!", self.name, exc_info=True)
            BaseTask.stop_all_tasks()
            sys.exit(1)
            return
        LOG.info("[Task - %s] Completed!", self.name)

    def execute(self):
        """
        Inherited class should implement customized task logic.
        """
        raise NotImplementedError("inherited class must implement this")

    @property
    def is_task_stopping(self):
        """
        Judge whether task is requested to stop.
        """
        return self._is_task_stopping

    def stop(self):
        """
        Stop a running task.
        """
        LOG.info("Stopping Task - %s", self.name)
        self._is_task_stopping = True

class AppBase:
    """
    Application template.
    """

    def __init__(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)-15s %(levelname)-6s [%(module)-6s] %(message)s')
        self.init()

    def init(self):
        """
        Initalization entry for an application instance.
        """
        LOG.debug("Init function is used to collect parameter from "
                  "environment variable, inhertied class could overide it")

    @staticmethod
    def get_env(key, default=None):
        """
        Get environment variable.
        """
        if key not in os.environ:
            LOG.warning("Cloud not find the key %s in environment, use "
                        "default value %s", key, str(default))
            return default
        return os.environ[key]

    def run_and_wait_task(self):
        """
        Run and wait all tasks
        """
        self.run()
        BaseTask.wait_all_tasks_end()

    def run(self):
        """
        Application main logic provided by inherited class.
        """
        raise NotImplementedError("Inherited class must implement this.")

    def stop(self):
        """
        Stop an application instance
        """
        BaseTask.stop_all_tasks()
        BaseTask.wait_all_tasks_end()
