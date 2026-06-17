"""
reasoning/history.py
─────────────────────
Chat threads (Windsurf-style tabs) + turns, scoped to (user, brand).

A THREAD is one conversation/tab. Each turn (question + structured answer) lives
in a thread. A thread is auto-named from its first question. Everything is
private to the logged-in owner within a brand.
"""
from __future__ import annotations

import json
import re


# ── Threads ───────────────────────────────────────────────────────────────────
def create_thread(conn, company_id: str, user_id: str, title: str | None = None) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO chat_thread (company_id, user_id, title) VALUES (%s, %s, %s) "
            "RETURNING id, title, created_at, updated_at",
            (company_id, user_id, title),
        )
        r = cur.fetchone()
    conn.commit()
    return {"id": str(r[0]), "title": r[1], "created_at": r[2].isoformat(),
            "updated_at": r[3].isoformat(), "turn_count": 0}


def list_threads(conn, company_id: str, user_id: str, limit: int = 100) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT t.id, t.title, t.created_at, t.updated_at,
                      (SELECT COUNT(*) FROM chat_turn c WHERE c.thread_id = t.id) AS n
               FROM chat_thread t
               WHERE t.company_id = %s AND t.user_id = %s
               ORDER BY t.updated_at DESC LIMIT %s""",
            (company_id, user_id, max(1, min(300, int(limit)))),
        )
        rows = cur.fetchall()
    return [{"id": str(r[0]), "title": r[1] or "New chat",
             "created_at": r[2].isoformat(), "updated_at": r[3].isoformat(),
             "turn_count": int(r[4])} for r in rows]


def _owns_thread(conn, company_id: str, user_id: str, thread_id: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM chat_thread WHERE id = %s AND company_id = %s AND user_id = %s",
                    (thread_id, company_id, user_id))
        return cur.fetchone() is not None


def rename_thread(conn, company_id: str, user_id: str, thread_id: str, title: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE chat_thread SET title = %s, updated_at = now() "
            "WHERE id = %s AND company_id = %s AND user_id = %s",
            (title[:80], thread_id, company_id, user_id),
        )
    conn.commit()


def delete_thread(conn, company_id: str, user_id: str, thread_id: str) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM chat_turn WHERE thread_id = %s AND company_id = %s AND user_id = %s",
                    (thread_id, company_id, user_id))
        cur.execute("DELETE FROM chat_thread WHERE id = %s AND company_id = %s AND user_id = %s",
                    (thread_id, company_id, user_id))
    conn.commit()


# ── Turns ─────────────────────────────────────────────────────────────────────
def list_turns(conn, company_id: str, user_id: str, thread_id: str) -> list[dict]:
    if not _owns_thread(conn, company_id, user_id, thread_id):
        return []
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, question, answer, created_at FROM chat_turn
               WHERE thread_id = %s ORDER BY created_at ASC""",
            (thread_id,),
        )
        rows = cur.fetchall()
    return [{"id": str(r[0]), "question": r[1], "answer": r[2],
             "created_at": r[3].isoformat() if r[3] else None} for r in rows]


def save_turn(conn, company_id: str, user_id: str, thread_id: str,
              question: str, answer: dict) -> str:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO chat_turn (company_id, user_id, thread_id, question, answer) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (company_id, user_id, thread_id, question, json.dumps(answer)),
        )
        tid = cur.fetchone()[0]
        # Auto-name the thread from its first question if still unnamed.
        cur.execute("SELECT title FROM chat_thread WHERE id = %s", (thread_id,))
        row = cur.fetchone()
        if row and (not row[0] or row[0] in ("New chat", "")):
            cur.execute("UPDATE chat_thread SET title = %s, updated_at = now() WHERE id = %s",
                        (_title_for(question), thread_id))
        else:
            cur.execute("UPDATE chat_thread SET updated_at = now() WHERE id = %s", (thread_id,))
    conn.commit()
    return str(tid)


# ── Auto title ────────────────────────────────────────────────────────────────
def _title_for(question: str) -> str:
    """A short tab title from the first question. Uses Claude (Haiku) when active,
    else a clean heuristic from the question's first words."""
    q = (question or "").strip()
    try:
        from vinayak.reasoning import llm
        if llm.is_active():
            client = llm._get_client()
            resp = client.messages.create(
                model=llm.model_fast(), max_tokens=16,
                system="Give a 3-5 word title (Title Case, no quotes, no period) for this business question.",
                messages=[{"role": "user", "content": q}],
            )
            t = "".join(getattr(b, "text", "") for b in resp.content)
            t = re.sub(r"^[#*\-\s\"']+", "", t).strip().strip('"').strip(".").splitlines()[0].strip()
            if t:
                return t[:60]
    except Exception:
        pass
    words = re.sub(r"[^\w\s]", "", q).split()
    title = " ".join(words[:6]) or "New chat"
    return (title[:1].upper() + title[1:])[:60]
