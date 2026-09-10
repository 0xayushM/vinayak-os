"""
The morning brief is assembled from card sentences only — there is no step at
which a figure could be invented — and it must stay short, lead with what is
urgent, and be honest when a workspace has nothing to say.
"""
from datetime import date

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
