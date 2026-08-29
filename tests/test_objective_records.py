from eir_runtime import RunStore


def test_objective_records_are_opaque_and_do_not_change_run_state_shape(tmp_path):
    store = RunStore(tmp_path / "state.sqlite")
    store.create("r")
    before = store.load("r")["state"]
    store.objective_record("r", "measurement", {"coverage": 90.48}, "hash")
    assert store.objective_records("r") == [{"record_type": "measurement", "payload": {"coverage": 90.48}, "content_hash": "hash"}]
    assert store.load("r")["state"] == before
    store.close()
