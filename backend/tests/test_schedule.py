"""스케줄(파이프라인 cron) 설정 로직 + 엔드포인트 테스트."""

from __future__ import annotations

from datetime import datetime

from app import schedule


def _s(**kw):
    base = {"enabled": True, "frequency": "daily", "hour": 7, "minute": 0,
            "weekday": 0, "digestLimit": 20, "lastRunAt": None}
    base.update(kw)
    return base


def test_due_now_daily():
    now = datetime(2026, 6, 17, 7, 0)  # 수요일 07:00
    assert schedule.due_now(now, _s(), None) is True
    assert schedule.due_now(now, _s(enabled=False), None) is False
    assert schedule.due_now(now.replace(minute=1), _s(), None) is False
    # 같은 날 이미 실행 → 중복 방지
    assert schedule.due_now(now, _s(), datetime(2026, 6, 17, 7, 0)) is False


def test_due_now_weekly():
    wed = datetime(2026, 6, 17, 7, 0)  # 수요일(weekday=2)
    assert schedule.due_now(wed, _s(frequency="weekly", weekday=2), None) is True
    assert schedule.due_now(wed, _s(frequency="weekly", weekday=0), None) is False  # 월요일 설정


def test_next_run():
    now = datetime(2026, 6, 17, 9, 0)  # 07:00 이미 지남
    nxt = schedule.next_run(now, _s())
    assert nxt == datetime(2026, 6, 18, 7, 0)  # 다음날 07:00


def test_crontab_expr():
    assert schedule.crontab_expr(_s(minute=30, hour=8)) == "30 8 * * *"
    # weekly 월요일(weekday=0) → cron dow 1
    assert schedule.crontab_expr(_s(frequency="weekly", weekday=0, hour=6, minute=0)) == "0 6 * * 1"


def test_schedule_endpoints(client):
    got = client.get("/schedule").json()
    assert "schedule" in got and "crontab" in got and "nextRun" in got
    updated = client.put("/schedule", json={
        "enabled": True, "frequency": "weekly", "hour": 9, "minute": 30,
        "weekday": 4, "digestLimit": 15,
    }).json()
    assert updated["schedule"]["enabled"] is True
    assert updated["schedule"]["frequency"] == "weekly" and updated["schedule"]["hour"] == 9
    assert updated["crontab"] == "30 9 * * 5"  # 금요일(4) → cron 5
    assert "금" in updated["describe"]
