from src.adapters.queue import MemoryJobQueue
from src.adapters.storage import MemoryObjectStorage
from src.adapters.workflow import MemoryWorkflowEngine


def test_memory_storage_round_trip():
    storage = MemoryObjectStorage()
    storage.put_bytes("asset/a", b"video")
    assert storage.get_bytes("asset/a") == b"video"


def test_memory_queue_round_trip():
    queue = MemoryJobQueue()
    job_id = queue.enqueue({"kind": "render"})
    item = queue.dequeue()
    assert item is not None
    assert item["job_id"] == job_id
    assert item["kind"] == "render"
    assert queue.dequeue() is None


def test_memory_workflow_state():
    engine = MemoryWorkflowEngine()
    run_id = engine.start("render-project", {"project_id": "local"})
    state = engine.status(run_id)
    assert state["workflow"] == "render-project"
    assert state["status"] == "queued"
