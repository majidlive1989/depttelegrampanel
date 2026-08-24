from datetime import datetime, timedelta, timezone
from .db import db, utcnow


def rows(sql, params=()):
    with db() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def row(sql, params=()):
    with db() as conn:
        r = conn.execute(sql, params).fetchone()
        return dict(r) if r else None


def list_customers(search="", status=""):
    where, params = ["1=1"], []
    if search:
        where.append("name LIKE ?")
        params.append(f"%{search}%")
    if status:
        where.append("status=?")
        params.append(status)
    sql = f"""
    SELECT c.*,
      (SELECT COUNT(*) FROM promises p WHERE p.customer_id=c.id AND p.status IN ('awaiting_date','promised','overdue')) AS open_promises
    FROM customers c WHERE {' AND '.join(where)}
    ORDER BY c.debt_amount DESC, c.id DESC
    """
    return rows(sql, params)


def get_customer(customer_id):
    return row("SELECT * FROM customers WHERE id=?", (customer_id,))


def get_customer_by_chat(chat_id):
    return row("SELECT * FROM customers WHERE telegram_chat_id=?", (str(chat_id),))


def upsert_customer(name, debt_amount, external_id=None):
    now = utcnow()
    with db() as conn:
        existing = None
        if external_id:
            existing = conn.execute("SELECT * FROM customers WHERE external_id=?", (external_id,)).fetchone()
        if not existing:
            existing = conn.execute("SELECT * FROM customers WHERE lower(name)=lower(?)", (name,)).fetchone()
        new_status = "settled" if int(debt_amount) <= 0 else "active"
        if existing:
            conn.execute(
                "UPDATE customers SET name=?, debt_amount=?, updated_at=?, status=?, collection_active=CASE WHEN ?<=0 THEN 0 ELSE collection_active END WHERE id=?",
                (name, int(debt_amount), now, new_status, int(debt_amount), existing["id"]),
            )
            return existing["id"], "updated"
        cur = conn.execute(
            "INSERT INTO customers(external_id,name,debt_amount,status,created_at,updated_at) VALUES(?,?,?,?,?,?)",
            (external_id, name, int(debt_amount), new_status, now, now),
        )
        return cur.lastrowid, "inserted"


def update_customer(customer_id, fields):
    allowed = {"name", "debt_amount", "telegram_chat_id", "telegram_group_title", "status"}
    pairs, params = [], []
    for k, v in fields.items():
        if k in allowed:
            pairs.append(f"{k}=?")
            params.append(v)
    if not pairs:
        return get_customer(customer_id)
    if "debt_amount" in fields and int(fields["debt_amount"] or 0) <= 0:
        pairs.extend(["status='settled'", "collection_active=0"])
    pairs.append("updated_at=?")
    params.extend([utcnow(), customer_id])
    with db() as conn:
        conn.execute(f"UPDATE customers SET {', '.join(pairs)} WHERE id=?", params)
    return get_customer(customer_id)


def bind_group(customer_id, chat_id, title=None):
    with db() as conn:
        conn.execute("UPDATE customers SET telegram_chat_id=NULL, telegram_group_title=NULL WHERE telegram_chat_id=? AND id<>?", (str(chat_id), customer_id))
        conn.execute(
            "UPDATE customers SET telegram_chat_id=?, telegram_group_title=?, updated_at=? WHERE id=?",
            (str(chat_id), title or "", utcnow(), customer_id),
        )
    return get_customer(customer_id)


def add_message(customer_id, direction, body, telegram_message_id=None):
    now = utcnow()
    with db() as conn:
        conn.execute(
            "INSERT INTO messages(customer_id,direction,body,telegram_message_id,created_at) VALUES(?,?,?,?,?)",
            (customer_id, direction, body, str(telegram_message_id or ""), now),
        )
        col = "last_contact_at" if direction == "out" else "last_reply_at"
        conn.execute(f"UPDATE customers SET {col}=?, updated_at=? WHERE id=?", (now, now, customer_id))


def set_collection_active(customer_id, active=True):
    now = utcnow()
    with db() as conn:
        conn.execute(
            "UPDATE customers SET collection_active=?, collection_started_at=CASE WHEN ?=1 THEN ? ELSE collection_started_at END, updated_at=? WHERE id=?",
            (1 if active else 0, 1 if active else 0, now, now, customer_id),
        )


def recent_contact_within(customer_id, minutes):
    if minutes <= 0:
        return False
    customer = get_customer(customer_id)
    if not customer or not customer.get("last_contact_at"):
        return False
    try:
        last = datetime.fromisoformat(customer["last_contact_at"])
    except ValueError:
        return False
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - last < timedelta(minutes=minutes)


def create_promise(customer_id, amount, source_message=""):
    now = utcnow()
    with db() as conn:
        # Keep at most one unfinished date-selection promise per customer.
        conn.execute("UPDATE promises SET status='cancelled', updated_at=? WHERE customer_id=? AND status='awaiting_date'", (now, customer_id))
        cur = conn.execute(
            "INSERT INTO promises(customer_id,amount,status,source_message,created_at,updated_at) VALUES(?,?,?,?,?,?)",
            (customer_id, int(amount), "awaiting_date", source_message, now, now),
        )
        return cur.lastrowid


def latest_awaiting_promise(customer_id):
    return row(
        "SELECT * FROM promises WHERE customer_id=? AND status='awaiting_date' ORDER BY id DESC LIMIT 1",
        (customer_id,),
    )


def set_promise_date(promise_id, due_date, due_date_jalali):
    with db() as conn:
        promise = conn.execute("SELECT customer_id FROM promises WHERE id=?", (promise_id,)).fetchone()
        if not promise:
            return None
        conn.execute(
            "UPDATE promises SET due_date=?, due_date_jalali=?, status='promised', reminder_sent=0, updated_at=? WHERE id=?",
            (due_date, due_date_jalali, utcnow(), promise_id),
        )
        conn.execute("UPDATE customers SET collection_active=0, updated_at=? WHERE id=?", (utcnow(), promise["customer_id"]))
    return get_promise(promise_id)


def get_promise(promise_id):
    return row("SELECT p.*, c.name customer_name, c.telegram_chat_id FROM promises p JOIN customers c ON c.id=p.customer_id WHERE p.id=?", (promise_id,))


def list_promises(status=""):
    where = "WHERE p.status=?" if status else ""
    params = (status,) if status else ()
    return rows(
        f"""SELECT p.*, c.name customer_name, c.debt_amount, c.telegram_group_title
        FROM promises p JOIN customers c ON c.id=p.customer_id
        {where}
        ORDER BY CASE WHEN p.due_date IS NULL THEN 1 ELSE 0 END, p.due_date ASC, p.id DESC""",
        params,
    )


def update_promise_status(promise_id, status):
    with db() as conn:
        conn.execute("UPDATE promises SET status=?, updated_at=? WHERE id=?", (status, utcnow(), promise_id))
    return get_promise(promise_id)


def due_promises(today_iso):
    return rows(
        """SELECT p.*, c.name customer_name, c.telegram_chat_id
        FROM promises p JOIN customers c ON c.id=p.customer_id
        WHERE p.status='promised' AND p.due_date<=? AND p.reminder_sent=0 AND c.telegram_chat_id IS NOT NULL""",
        (today_iso,),
    )


def mark_promise_reminded(promise_id):
    with db() as conn:
        promise = conn.execute("SELECT customer_id FROM promises WHERE id=?", (promise_id,)).fetchone()
        conn.execute("UPDATE promises SET reminder_sent=1, status='overdue', updated_at=? WHERE id=?", (utcnow(), promise_id))
        if promise:
            conn.execute("UPDATE customers SET collection_active=1, collection_started_at=?, updated_at=? WHERE id=?", (utcnow(), utcnow(), promise["customer_id"]))


def dashboard():
    with db() as conn:
        c = conn.execute("SELECT COUNT(*) n, COALESCE(SUM(debt_amount),0) debt FROM customers WHERE debt_amount>0").fetchone()
        no_reply = conn.execute(
            """SELECT COUNT(*) n FROM customers
               WHERE debt_amount>0 AND last_contact_at IS NOT NULL
               AND (last_reply_at IS NULL OR last_reply_at < last_contact_at)"""
        ).fetchone()["n"]
        promised = conn.execute("SELECT COUNT(*) n FROM promises WHERE status='promised'").fetchone()["n"]
        overdue = conn.execute("SELECT COUNT(*) n FROM promises WHERE status='overdue'").fetchone()["n"]
        connected = conn.execute("SELECT COUNT(*) n FROM customers WHERE debt_amount>0 AND telegram_chat_id IS NOT NULL").fetchone()["n"]
        settled = conn.execute("SELECT COUNT(*) n FROM customers WHERE status='settled'").fetchone()["n"]
        active = conn.execute("SELECT COUNT(*) n FROM customers WHERE collection_active=1").fetchone()["n"]
        return {
            "debtors": c["n"], "total_debt": c["debt"], "no_reply": no_reply,
            "promised": promised, "overdue": overdue, "connected": connected,
            "settled": settled, "active_collections": active,
        }


def record_import(filename, file_type, row_count, inserted, updated, skipped):
    with db() as conn:
        conn.execute(
            "INSERT INTO imports(filename,file_type,row_count,inserted_count,updated_count,skipped_count,created_at) VALUES(?,?,?,?,?,?,?)",
            (filename, file_type, row_count, inserted, updated, skipped, utcnow()),
        )
