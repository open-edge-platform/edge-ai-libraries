import time
import json
import threading
import os
from threading import local

_now = time.perf_counter_ns


def now_us():
    return _now() // 1000


class Tracer:
    def __init__(
        self,
        output_file="trace.json",
        pid=0,
        enabled=True,
        sample_rate=1,
        buffer_size=1024,
        flush_interval=0.5,
    ):
        self.output_file = output_file
        self.pid = pid
        self.enabled = enabled
        self.sample_rate = max(1, sample_rate)
        self.buffer_size = buffer_size
        self.flush_interval = flush_interval

        self._global_buffer = []
        self._lock = threading.Lock()

        self._running = False
        self._writer_thread = threading.Thread(target=self._writer, daemon=True)

        self._last_flush = time.time()

    def start(self):
        if not self.enabled:
            return
        self._running = True
        self._writer_thread.start()

    def stop(self):
        if not self.enabled:
            return
        
        buf = self._get_buffer()
        if len(buf) > 0:
            self._commit(buf[:])
            buf.clear()

        self._running = False
        self._writer_thread.join()
        self._flush(final=True)
        self._finalize_file()

    def _finalize_file(self):
        tmp_file = self.output_file + ".tmp"

        with open(self.output_file, "r") as fin, open(tmp_file, "w") as fout:
            fout.write('{"traceEvents":[\n')

            first = True
            for line in fin:
                line = line.strip()
                if not line:
                    continue

                if not first:
                    fout.write(",\n")
                fout.write(line)
                first = False

            fout.write("\n]}")

        os.replace(tmp_file, self.output_file)

    def _get_buffer(self):
        return self._global_buffer

    def _commit(self, events):
        with self._lock:
            self._global_buffer.extend(events)

    def _writer(self):
        while self._running:
            time.sleep(self.flush_interval)
            self._flush()

    def _flush(self, final=False):
        with self._lock:
            if not self._global_buffer:
                return

            data = self._global_buffer
            self._global_buffer = []

        # print("Output tracer file path")
        # print(self.output_file)
        mode = "a" if os.path.exists(self.output_file) else "w"
        with open(self.output_file, mode) as f:
            f.writelines(json.dumps(e) + "\n" for e in data)

    def should_trace(self):
        return self.enabled

    def _emit(self, event):
        if not self.enabled:
            return

        buf = self._get_buffer()
        buf.append(event)

        if len(buf) >= self.buffer_size:
            # print(f"full commit buffer {len(buf)}")
            self._commit(buf[:])
            buf.clear()

    def emit_complete(self, name, ts_start, ts_end, tid, cat="pipeline", args=None):
        self._emit(
            {
                "name": name,
                "cat": cat,
                "ph": "X",
                "ts": ts_start,
                "dur": ts_end - ts_start,
                "pid": self.pid,
                "tid": tid,
                "args": args or {},
            }
        )

    def flow_start(self, flow_id, tid, ts):
        self._emit(
            {
                "name": "flow",
                "cat": "flow",
                "ph": "s",
                "ts": ts,
                "pid": self.pid,
                "tid": tid,
                "id": str(flow_id),
                "bp": "e",
            }
        )

    def flow_step(self, flow_id, tid, ts):
        self._emit(
            {
                "name": "flow",
                "cat": "flow",
                "ph": "t",
                "ts": ts,
                "pid": self.pid,
                "tid": tid,
                "id": str(flow_id),
                "bp": "e",
            }
        )

    def flow_end(self, flow_id, tid, ts):
        self._emit(
            {
                "name": "flow",
                "cat": "flow",
                "ph": "f",
                "ts": ts,
                "pid": self.pid,
                "tid": tid,
                "id": str(flow_id),
                "bp": "e",
            }
        )

    def counter(self, name, value, ts):
        self._emit({"ph": "C", "name": name, "ts": ts, "pid": self.pid, "args": {"value": value}})

    def instant(self, name, tid, ts):
        self._emit(
            {
                "name": name,
                "cat": "event",
                "ph": "i",
                "s": "t",
                "ts": ts,
                "pid": self.pid,
                "tid": tid,
            }
        )

    def set_thread_name(self, tid, name):
        self._emit(
            {"ph": "M", "name": "thread_name", "pid": self.pid, "tid": tid, "args": {"name": name}}
        )

    def set_process_name(self, name):
        self._emit({"ph": "M", "name": "process_name", "pid": self.pid, "args": {"name": name}})


_tracer = None


def init_tracer(**kwargs):
    global _tracer
    _tracer = Tracer(**kwargs)
    _tracer.start()
    return _tracer


def get_tracer():
    return _tracer


def shutdown_tracer():
    global _tracer
    if _tracer:
        _tracer.stop()
