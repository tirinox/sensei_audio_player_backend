import itertools
import queue
import sys
import threading
import time
import traceback

MAX_LOG_LINES = 500
KEEP_FINISHED_JOBS = 30


class Job:
    def __init__(self, job_id, kind, code, name, params, then):
        self.id = job_id
        self.kind = kind
        self.code = code
        self.name = name  # file name; None for jobs about a whole code
        self.params = params
        self.then = then  # kinds to queue for the same file after this one succeeds
        self.status = 'queued'  # queued -> running -> done | failed | cancelled
        self.progress = None  # (done, total)
        self.error = None
        self.result = None  # new file name, if the job renamed the file
        self.data = None  # anything else the handler wants to show in the browser
        self.log = []
        self.created = time.time()
        self.started = None
        self.finished = None

    @property
    def active(self):
        return self.status in ('queued', 'running')

    def to_dict(self, with_log=False):
        result = {
            "id": self.id, "kind": self.kind, "code": self.code, "name": self.name, "params": self.params,
            "then": self.then, "status": self.status, "progress": self.progress, "error": self.error, "result": self.result, "data": self.data,
            "created": self.created, "started": self.started, "finished": self.finished,
        }
        if with_log:
            result["log"] = self.log
        return result


class JobLogWriter:
    """Replaces sys.stdout: print() of the worker thread goes to the log of the running job as well"""

    def __init__(self, original, job_queue):
        self.original = original
        self.job_queue = job_queue
        self.buffer = ''

    def write(self, text):
        try:
            self.original.write(text)
        except ValueError:
            pass  # the original stream is closed
        if threading.current_thread() is self.job_queue.worker:
            self.buffer += text
            *lines, self.buffer = self.buffer.split('\n')
            for line in lines:
                self.job_queue.add_log_line(line)
        return len(text)

    def flush(self):
        self.original.flush()

    def __getattr__(self, item):
        return getattr(self.original, item)


class JobQueue:
    """
    One worker thread runs the jobs one by one: Whisper is heavy, and segment files must not be written concurrently.
    handlers: kind -> function(job, job_queue); it may return a new file name (after a rename) for the `then` jobs.
    """

    def __init__(self, handlers):
        self.handlers = handlers
        self.jobs = []
        self.lock = threading.Lock()
        self.pending = queue.Queue()
        self.subscribers = []
        self.ids = itertools.count(1)
        self.current = None
        self.worker = threading.Thread(target=self.run, daemon=True, name='job-worker')
        self.started = False

    def start(self, capture_stdout=True):
        if not self.started:
            self.started = True
            if capture_stdout:
                sys.stdout = JobLogWriter(sys.stdout, self)
            self.worker.start()

    # ---- jobs ----

    def submit(self, kind, code=None, name=None, params=None, then=()):
        if kind not in self.handlers:
            raise ValueError(f"Unknown job kind: {kind}")
        with self.lock:
            job = Job(next(self.ids), kind, code, name, params or {}, list(then))
            self.jobs.append(job)
            finished = [j for j in self.jobs if not j.active]
            for old in finished[:-KEEP_FINISHED_JOBS]:
                self.jobs.remove(old)
        self.publish_job(job)
        self.pending.put(job)
        return job

    def cancel(self, job_id):
        with self.lock:
            job = next((j for j in self.jobs if j.id == job_id), None)
            if not job or job.status != 'queued':
                return False
            job.status = 'cancelled'
            job.finished = time.time()
        self.publish_job(job)
        return True

    def is_busy(self, code, name):
        """A file is read-only for the editor while a job for it, for its whole code or for everything (upload) is active"""
        with self.lock:
            return any(j.active and (j.code is None or (j.code == code and j.name in (name, None))) for j in self.jobs)

    def has_active(self):
        with self.lock:
            return any(j.active for j in self.jobs)

    def last_finished(self, kinds):
        with self.lock:
            return next((j for j in reversed(self.jobs) if j.kind in kinds and not j.active), None)

    def snapshot(self):
        with self.lock:
            return [j.to_dict(with_log=True) for j in self.jobs]

    def set_progress(self, job, done, total):
        job.progress = (done, total)
        self.publish_job(job)

    def add_log_line(self, line):
        job = self.current
        if job is None:
            return
        job.log.append(line)
        del job.log[:-MAX_LOG_LINES]
        self.publish({"type": "log", "id": job.id, "line": line})

    def run(self):
        while True:
            job = self.pending.get()
            if job.status != 'queued':
                continue

            job.status = 'running'
            job.started = time.time()
            self.current = job
            self.publish_job(job)

            new_name = None
            try:
                new_name = job.result = self.handlers[job.kind](job, self)
                job.status = 'done'
            except Exception as e:
                traceback.print_exc()
                print(f"Job failed: {e}")
                job.status = 'failed'
                job.error = str(e) or type(e).__name__
            finally:
                sys.stdout.flush()
                job.finished = time.time()
                self.current = None
                self.publish_job(job)

            if job.status == 'done' and job.then:
                self.submit(job.then[0], job.code, new_name or job.name, then=job.then[1:])

    # ---- events for the browser (SSE) ----

    def subscribe(self):
        subscriber = queue.Queue()
        with self.lock:
            self.subscribers.append(subscriber)
        return subscriber

    def unsubscribe(self, subscriber):
        with self.lock:
            if subscriber in self.subscribers:
                self.subscribers.remove(subscriber)

    def publish(self, event):
        with self.lock:
            subscribers = list(self.subscribers)
        for subscriber in subscribers:
            subscriber.put(event)

    def publish_job(self, job):
        self.publish({"type": "job", "job": job.to_dict()})
