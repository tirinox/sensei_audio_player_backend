import threading
import time

from editor.jobs import JobQueue


def wait_idle(job_queue, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not any(j['status'] in ('queued', 'running') for j in job_queue.snapshot()):
            return
        time.sleep(0.02)
    raise TimeoutError


def test_order_progress_failure_and_chain():
    done = []

    def ok(job, jobs):
        jobs.set_progress(job, 1, 2)
        done.append((job.kind, job.name))

    def rename(job, jobs):
        done.append((job.kind, job.name))
        return 'lb_' + job.name

    def fail(job, jobs):
        raise ValueError("boom")

    job_queue = JobQueue({"ok": ok, "rename": rename, "fail": fail})
    events = job_queue.subscribe()
    job_queue.start(capture_stdout=False)

    job_queue.submit('rename', 'JPX', 'a.mp3', then=['ok', 'fail', 'ok'])
    job_queue.submit('ok', 'JPX', 'b.mp3')
    wait_idle(job_queue)

    # the chain goes on with the new name and stops at the failure
    assert done == [('rename', 'a.mp3'), ('ok', 'b.mp3'), ('ok', 'lb_a.mp3')]
    by_kind = {(j['kind'], j['name']): j for j in job_queue.snapshot()}
    assert by_kind[('ok', 'lb_a.mp3')]['progress'] == (1, 2)
    assert by_kind[('fail', 'lb_a.mp3')]['status'] == 'failed'
    assert by_kind[('fail', 'lb_a.mp3')]['error'] == 'boom'
    assert len(job_queue.snapshot()) == 4

    assert not events.empty()
    job_queue.unsubscribe(events)


def test_busy_and_cancel():
    release = threading.Event()
    job_queue = JobQueue({"slow": lambda job, jobs: release.wait(5), "reindex": lambda job, jobs: None})
    job_queue.start(capture_stdout=False)

    job_queue.submit('slow', 'JPX', 'a.mp3')
    queued = job_queue.submit('slow', 'JPX', 'b.mp3')
    assert job_queue.is_busy('JPX', 'a.mp3') and job_queue.is_busy('JPX', 'b.mp3')
    assert not job_queue.is_busy('JPX', 'c.mp3') and not job_queue.is_busy('JPY', 'a.mp3')

    assert job_queue.cancel(queued.id)
    assert not job_queue.cancel(queued.id)
    assert not job_queue.is_busy('JPX', 'b.mp3')

    # a job for the whole code makes all its files busy
    job_queue.submit('reindex', 'JPX')
    assert job_queue.is_busy('JPX', 'c.mp3')

    release.set()
    wait_idle(job_queue)
    assert [j['status'] for j in job_queue.snapshot()] == ['done', 'cancelled', 'done']
    assert not job_queue.is_busy('JPX', 'c.mp3')
