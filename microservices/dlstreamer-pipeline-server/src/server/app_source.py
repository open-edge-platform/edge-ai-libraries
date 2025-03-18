#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import abc

class AppSource(metaclass=abc.ABCMeta):
    """Abstract class representing an application source.

    When a pipeline with an application source with a matching class
    name and pipeline type is created the implementation class is
    instantiated and passed the pipeline instance and request.

    When the pipeline starts the start_frames method is called to
    signal that it is safe to push frames into the pipeline. Note:
    start frames may be called multiple times.

    When the pipeline can not handle more frames at a point in time
    the pause_frames method will be called. Note: pause frames may be
    called multiple times.

    When the pipeline has ended the finish method is called to allow
    the source to dispose of any resources. Finish will be called
    exactly once per pipeline.

    """

    @abc.abstractmethod
    def __init__(self, request, pipeline):
        """Initializes AppSource

        Parameters
        ----------
        request : dict
          Dictionary of pipeline request. Contains source, destination
          and parameters.  Beyond the required fields applications can
          extend the request to pass additional context.

        pipeline : GStreamerPipeline or FFMpegPipeline
          AppSource Classes can make direct use of the Pipeline implementation
          classes to interact with the underlying pipeline framework.

        """

    @abc.abstractmethod
    def start_frames(self):
        """Called when the pipeline can accept frames. May be called multiple times."""

    @abc.abstractmethod
    def pause_frames(self):
        """Called when the pipeline can not currently accept frames.
           May be called multiple times.
        """

    @abc.abstractmethod
    def finish(self):
        """Signals that the pipeline has ended."""

    @classmethod
    def create_app_source(cls, request, pipeline):
        """Factory method for creating an AppSource instance based on registered subclasses"""

        requested_source = request.get("source", {})
        requested_source_type = requested_source.get("type", None)
        requested_source_class = requested_source.get("class", None)
        source_class = None

        if ((requested_source_type == "application") and requested_source_class):
            for source_class in AppSource.__subclasses__():
                if (source_class.__name__ == requested_source_class):
                    break
            else:
                source_class = None

        if source_class:
            try:
                return source_class(request, pipeline)
            except Exception as error:
                raise Exception("Error Creating App Source: {},"
                                "Exception: {} {}".format(requested_source_class,
                                                          type(error),
                                                          error)) from error
        return None
