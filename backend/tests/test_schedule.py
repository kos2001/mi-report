"""스케줄(파이프라인 cron) 설정 로직 + 엔드포인트 테스트."""

from __future__ import annotations

from datetime import datetime

from app import schedule


def _s(**kw):
    base = {"enabled": True, "frequency": "daily", "hour": 7, "minute": 0,
            "weekday": 0, "digestLimit": 20, "lastRunAt": None,
            "retryEnabled": True, "retryMinutes": 10}
    base.update(kw)
    return base


def _run(**kw):
    base = {"trigger": "auto", "status": "failure", "ranAt": "2026-06-17 07:00:00",
            "error": "실패", "ingested": None}
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


def test_retry_due_after_interval_elapsed():
    now = datetime(2026, 6, 17, 7, 10)  # 실패로부터 10분 경과
    runs = [_run(ranAt="2026-06-17 07:00:00")]
    assert schedule.retry_due(now, _s(), runs) is True


def test_retry_due_before_interval_not_due():
    now = datetime(2026, 6, 17, 7, 5)  # 실패로부터 5분(재시도 간격 10분 미만)
    runs = [_run(ranAt="2026-06-17 07:00:00")]
    assert schedule.retry_due(now, _s(), runs) is False


def test_retry_due_disabled_setting():
    now = datetime(2026, 6, 17, 7, 10)
    runs = [_run(ranAt="2026-06-17 07:00:00")]
    assert schedule.retry_due(now, _s(retryEnabled=False), runs) is False


def test_retry_due_last_run_succeeded():
    now = datetime(2026, 6, 17, 7, 10)
    runs = [_run(ranAt="2026-06-17 07:00:00", status="success")]
    assert schedule.retry_due(now, _s(), runs) is False


def test_retry_due_no_runs_today():
    now = datetime(2026, 6, 17, 7, 10)
    runs = [_run(ranAt="2026-06-16 07:00:00")]  # 어제 실패
    assert schedule.retry_due(now, _s(), runs) is False


def test_retry_due_stops_after_max_retries():
    now = datetime(2026, 6, 17, 8, 0)
    # 오늘 이미 3회 연속 실패(자동 재시도 상한) → 더 재시도하지 않음
    runs = [
        _run(ranAt="2026-06-17 07:30:00"),
        _run(ranAt="2026-06-17 07:20:00"),
        _run(ranAt="2026-06-17 07:10:00"),
        _run(ranAt="2026-06-17 07:00:00"),
    ]
    assert schedule.retry_due(now, _s(), runs) is False


def test_retry_due_ignores_manual_runs():
    now = datetime(2026, 6, 17, 7, 10)
    runs = [_run(ranAt="2026-06-17 07:05:00", trigger="manual", status="failure")]
    assert schedule.retry_due(now, _s(), runs) is False


def test_crontab_expr():
    assert schedule.crontab_expr(_s(minute=30, hour=8)) == "30 8 * * *"
    # weekly 월요일(weekday=0) → cron dow 1
    assert schedule.crontab_expr(_s(frequency="weekly", weekday=0, hour=6, minute=0)) == "0 6 * * 1"


def test_schedule_endpoints(client):
    got = client.get("/schedule").json()
    assert "schedule" in got and "crontab" in got and "nextRun" in got
    updated = client.put("/schedule", json={
        "enabled": True, "frequency": "weekly", "hour": 9, "minute": 30,
        "weekday": 4, "digestLimit": 15, "retryEnabled": True, "retryMinutes": 15,
    }).json()
    assert updated["schedule"]["enabled"] is True
    assert updated["schedule"]["frequency"] == "weekly" and updated["schedule"]["hour"] == 9
    assert updated["schedule"]["retryEnabled"] is True and updated["schedule"]["retryMinutes"] == 15
    assert updated["crontab"] == "30 9 * * 5"  # 금요일(4) → cron 5
    assert "금" in updated["describe"]


def test_log_run_and_recent_runs(isolated):
    schedule.log_run(trigger="manual", status="success", ingested=7)
    schedule.log_run(trigger="auto", status="failure", error="LLM 게이트웨이 타임아웃")
    runs = schedule.recent_runs(limit=10)
    assert len(runs) == 2
    # 최신 실행이 먼저 온다
    assert runs[0]["trigger"] == "auto"
    assert runs[0]["status"] == "failure"
    assert runs[0]["error"] == "LLM 게이트웨이 타임아웃"
    assert runs[0]["ingested"] is None
    assert runs[1]["trigger"] == "manual"
    assert runs[1]["status"] == "success"
    assert runs[1]["ingested"] == 7
    assert runs[1]["error"] is None


def test_recent_runs_respects_limit(isolated):
    for i in range(5):
        schedule.log_run(trigger="manual", status="success", ingested=i)
    assert len(schedule.recent_runs(limit=3)) == 3


def test_schedule_view_includes_runs_and_last_status(client):
    got = client.get("/schedule").json()
    assert got["runs"] == []
    assert got["lastStatus"] is None and got["lastError"] is None
