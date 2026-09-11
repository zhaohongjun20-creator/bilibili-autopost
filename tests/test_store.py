import os, tempfile
from src.store import Store

def make_store():
    fd, path = tempfile.mkstemp(suffix=".db"); os.close(fd)
    return Store(path)

def test_record_and_is_published():
    s = make_store()
    assert not s.is_published(12345)
    s.record_fetched(12345, "ocean", "https://pexels.com/v/12345")
    s.mark_published(12345, "BV1xx411c7mD")
    assert s.is_published(12345)
    assert s.get_bvid(12345) == "BV1xx411c7mD"

def test_mark_failed_and_retry_queue():
    s = make_store()
    s.record_fetched(111, "x", "u")
    s.mark_failed(111, "upload timeout")
    rows = s.pending_retry()
    assert len(rows) == 1 and rows[0]["pexels_id"] == 111
    s.mark_published(111, "BV2")
    assert s.pending_retry() == []

def test_duplicate_record_rejected():
    s = make_store()
    s.record_fetched(123, "x", "u")
    try:
        s.record_fetched(123, "x", "u")  # 同一素材二次记录应抛错
        assert False, "should raise"
    except Exception:
        pass
