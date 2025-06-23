#!/usr/bin/env python3
# Copyright (C) 2022 Intel Corporationn
# SPDX-License-Identifier: MIT

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
import json
from gstgva.util import GVAJSONMeta
from threading import Thread
from gi.repository import Gst, GLib
import gi
import sys

gi.require_version('Gst', '1.0')

frame_number = 0
mainloop = None


def gobject_mainloop():
    global mainloop
    mainloop = GLib.MainLoop.new(None, False)
    mainloop.run()


def on_sample(sink):
    sample = sink.emit("pull-sample")
    buf = sample.get_buffer()
    for meta in GVAJSONMeta.iterate(buf):
        json_object = json.loads(meta.get_message())
        print(json.dumps(json_object))
    global frame_number
    frame_number += 1
    return Gst.FlowReturn.OK


Gst.init(None)

pipeline = Gst.parse_launch(" uridecodebin uri=https://raw.githubusercontent.com/open-edge-insights/video-ingestion/master/test_videos/pcb_d2000.avi ! videoconvert ! video/x-raw,format=BGR ! udfloader config=/home/pipeline-server/udfs/configs/python_pcb.json ! appsink name=sink")
appsink_element = pipeline.get_by_name("sink")

if appsink_element:
    appsink_element.set_property("emit-signals", True)
    appsink_element.set_property('sync', False)
    appsink_element.connect("new-sample", on_sample)


def bus_call(bus, message, unused_data=None):
    if message.type == Gst.MessageType.EOS:
        print("End of stream")
        global mainloop
        global pipeline
        mainloop.quit()
        mainloop = None


bus = pipeline.get_bus()
bus.add_signal_watch()
bus_connection_id = bus.connect("message", bus_call)

ret = pipeline.set_state(Gst.State.PLAYING)
if ret == Gst.StateChangeReturn.FAILURE:
    print("Unable to set the pipeline to the playing state.")
    exit(-1)
try:
    gobject_mainloop()
except (KeyboardInterrupt, SystemExit):
    pass

bus.remove_signal_watch()
bus.disconnect(bus_connection_id)
bus_connection_id = None
pipeline.set_state(Gst.State.NULL)
del pipeline
pipeline = None

print(" pipeline ended after processing frames ", frame_number)
exit()
