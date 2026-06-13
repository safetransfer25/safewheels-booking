import json
import os
import secrets
import sqlite3
from datetime import date, datetime, timedelta
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

ROOT = Path(__file__).parent
PUBLIC = ROOT / "public"
DB_PATH = Path(os.environ.get("SAFEWHEELS_DB", ROOT / "safewheels.sqlite"))
PORT = int(os.environ.get("PORT", "4173"))
SESSIONS = set()
LOGIN_USERNAME = os.environ.get("SAFEWHEELS_USERNAME", "admin")
LOGIN_PASSWORD = os.environ.get("SAFEWHEELS_PASSWORD", "Safe2026&&&")
SEED_DEMO_DATA = os.environ.get("SAFEWHEELS_SEED_DEMO", "1") == "1"
APP_TZ = ZoneInfo(os.environ.get("SAFEWHEELS_TZ", "Europe/Athens"))
SEASON_MONTHS = [
    (4, "Απρίλιος"),
    (5, "Μάιος"),
    (6, "Ιούνιος"),
    (7, "Ιούλιος"),
    (8, "Αύγουστος"),
    (9, "Σεπτέμβριος"),
    (10, "Οκτώβριος"),
    (11, "Νοέμβριος"),
]

VEHICLES = {"OPEL VIVARO", "PEUGEOT 5008"}
DRIVERS = {"Θεόδωρος Τσιάμης", "Γεώργιος Τσιάμης", "Ιωάννης Τσιάμης"}
PAYMENT_METHODS = {"Μετρητά", "Κάρτα"}


def db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def table_columns(conn, table):
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row["name"] for row in rows}


def init_db():
    with db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bookings (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              date TEXT NOT NULL,
              pickupTime TEXT NOT NULL,
              travelTime TEXT,
              flightNumber TEXT,
              customerName TEXT NOT NULL,
              phone TEXT,
              hotel TEXT,
              route TEXT,
              passengers INTEGER DEFAULT 1,
              luggage INTEGER DEFAULT 0,
              price REAL DEFAULT 0,
              deposit REAL DEFAULT 0,
              balance REAL DEFAULT 0,
              paymentStatus TEXT DEFAULT 'Unpaid',
              paymentMethod TEXT DEFAULT 'Μετρητά',
              vehicle TEXT DEFAULT 'OPEL VIVARO',
              driver TEXT,
              status TEXT DEFAULT 'Pending',
              notes TEXT,
              createdAt TEXT DEFAULT CURRENT_TIMESTAMP,
              updatedAt TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        columns = table_columns(conn, "bookings")
        if "paymentMethod" not in columns:
            conn.execute("ALTER TABLE bookings ADD COLUMN paymentMethod TEXT DEFAULT 'Μετρητά'")
        if "flightNumber" not in columns:
            conn.execute("ALTER TABLE bookings ADD COLUMN flightNumber TEXT")
        conn.execute("UPDATE bookings SET vehicle = 'OPEL VIVARO' WHERE vehicle IN ('SafeWheels 1', 'SafeWheels1')")
        conn.execute("UPDATE bookings SET vehicle = 'PEUGEOT 5008' WHERE vehicle IN ('SafeWheels 2', 'SafeWheels2')")
        conn.execute("UPDATE bookings SET paymentMethod = 'Μετρητά' WHERE paymentMethod IS NULL OR paymentMethod = ''")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS expenses (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              date TEXT NOT NULL,
              category TEXT NOT NULL DEFAULT 'Καύσιμα',
              description TEXT,
              amount REAL DEFAULT 0,
              paymentMethod TEXT DEFAULT 'Μετρητά',
              notes TEXT,
              createdAt TEXT DEFAULT CURRENT_TIMESTAMP,
              updatedAt TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        total = conn.execute("SELECT COUNT(*) AS total FROM bookings").fetchone()["total"]
        if total or not SEED_DEMO_DATA:
            return
        today = datetime.now().date().isoformat()
        seed = [
            (today, "08:20", "10:05", "A3 1234", "Maria Jensen", "+45 20 12 45 88", "Aqua Blu Boutique Hotel", "Αεροδρόμιο Κω -> Ξενοδοχείο", 2, 2, 45, "Paid", "Μετρητά", "OPEL VIVARO", "Θεόδωρος Τσιάμης", "Confirmed", "Παιδικό κάθισμα"),
            (today, "14:10", "15:00", "FR 2451", "Luca Moretti", "+39 333 700 1200", "Kos Aktis Art Hotel", "Λιμάνι Κω -> Ξενοδοχείο", 4, 3, 35, "Unpaid", "Κάρτα", "PEUGEOT 5008", "Γεώργιος Τσιάμης", "Pending", "Άφιξη με ferry από Ρόδο"),
        ]
        conn.executemany(
            """
            INSERT INTO bookings
            (date, pickupTime, travelTime, flightNumber, customerName, phone, hotel, route, passengers, luggage, price, paymentStatus, paymentMethod, vehicle, driver, status, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            seed,
        )


def row_to_dict(row):
    return dict(row) if row else None


def parse_date(value):
    return datetime.strptime(value, "%Y-%m-%d").date()


def month_bounds(month):
    start = datetime.strptime(month, "%Y-%m").date().replace(day=1)
    next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return start.isoformat(), (next_month - timedelta(days=1)).isoformat()


def normalize_booking(data):
    price = float(data.get("price") or 0)
    vehicle = str(data.get("vehicle") or "OPEL VIVARO")
    driver = str(data.get("driver") or "").strip()
    payment_method = str(data.get("paymentMethod") or "Μετρητά")
    return {
        "date": str(data.get("date") or "")[:10],
        "pickupTime": str(data.get("pickupTime") or ""),
        "travelTime": str(data.get("travelTime") or ""),
        "flightNumber": str(data.get("flightNumber") or "").strip().upper(),
        "customerName": str(data.get("customerName") or "").strip(),
        "phone": str(data.get("phone") or "").strip(),
        "hotel": str(data.get("hotel") or "").strip(),
        "route": str(data.get("route") or "").strip(),
        "passengers": int(data.get("passengers") or 1),
        "luggage": int(data.get("luggage") or 0),
        "price": price,
        "paymentStatus": str(data.get("paymentStatus") or "Unpaid"),
        "paymentMethod": payment_method if payment_method in PAYMENT_METHODS else "Μετρητά",
        "vehicle": vehicle if vehicle in VEHICLES else "OPEL VIVARO",
        "driver": driver if driver in DRIVERS else driver,
        "status": str(data.get("status") or "Pending"),
        "notes": str(data.get("notes") or "").strip(),
    }


def normalize_expense(data):
    payment_method = str(data.get("paymentMethod") or "Μετρητά")
    return {
        "date": str(data.get("date") or "")[:10],
        "category": str(data.get("category") or "Καύσιμα").strip(),
        "description": str(data.get("description") or "").strip(),
        "amount": float(data.get("amount") or 0),
        "paymentMethod": payment_method if payment_method in PAYMENT_METHODS else "Μετρητά",
        "notes": str(data.get("notes") or "").strip(),
    }


def booking_error(booking):
    if not booking["date"]:
        return "Η ημερομηνία είναι υποχρεωτική."
    if not booking["pickupTime"]:
        return "Η ώρα παραλαβής είναι υποχρεωτική."
    if not booking["customerName"]:
        return "Το όνομα πελάτη είναι υποχρεωτικό."
    return None


def expense_error(expense):
    if not expense["date"]:
        return "Η ημερομηνία είναι υποχρεωτική."
    if not expense["category"]:
        return "Η κατηγορία εξόδου είναι υποχρεωτική."
    if expense["amount"] < 0:
        return "Το ποσό δεν μπορεί να είναι αρνητικό."
    return None


def auto_complete_transfers(conn):
    cutoff = datetime.now(APP_TZ) - timedelta(minutes=30)
    rows = conn.execute(
        """
        SELECT id, date, pickupTime
        FROM bookings
        WHERE status NOT IN ('Completed', 'Cancelled')
        """
    ).fetchall()
    complete_ids = []
    for row in rows:
        try:
            pickup = datetime.strptime(f"{row['date']} {row['pickupTime']}", "%Y-%m-%d %H:%M")
            pickup = pickup.replace(tzinfo=APP_TZ)
        except ValueError:
            continue
        if pickup <= cutoff:
            complete_ids.append(row["id"])
    if complete_ids:
        placeholders = ",".join(["?"] * len(complete_ids))
        conn.execute(
            f"UPDATE bookings SET status = 'Completed', updatedAt = CURRENT_TIMESTAMP WHERE id IN ({placeholders})",
            complete_ids,
        )


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def translate_path(self, path):
        clean = urlparse(path).path.lstrip("/")
        if not clean:
            clean = "index.html"
        return str(PUBLIC / clean)

    def do_POST(self):
        if self.path == "/api/login":
            data = self.read_json()
            if data.get("username") == LOGIN_USERNAME and data.get("password") == LOGIN_PASSWORD:
                token = secrets.token_urlsafe(32)
                SESSIONS.add(token)
                return self.send_json({"token": token})
            return self.send_json({"error": "Λάθος στοιχεία σύνδεσης."}, 401)
        if self.path == "/api/bookings":
            return self.create_booking()
        if self.path == "/api/expenses":
            return self.create_expense()
        self.send_error(404)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/bookings":
            return self.list_bookings(parsed)
        if parsed.path == "/api/totals":
            return self.totals(parsed)
        if parsed.path == "/api/expenses":
            return self.list_expenses(parsed)
        if parsed.path == "/api/expense-summary":
            return self.expense_summary(parsed)
        if parsed.path == "/api/monthly-revenue":
            return self.monthly_revenue(parsed)
        if parsed.path.startswith("/api/"):
            return self.send_error(404)
        return super().do_GET()

    def do_PUT(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/bookings/"):
            return self.update_booking(parsed)
        if parsed.path.startswith("/api/expenses/"):
            return self.update_expense(parsed)
        return self.send_error(404)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/bookings/"):
            return self.delete_row("bookings", parsed)
        if parsed.path.startswith("/api/expenses/"):
            return self.delete_row("expenses", parsed)
        return self.send_error(404)

    def create_booking(self):
        if not self.authorized():
            return self.send_json({"error": "Unauthorized"}, 401)
        booking = normalize_booking(self.read_json())
        error = booking_error(booking)
        if error:
            return self.send_json({"error": error}, 400)
        keys = ", ".join(booking.keys())
        placeholders = ", ".join([f":{key}" for key in booking])
        with db() as conn:
            cur = conn.execute(f"INSERT INTO bookings ({keys}) VALUES ({placeholders})", booking)
            saved = conn.execute("SELECT * FROM bookings WHERE id = ?", (cur.lastrowid,)).fetchone()
        return self.send_json(row_to_dict(saved), 201)

    def list_bookings(self, parsed):
        if not self.authorized():
            return self.send_json({"error": "Unauthorized"}, 401)
        query = parse_qs(parsed.query)
        history = query.get("history", ["0"])[0] == "1"
        where = []
        params = {}
        with db() as conn:
            auto_complete_transfers(conn)
        if query.get("date", [""])[0]:
            where.append("date = :date")
            params["date"] = query["date"][0]
        if query.get("start", [""])[0] and query.get("end", [""])[0]:
            where.append("date BETWEEN :start AND :end")
            params["start"] = query["start"][0]
            params["end"] = query["end"][0]
        if query.get("q", [""])[0]:
            where.append("(customerName LIKE :q OR phone LIKE :q OR hotel LIKE :q OR date LIKE :q)")
            params["q"] = f"%{query['q'][0]}%"
        if history:
            where.append("status = 'Completed'")
        else:
            where.append("status != 'Completed'")
        sql = "SELECT * FROM bookings"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY date DESC, pickupTime DESC" if history else " ORDER BY date ASC, pickupTime ASC"
        with db() as conn:
            rows = conn.execute(sql, params).fetchall()
        return self.send_json([row_to_dict(row) for row in rows])

    def update_booking(self, parsed):
        if not self.authorized():
            return self.send_json({"error": "Unauthorized"}, 401)
        booking_id = parsed.path.rsplit("/", 1)[-1]
        booking = normalize_booking(self.read_json())
        error = booking_error(booking)
        if error:
            return self.send_json({"error": error}, 400)
        assignments = ", ".join([f"{key}=:{key}" for key in booking])
        with db() as conn:
            cur = conn.execute(
                f"UPDATE bookings SET {assignments}, updatedAt=CURRENT_TIMESTAMP WHERE id=:id",
                {**booking, "id": booking_id},
            )
            if cur.rowcount == 0:
                return self.send_json({"error": "Δεν βρέθηκε η κράτηση."}, 404)
            saved = conn.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()
        return self.send_json(row_to_dict(saved))

    def totals(self, parsed):
        if not self.authorized():
            return self.send_json({"error": "Unauthorized"}, 401)
        query = parse_qs(parsed.query)
        start = query.get("start", [""])[0]
        end = query.get("end", [""])[0]
        with db() as conn:
            auto_complete_transfers(conn)
            row = conn.execute(
                """
                SELECT
                  COUNT(*) AS bookings,
                  COALESCE(SUM(CASE WHEN paymentMethod = 'Μετρητά' THEN price ELSE 0 END), 0) AS cash,
                  COALESCE(SUM(CASE WHEN paymentMethod = 'Κάρτα' THEN price ELSE 0 END), 0) AS card,
                  COALESCE(SUM(price), 0) AS total
                FROM bookings
                WHERE date BETWEEN ? AND ? AND status NOT IN ('Cancelled', 'Completed')
                """,
                (start, end),
            ).fetchone()
        return self.send_json(row_to_dict(row))

    def create_expense(self):
        if not self.authorized():
            return self.send_json({"error": "Unauthorized"}, 401)
        expense = normalize_expense(self.read_json())
        error = expense_error(expense)
        if error:
            return self.send_json({"error": error}, 400)
        keys = ", ".join(expense.keys())
        placeholders = ", ".join([f":{key}" for key in expense])
        with db() as conn:
            cur = conn.execute(f"INSERT INTO expenses ({keys}) VALUES ({placeholders})", expense)
            saved = conn.execute("SELECT * FROM expenses WHERE id = ?", (cur.lastrowid,)).fetchone()
        return self.send_json(row_to_dict(saved), 201)

    def list_expenses(self, parsed):
        if not self.authorized():
            return self.send_json({"error": "Unauthorized"}, 401)
        query = parse_qs(parsed.query)
        month = query.get("month", [datetime.now().strftime("%Y-%m")])[0]
        start, end = month_bounds(month)
        with db() as conn:
            rows = conn.execute(
                "SELECT * FROM expenses WHERE date BETWEEN ? AND ? ORDER BY date ASC, id ASC",
                (start, end),
            ).fetchall()
        return self.send_json([row_to_dict(row) for row in rows])

    def update_expense(self, parsed):
        if not self.authorized():
            return self.send_json({"error": "Unauthorized"}, 401)
        expense_id = parsed.path.rsplit("/", 1)[-1]
        expense = normalize_expense(self.read_json())
        error = expense_error(expense)
        if error:
            return self.send_json({"error": error}, 400)
        assignments = ", ".join([f"{key}=:{key}" for key in expense])
        with db() as conn:
            cur = conn.execute(
                f"UPDATE expenses SET {assignments}, updatedAt=CURRENT_TIMESTAMP WHERE id=:id",
                {**expense, "id": expense_id},
            )
            if cur.rowcount == 0:
                return self.send_json({"error": "Δεν βρέθηκε το έξοδο."}, 404)
            saved = conn.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()
        return self.send_json(row_to_dict(saved))

    def expense_summary(self, parsed):
        if not self.authorized():
            return self.send_json({"error": "Unauthorized"}, 401)
        month = parse_qs(parsed.query).get("month", [datetime.now().strftime("%Y-%m")])[0]
        start, end = month_bounds(month)
        with db() as conn:
            revenue = conn.execute(
                "SELECT COALESCE(SUM(price), 0) AS total FROM bookings WHERE date BETWEEN ? AND ? AND status != 'Cancelled'",
                (start, end),
            ).fetchone()["total"]
            expenses = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) AS total FROM expenses WHERE date BETWEEN ? AND ?",
                (start, end),
            ).fetchone()["total"]
            by_category = conn.execute(
                "SELECT category, COALESCE(SUM(amount), 0) AS total FROM expenses WHERE date BETWEEN ? AND ? GROUP BY category ORDER BY total DESC",
                (start, end),
            ).fetchall()
        return self.send_json({
            "revenue": revenue,
            "expenses": expenses,
            "net": revenue - expenses,
            "byCategory": [row_to_dict(row) for row in by_category],
        })

    def monthly_revenue(self, parsed):
        if not self.authorized():
            return self.send_json({"error": "Unauthorized"}, 401)
        query = parse_qs(parsed.query)
        try:
            year = int(query.get("year", [datetime.now(APP_TZ).year])[0])
        except ValueError:
            year = datetime.now(APP_TZ).year

        months = []
        season = {"cash": 0, "card": 0, "total": 0, "expenses": 0, "net": 0}
        with db() as conn:
            auto_complete_transfers(conn)
            for month_num, month_name in SEASON_MONTHS:
                start = date(year, month_num, 1)
                next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
                end = next_month - timedelta(days=1)
                start_iso = start.isoformat()
                end_iso = end.isoformat()

                bookings = conn.execute(
                    """
                    SELECT date, pickupTime, route, customerName, price, paymentMethod
                    FROM bookings
                    WHERE date BETWEEN ? AND ? AND status != 'Cancelled'
                    ORDER BY date ASC, pickupTime ASC
                    """,
                    (start_iso, end_iso),
                ).fetchall()
                expenses = conn.execute(
                    """
                    SELECT date, description, category, amount
                    FROM expenses
                    WHERE date BETWEEN ? AND ?
                    ORDER BY date ASC, id ASC
                    """,
                    (start_iso, end_iso),
                ).fetchall()

                entries = []
                cash_total = 0
                card_total = 0
                expense_total = 0
                for booking in bookings:
                    price = float(booking["price"] or 0)
                    is_card = booking["paymentMethod"] == "Κάρτα"
                    if is_card:
                        card_total += price
                    else:
                        cash_total += price
                    entries.append({
                        "type": "booking",
                        "date": booking["date"],
                        "time": booking["pickupTime"],
                        "route": booking["route"] or "",
                        "customer": booking["customerName"] or "",
                        "cash": 0 if is_card else price,
                        "card": price if is_card else 0,
                        "expenses": 0,
                        "description": "",
                    })
                for expense in expenses:
                    amount = float(expense["amount"] or 0)
                    expense_total += amount
                    entries.append({
                        "type": "expense",
                        "date": expense["date"],
                        "time": "",
                        "route": "",
                        "customer": "",
                        "cash": 0,
                        "card": 0,
                        "expenses": amount,
                        "description": expense["description"] or expense["category"] or "",
                    })
                entries.sort(key=lambda item: (item["date"], item["time"] or "99:99", item["type"]))
                total = cash_total + card_total
                net = total - expense_total
                month_data = {
                    "month": month_num,
                    "name": month_name,
                    "cash": cash_total,
                    "card": card_total,
                    "total": total,
                    "expenses": expense_total,
                    "net": net,
                    "entries": entries,
                }
                months.append(month_data)
                for key in season:
                    season[key] += month_data[key]
        return self.send_json({"year": year, "months": months, "season": season})

    def delete_row(self, table, parsed):
        if not self.authorized():
            return self.send_json({"error": "Unauthorized"}, 401)
        item_id = parsed.path.rsplit("/", 1)[-1]
        with db() as conn:
            cur = conn.execute(f"DELETE FROM {table} WHERE id = ?", (item_id,))
        if cur.rowcount == 0:
            return self.send_json({"error": "Δεν βρέθηκε η εγγραφή."}, 404)
        self.send_response(204)
        self.end_headers()

    def authorized(self):
        return self.headers.get("x-safewheels-session") in SESSIONS

    def read_json(self):
        length = int(self.headers.get("content-length") or 0)
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    init_db()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"SafeWheels booking app running at http://localhost:{PORT}")
    server.serve_forever()
