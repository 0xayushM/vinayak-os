"""
The morning brief is assembled from card sentences only — there is no step at
which a figure could be invented — and it must stay short, lead with what is
urgent, and be honest when a workspace has nothing to say.

It is also evidence: every attempt is logged, and "arrived every working day"
is counted from that log. And it carries the one decision Milestone 1 is stuck
on — experiments nobody has accepted — without becoming a list he skims past.
"""
from datetime import date, timedelta

from vinayak import brief as B


def _card(key, title, display, why, severity, change=None, action=None):
    return {"key": key, "title": title,
            "headline": {"value": 1, "display": display},
            "change": change, "why": why, "items": [], "action": action,
            "confidence": "CERTAIN", "severity": severity,
            "stale": False, "last_synced_at": None}


def _patch_cards(monkeypatch, cards, no_data=False):
    monkeypatch.setattr(B.C, "build_cards",
                        lambda conn, cid, role=None, pinned=None, sort="role": {
                            "cards": cards, "role": role, "failed": [],
                            "no_data": no_data, "needs_attention": 0})


def test_urgent_leads_and_sets_the_subject(monkeypatch):
    _patch_cards(monkeypatch, [
        _card("aging_drift", "Aging drift", "₹17.00L",
              "₹10.80L moved into the 61–90 and 90+ buckets.", 90,
              change={"value": 1, "display": "+₹10.80L", "direction": "bad", "label": "in 30 days"},
              action={"label": "Draft chases (3)", "kind": "draft_chase", "params": {}}),
        _card("concentration", "Customer concentration", "84.5%", "Top 3 are 84.5%.", 45),
    ])
    b = B.build_brief(None, "protegere", today=date(2026, 9, 10))
    assert "1 thing" in b["subject"]
    assert b["text"].index("Aging drift") < b["text"].index("Customer concentration")
    assert "₹10.80L" in b["text"] and "Draft chases (3)" in b["text"]
    assert b["urgent"] == 1


def test_quiet_day_says_so_without_inventing_urgency(monkeypatch):
    _patch_cards(monkeypatch, [_card("week_delta", "What changed this week", "₹5.79L",
                                     "In line with your usual week.", 20)])
    b = B.build_brief(None, "protegere", today=date(2026, 9, 10))
    assert "nothing urgent" in b["subject"]
    assert b["urgent"] == 0


def test_quiet_cards_are_left_out_and_the_brief_stays_short(monkeypatch):
    _patch_cards(monkeypatch, [_card(f"c{i}", f"Card {i}", "₹1", "Something.", 70 - i)
                               for i in range(12)]
                              + [_card("silent", "Silent", "0", "Nothing.", 2)])
    b = B.build_brief(None, "protegere", today=date(2026, 9, 10))
    assert len(b["cards"]) <= B.BRIEF_MAX_CARDS
    assert all(c["severity"] >= B.BRIEF_MIN_SEVERITY for c in b["cards"])
    assert "Silent" not in b["text"]


def test_a_workspace_with_no_data_is_told_plainly(monkeypatch):
    _patch_cards(monkeypatch, [], no_data=True)
    b = B.build_brief(None, "fresh", today=date(2026, 9, 10))
    assert b["no_data"] is True
    assert "sync" in b["text"].lower()
    assert b["cards"] == []


def test_html_is_inert_and_escapes_content(monkeypatch):
    _patch_cards(monkeypatch, [_card("x", "Card <b>", "₹1",
                                     "Customer <script>alert(1)</script> & Co owes money.", 70)])
    b = B.build_brief(None, "protegere", today=date(2026, 9, 10))
    assert "<script" not in b["html"].lower()
    assert "&lt;script&gt;" in b["html"] and "&amp;" in b["html"]


def test_link_has_no_dangling_fragment(monkeypatch):
    monkeypatch.setenv("NEXT_PUBLIC_APP_URL", "https://example.com/")
    assert B._card_link("protegere") == "https://example.com/w/protegere/dashboard"
    assert B._card_link("protegere", "cash_30d").endswith("#cash_30d")


def test_viewers_do_not_get_the_brief():
    class _Cur:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, *a): pass
        def fetchall(self): return [("owner@x.com", "owner"), ("cfo@x.com", "finance"),
                                    ("look@x.com", "viewer"), ("new@x.com", None)]
    class _Conn:
        def cursor(self): return _Cur()
    got = B.brief_recipients(_Conn(), "protegere")
    assert "look@x.com" not in got
    assert {"owner@x.com", "cfo@x.com", "new@x.com"} == set(got)


# ── experiments waiting for a decision ─────────────────────────────────────
# 2026-09-14 is a Monday.
MON, TUE, THU, SAT = date(2026, 9, 14), date(2026, 9, 15), date(2026, 9, 17), date(2026, 9, 19)


def _exp(title, created=None, ends=None):
    return {"title": title, "created_at": created and f"{created.isoformat()}T09:00:00+05:30",
            "ends_at": ends and ends.isoformat()}


def _proposed(n, created):
    return [_exp(f"Suggestion {i}", created=created) for i in range(n)]


def test_monday_names_the_longest_waiting_suggestions_first():
    got = B.experiments_section(
        [_exp("Fresh", created=date(2026, 9, 13)), _exp("Stale", created=date(2026, 9, 1)),
         _exp("Middle", created=date(2026, 9, 8)), _exp("Newest", created=MON)],
        [], MON, "protegere")
    assert got["lines"][0] == "4 suggested experiments waiting for a decision (oldest 13 days)."
    assert got["titles"] == ["Stale", "Middle", "Fresh"]
    assert len(got["titles"]) == B.EXPERIMENT_TITLES


def test_on_other_days_a_fresh_suggestion_is_left_alone():
    """Filed on Monday and not yet decided is not a bottleneck; saying so every
    morning would teach him to skip the section."""
    assert B.experiments_section(_proposed(2, MON), [], THU, "p") is None


def test_on_other_days_a_long_wait_earns_one_line_and_no_list():
    got = B.experiments_section(_proposed(10, date(2026, 9, 1)), [], THU, "p")
    assert got["lines"] == ["10 suggested experiments waiting for a decision, the oldest for 16 days."]
    assert got["titles"] == []


def test_the_nudge_starts_the_day_after_the_wait_limit():
    at_limit = THU - timedelta(days=B.WAIT_NUDGE_DAYS)
    assert B.experiments_section(_proposed(1, at_limit), [], THU, "p") is None
    got = B.experiments_section(_proposed(1, at_limit - timedelta(days=1)), [], THU, "p")
    assert got["lines"] == ["1 suggested experiment waiting for a decision, the oldest for 4 days."]


def test_nothing_proposed_and_nothing_ending_says_nothing():
    assert B.experiments_section([], [], MON, "p") is None
    assert B.experiments_section([], [_exp("Later", ends=date(2026, 10, 1))], MON, "p") is None


def test_monday_mentions_running_experiments_that_end_this_week():
    got = B.experiments_section([], [_exp("Firm tone", ends=THU), _exp("Win-back", ends=SAT),
                                     _exp("Next week", ends=date(2026, 9, 22))], MON, "p")
    assert got["lines"] == ["2 running experiments end this week: Firm tone (Thu), Win-back (Sat)."]


def test_midweek_a_running_experiment_is_mentioned_only_on_its_last_day():
    running = [_exp("Firm tone", ends=THU)]
    assert B.experiments_section([], running, TUE, "p") is None
    assert B.experiments_section([], running, THU, "p")["lines"] == [
        "1 running experiment ends today: Firm tone (today)."]


def test_the_link_goes_to_the_experiments_page(monkeypatch):
    monkeypatch.setenv("NEXT_PUBLIC_APP_URL", "https://example.com/")
    got = B.experiments_section(_proposed(1, MON), [], MON, "protegere")
    assert got["link"] == "https://example.com/w/protegere/dashboard/experiments"
    monkeypatch.delenv("NEXT_PUBLIC_APP_URL")
    assert B.experiments_section(_proposed(1, MON), [], MON, "protegere")["link"] == ""


def test_the_section_rides_after_the_cards_and_is_escaped(monkeypatch):
    monkeypatch.setenv("NEXT_PUBLIC_APP_URL", "https://example.com")
    _patch_cards(monkeypatch, [_card("aging_drift", "Aging drift", "₹17.00L", "Moved.", 90)])
    monkeypatch.setattr(B, "_read_experiments", lambda conn, cid: (
        [_exp("Clear <dead> stock & more", created=date(2026, 9, 1))], []))
    b = B.build_brief(None, "protegere", today=MON)
    assert b["text"].index("Aging drift") < b["text"].index("Experiments")
    assert "Clear <dead> stock & more" in b["text"]
    assert "/w/protegere/dashboard/experiments" in b["text"]
    assert "Clear &lt;dead&gt; stock &amp; more" in b["html"] and "<dead>" not in b["html"]
    # A decision to make this week never takes the subject line from a card.
    assert b["subject"] == "protegere: 1 thing need you today"


def test_a_failed_experiments_read_costs_the_section_not_the_brief(monkeypatch):
    _patch_cards(monkeypatch, [_card("x", "Card", "₹1", "Something.", 70)])
    b = B.build_brief(None, "protegere", today=MON)      # conn=None: the read raises
    assert b["experiments"] is None and "Card" in b["text"]


# ── the delivery log ───────────────────────────────────────────────────────
class _LogCur:
    def __init__(self, conn): self.conn = conn
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def execute(self, sql, params=None):
        if self.conn.fail:
            raise RuntimeError('relation "brief_deliveries" does not exist')
        self.conn.rows.append(params)
    def fetchall(self): return [(d,) for d in self.conn.days]


class _LogConn:
    def __init__(self, fail=False, days=()):
        self.fail, self.rows, self.days = fail, [], list(days)
        self.commits = self.rollbacks = 0
    def cursor(self): return _LogCur(self)
    def commit(self): self.commits += 1
    def rollback(self): self.rollbacks += 1


def _sending(monkeypatch, outcome):
    from vinayak import notify
    sent = []

    def fake_send(to, subject, body, html=None):
        sent.append({"to": to, "html": html})
        return outcome(to)
    monkeypatch.setattr(notify, "send_email", fake_send)
    monkeypatch.setattr(B, "_read_experiments", lambda conn, cid: ([], []))
    _patch_cards(monkeypatch, [_card("aging_drift", "Aging drift", "₹17.00L", "Moved.", 90)])
    return sent


def test_every_attempt_is_logged_including_the_failures(monkeypatch):
    sent = _sending(monkeypatch, lambda to: {"sent": True, "provider": "resend", "to": to}
                    if to.startswith("OK") else
                    {"sent": False, "provider": "resend", "error": "HTTP 500"})
    monkeypatch.setattr(B, "brief_recipients", lambda conn, cid: ["OK@x.com", "bad@x.com"])
    conn = _LogConn()
    out = B.send_brief(conn, "protegere")
    assert out["delivered"] == 1 and len(conn.rows) == 2
    ok, bad = conn.rows
    assert ok[1] == "ok@x.com" and ok[3] is True and ok[4] == "resend" and ok[5] is None
    assert bad[3] is False and bad[5] == "HTTP 500"
    assert ok[7] == '["aging_drift"]' and ok[8] == 1
    assert all(s["html"] and "<div" in s["html"] for s in sent)   # the html goes too


def test_a_broken_log_never_stops_a_send(monkeypatch):
    sent = _sending(monkeypatch, lambda to: {"sent": True, "provider": "smtp", "to": to})
    monkeypatch.setattr(B, "brief_recipients", lambda conn, cid: ["a@x.com", "b@x.com"])
    conn = _LogConn(fail=True)
    out = B.send_brief(conn, "protegere")
    assert [s["to"] for s in sent] == ["a@x.com", "b@x.com"]
    assert out["delivered"] == 2 and conn.rollbacks == 2


# ── working days: what the 30-day claim is counted against ──────────────────
def _run_of(days, ending):
    return [ending - timedelta(days=i) for i in range(days)]


def test_sunday_is_not_a_working_day_and_saturday_is():
    assert not B.is_working_day(date(2026, 9, 20))
    assert B.is_working_day(SAT) and B.is_working_day(MON)


def test_a_perfect_month_is_every_working_day():
    today = date(2026, 9, 30)
    s = B.delivery_summary(_run_of(30, today), today, days=30)
    # 1–30 Sep 2026 has four Sundays (6, 13, 20, 27).
    assert s["expected_working_days"] == 26 and s["delivered_working_days"] == 26
    assert s["every_working_day"] is True and s["missed"] == []


def test_a_sunday_brief_does_not_cover_a_missed_tuesday():
    today = date(2026, 9, 30)
    days = [d for d in _run_of(30, today) if d != TUE]
    s = B.delivery_summary(days, today, days=30)
    assert s["missed"] == ["2026-09-15"]
    assert s["delivered_working_days"] == 25 and s["every_working_day"] is False


def test_this_morning_is_not_a_miss_before_the_job_has_run():
    before = _run_of(6, THU - timedelta(days=1))
    s = B.delivery_summary(before, THU, days=7)
    assert s["missed"] == [] and s["expected_working_days"] == 5
    s = B.delivery_summary(before + [THU], THU, days=7)
    assert s["expected_working_days"] == 6 and s["every_working_day"] is True


def test_deliveries_outside_the_window_do_not_count():
    s = B.delivery_summary([date(2026, 8, 1)], THU, days=7)
    assert s["delivered_working_days"] == 0 and s["last_delivered"] is None


def test_no_history_is_not_a_perfect_record():
    s = B.delivery_summary([], MON, days=1)      # only today, not yet delivered
    assert s["expected_working_days"] == 0 and s["every_working_day"] is False


def test_delivery_days_reads_distinct_delivered_days_for_one_recipient():
    conn = _LogConn(days=[TUE, date(2026, 9, 16), THU])
    s = B.delivery_days(conn, "protegere", " Owner@X.com ", days=3, today=THU)
    assert conn.rows[0] == ("protegere", "owner@x.com", TUE, THU)
    assert s["every_working_day"] is True and s["recipient"] == "owner@x.com"
