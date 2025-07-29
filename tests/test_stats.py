import json
import src.main as main


def test_stats_increment_and_flush(tmp_path):
    path = tmp_path / "stats.json"
    tracker = main.StatsTracker(str(path), flush_interval=0)
    tracker.increment("a")
    tracker.increment("a")
    tracker.increment("b")
    tracker.flush()
    data = json.loads(path.read_text())
    assert data["total"] == 3
    inst_a = next(i for i in data["instances"] if i["name"] == "a")
    inst_b = next(i for i in data["instances"] if i["name"] == "b")
    assert inst_a["total"] == 2
    assert inst_b["total"] == 1
    day = list(inst_a["days"].keys())[0]
    assert inst_a["days"][day] == 2
