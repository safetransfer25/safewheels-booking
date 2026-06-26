import json
import os
import re
import shutil
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
BACKUP_DIR = Path(os.environ.get("SAFEWHEELS_BACKUP_DIR", DB_PATH.parent / "backups"))
MAX_BACKUPS = 20
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

DEFAULT_VEHICLES = ["OPEL VIVARO", "PEUGEOT 5008"]
DEFAULT_DRIVERS = ["Θεόδωρος Τσιάμης", "Γεώργιος Τσιάμης", "Ιωάννης Τσιάμης"]
DEFAULT_BOOKING_SOURCES = ["PRIVATE", "WELCOME", "CONNECTO"]
PAYMENT_METHODS = {"Μετρητά", "Κάρτα", "Πίστωση"}
TAX_STATUSES = {"Καταχωρημένο", "Μη Καταχωρημένο"}
BOOKING_STATUSES = {"Pending", "Confirmed", "Completed", "Cancelled"}


def db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def table_columns(conn, table):
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row["name"] for row in rows}


def ensure_option_table(conn, table):
    columns = table_columns(conn, table)
    if "active" not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN active INTEGER DEFAULT 1")
    if "createdAt" not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN createdAt TEXT")
        conn.execute(f"UPDATE {table} SET createdAt = CURRENT_TIMESTAMP WHERE createdAt IS NULL")
    if "updatedAt" not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN updatedAt TEXT")
        conn.execute(f"UPDATE {table} SET updatedAt = CURRENT_TIMESTAMP WHERE updatedAt IS NULL")


def ensure_booking_audit_table(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS booking_audit_log (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          bookingId INTEGER NOT NULL,
          action TEXT NOT NULL,
          loggedAt TEXT DEFAULT CURRENT_TIMESTAMP,
          createdAt TEXT,
          updatedAt TEXT,
          status TEXT,
          driver TEXT,
          vehicle TEXT,
          paymentMethod TEXT,
          taxStatus TEXT,
          snapshot TEXT
        )
        """
    )


def upsert_option(conn, table, name):
    clean = str(name or "").strip()
    if not clean:
        return
    existing = conn.execute(
        f"SELECT rowid AS option_rowid FROM {table} WHERE name = ? COLLATE NOCASE LIMIT 1",
        (clean,),
    ).fetchone()
    if existing:
        conn.execute(
            f"UPDATE {table} SET name = ?, active = 1, updatedAt = CURRENT_TIMESTAMP WHERE rowid = ?",
            (clean, existing["option_rowid"]),
        )
        return
    conn.execute(f"INSERT INTO {table} (name, active) VALUES (?, 1)", (clean,))


def seed_options(conn):
    for name in DEFAULT_VEHICLES:
        upsert_option(conn, "vehicles", name)
    for name in DEFAULT_DRIVERS:
        upsert_option(conn, "drivers", name)
    for name in DEFAULT_BOOKING_SOURCES:
        upsert_option(conn, "booking_sources", name)
    for row in conn.execute("SELECT DISTINCT vehicle AS name FROM bookings WHERE vehicle IS NOT NULL AND vehicle != ''").fetchall():
        upsert_option(conn, "vehicles", row["name"])
    for row in conn.execute("SELECT DISTINCT driver AS name FROM bookings WHERE driver IS NOT NULL AND driver != ''").fetchall():
        upsert_option(conn, "drivers", row["name"])
    for row in conn.execute("SELECT DISTINCT bookingSource AS name FROM bookings WHERE bookingSource IS NOT NULL AND bookingSource != ''").fetchall():
        upsert_option(conn, "booking_sources", row["name"])


def active_option_names(conn, table):
    return [
        row["name"]
        for row in conn.execute(f"SELECT name FROM {table} WHERE active = 1 ORDER BY name COLLATE NOCASE").fetchall()
    ]


def active_option_rows(conn, table):
    return [
        row_to_dict(row)
        for row in conn.execute(f"SELECT id, name FROM {table} WHERE active = 1 ORDER BY name COLLATE NOCASE").fetchall()
    ]


def init_db():
    backup_database("schema-change")
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
              bookingSource TEXT DEFAULT 'PRIVATE',
              taxStatus TEXT DEFAULT 'Μη Καταχωρημένο',
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
        if "bookingSource" not in columns:
            conn.execute("ALTER TABLE bookings ADD COLUMN bookingSource TEXT DEFAULT 'PRIVATE'")
        if "taxStatus" not in columns:
            conn.execute("ALTER TABLE bookings ADD COLUMN taxStatus TEXT DEFAULT 'Μη Καταχωρημένο'")
        conn.execute("UPDATE bookings SET vehicle = 'OPEL VIVARO' WHERE vehicle IN ('SafeWheels 1', 'SafeWheels1')")
        conn.execute("UPDATE bookings SET vehicle = 'PEUGEOT 5008' WHERE vehicle IN ('SafeWheels 2', 'SafeWheels2')")
        conn.execute("UPDATE bookings SET paymentMethod = 'Μετρητά' WHERE paymentMethod IS NULL OR paymentMethod = ''")
        conn.execute("UPDATE bookings SET bookingSource = 'PRIVATE' WHERE bookingSource IS NULL OR bookingSource = ''")
        conn.execute("UPDATE bookings SET taxStatus = 'Μη Καταχωρημένο' WHERE taxStatus IS NULL OR taxStatus = ''")
        repair_booking_dates(conn)

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS expenses (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              date TEXT NOT NULL,
              category TEXT NOT NULL DEFAULT 'Καύσιμα',
              description TEXT,
              amount REAL DEFAULT 0,
              paymentMethod TEXT DEFAULT 'Μετρητά',
              vehicle TEXT,
              notes TEXT,
              createdAt TEXT DEFAULT CURRENT_TIMESTAMP,
              updatedAt TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        expense_columns = table_columns(conn, "expenses")
        if "vehicle" not in expense_columns:
            conn.execute("ALTER TABLE expenses ADD COLUMN vehicle TEXT")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS vehicles (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL UNIQUE,
              active INTEGER DEFAULT 1,
              createdAt TEXT DEFAULT CURRENT_TIMESTAMP,
              updatedAt TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS drivers (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL UNIQUE,
              active INTEGER DEFAULT 1,
              createdAt TEXT DEFAULT CURRENT_TIMESTAMP,
              updatedAt TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS booking_sources (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL UNIQUE,
              active INTEGER DEFAULT 1,
              createdAt TEXT DEFAULT CURRENT_TIMESTAMP,
              updatedAt TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        ensure_booking_audit_table(conn)
        ensure_option_table(conn, "vehicles")
        ensure_option_table(conn, "drivers")
        ensure_option_table(conn, "booking_sources")
        seed_options(conn)
        ensure_booking_audit_baseline(conn)

        total = conn.execute("SELECT COUNT(*) AS total FROM bookings").fetchone()["total"]
        if total or not SEED_DEMO_DATA:
            return
        today = datetime.now().date().isoformat()
        seed = [
            (today, "08:20", "10:05", "A3 1234", "Maria Jensen", "+45 20 12 45 88", "Aqua Blu Boutique Hotel", "Αεροδρόμιο Κω -> Ξενοδοχείο", 2, 2, 45, "Paid", "Μετρητά", "OPEL VIVARO", "Θεόδωρος Τσιάμης", "PRIVATE", "Μη Καταχωρημένο", "Confirmed", "Παιδικό κάθισμα"),
            (today, "14:10", "15:00", "FR 2451", "Luca Moretti", "+39 333 700 1200", "Kos Aktis Art Hotel", "Λιμάνι Κω -> Ξενοδοχείο", 4, 3, 35, "Unpaid", "Κάρτα", "PEUGEOT 5008", "Γεώργιος Τσιάμης", "WELCOME", "Μη Καταχωρημένο", "Pending", "Άφιξη με ferry από Ρόδο"),
        ]
        conn.executemany(
            """
            INSERT INTO bookings
            (date, pickupTime, travelTime, flightNumber, customerName, phone, hotel, route, passengers, luggage, price, paymentStatus, paymentMethod, vehicle, driver, bookingSource, taxStatus, status, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            seed,
        )


def row_to_dict(row):
    return dict(row) if row else None


def utc_timestamp():
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def backup_database(reason):
    if not DB_PATH.exists():
        return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(APP_TZ).strftime("%Y_%m_%d_%H%M")
    backup_path = BACKUP_DIR / f"safewheels_backup_{timestamp}.db"
    suffix = 1
    while backup_path.exists():
        backup_path = BACKUP_DIR / f"safewheels_backup_{timestamp}_{suffix:02d}.db"
        suffix += 1
    shutil.copy2(DB_PATH, backup_path)
    prune_backups()
    return backup_path


def prune_backups():
    backups = sorted(
        BACKUP_DIR.glob("safewheels_backup_*.db"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    for old_backup in backups[MAX_BACKUPS:]:
        old_backup.unlink(missing_ok=True)


def audit_booking(conn, booking_id, action):
    ensure_booking_audit_table(conn)
    row = conn.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()
    if not row:
        return
    conn.execute(
        """
        INSERT INTO booking_audit_log
        (bookingId, action, createdAt, updatedAt, status, driver, vehicle, paymentMethod, taxStatus, snapshot)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row["id"],
            action,
            row["createdAt"],
            row["updatedAt"],
            row["status"],
            row["driver"],
            row["vehicle"],
            row["paymentMethod"],
            row["taxStatus"],
            json.dumps(row_to_dict(row), ensure_ascii=False),
        ),
    )


def persist_booking_audit(booking_id, action):
    try:
        with db() as conn:
            audit_booking(conn, booking_id, action)
    except Exception:
        # Audit runs after commit; never undo a saved booking.
        pass


def ensure_booking_audit_baseline(conn):
    ensure_booking_audit_table(conn)
    rows = conn.execute(
        """
        SELECT id
        FROM bookings
        WHERE id NOT IN (SELECT DISTINCT bookingId FROM booking_audit_log)
        """
    ).fetchall()
    for row in rows:
        audit_booking(conn, row["id"], "baseline")


def parse_date(value):
    return datetime.strptime(value, "%Y-%m-%d").date()


def app_today():
    return datetime.now(APP_TZ).date()


def normalize_date(value):
    raw = str(value or "").strip()
    if not raw:
        return ""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date().isoformat()
        except ValueError:
            return ""
    match = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2}|\d{4}))?", raw)
    if match:
        day = int(match.group(1))
        month = int(match.group(2))
        year_value = match.group(3)
        year = app_today().year if not year_value else int(year_value)
        if year < 100:
            year += 2000
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return ""
    return ""


def normalize_time(value):
    raw = str(value or "").strip()
    if not raw:
        return ""
    match = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", raw)
    if match:
        return f"{int(match.group(1)):02d}:{match.group(2)}"
    match = re.fullmatch(r"(\d{1,2})([0-5]\d)", raw)
    if match and int(match.group(1)) <= 23:
        return f"{int(match.group(1)):02d}:{match.group(2)}"
    return raw


def normalize_number(value, default=0):
    raw = str(value if value is not None else "").strip().replace(",", ".")
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def normalize_int(value, default=0):
    try:
        return int(normalize_number(value, default))
    except (TypeError, ValueError):
        return default


def repair_booking_dates(conn):
    rows = conn.execute("SELECT id, date, pickupTime, travelTime, status FROM bookings").fetchall()
    for row in rows:
        fixed_date = normalize_date(row["date"])
        fixed_pickup = normalize_time(row["pickupTime"])
        fixed_travel = normalize_time(row["travelTime"])
        fixed_status = row["status"] if row["status"] in BOOKING_STATUSES else "Pending"
        updates = {}
        if fixed_date and fixed_date != row["date"]:
            updates["date"] = fixed_date
        if fixed_pickup and fixed_pickup != row["pickupTime"]:
            updates["pickupTime"] = fixed_pickup
        if fixed_travel != (row["travelTime"] or ""):
            updates["travelTime"] = fixed_travel
        if fixed_status != row["status"]:
            updates["status"] = fixed_status
        if updates:
            assignments = ", ".join([f"{key}=:{key}" for key in updates])
            conn.execute(
                f"UPDATE bookings SET {assignments}, updatedAt=CURRENT_TIMESTAMP WHERE id=:id",
                {**updates, "id": row["id"]},
            )


def month_bounds(month):
    start = datetime.strptime(month, "%Y-%m").date().replace(day=1)
    next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return start.isoformat(), (next_month - timedelta(days=1)).isoformat()


def normalize_booking(data):
    price = normalize_number(data.get("price"), 0)
    vehicle = str(data.get("vehicle") or "OPEL VIVARO")
    driver = str(data.get("driver") or "").strip()
    payment_method = str(data.get("paymentMethod") or "Μετρητά")
    booking_source = str(data.get("bookingSource") or "PRIVATE").strip().upper()
    tax_status = str(data.get("taxStatus") or "Μη Καταχωρημένο").strip()
    status = str(data.get("status") or "Pending").strip()
    return {
        "date": normalize_date(data.get("date")),
        "pickupTime": normalize_time(data.get("pickupTime")),
        "travelTime": normalize_time(data.get("travelTime")),
        "flightNumber": str(data.get("flightNumber") or "").strip().upper(),
        "customerName": str(data.get("customerName") or "").strip(),
        "phone": str(data.get("phone") or "").strip(),
        "hotel": str(data.get("hotel") or "").strip(),
        "route": str(data.get("route") or "").strip(),
        "passengers": normalize_int(data.get("passengers"), 1),
        "luggage": normalize_int(data.get("luggage"), 0),
        "price": price,
        "paymentStatus": str(data.get("paymentStatus") or "Unpaid"),
        "paymentMethod": payment_method if payment_method in PAYMENT_METHODS else "Μετρητά",
        "vehicle": vehicle,
        "driver": driver,
        "bookingSource": booking_source or "PRIVATE",
        "taxStatus": tax_status if tax_status in TAX_STATUSES else "Μη Καταχωρημένο",
        "status": status if status in BOOKING_STATUSES else "Pending",
        "notes": str(data.get("notes") or "").strip(),
    }


def normalize_expense(data):
    payment_method = str(data.get("paymentMethod") or "Μετρητά")
    return {
        "date": normalize_date(data.get("date")),
        "category": str(data.get("category") or "Καύσιμα").strip(),
        "description": str(data.get("description") or "").strip(),
        "amount": normalize_number(data.get("amount"), 0),
        "paymentMethod": payment_method if payment_method in PAYMENT_METHODS else "Μετρητά",
        "vehicle": str(data.get("vehicle") or "").strip(),
        "notes": str(data.get("notes") or "").strip(),
    }


def booking_error(booking):
    if not booking["date"]:
        return "Η ημερομηνία είναι υποχρεωτική και πρέπει να είναι σε μορφή YYYY-MM-DD ή ΗΗ/ΜΜ/ΕΕΕΕ."
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
        if self.path.startswith("/api/options/"):
            return self.create_option()
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
        if parsed.path == "/api/options":
            return self.options()
        if parsed.path == "/api/admin/debug":
            return self.admin_debug(parsed)
        if parsed.path.startswith("/api/"):
            return self.send_error(404)
        return super().do_GET()

    def do_PUT(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/bookings/"):
            if parsed.path.endswith("/tax-status"):
                return self.update_booking_tax_status(parsed)
            if parsed.path.endswith("/status"):
                return self.update_booking_status(parsed)
            return self.update_booking(parsed)
        if parsed.path.startswith("/api/expenses/"):
            return self.update_expense(parsed)
        if parsed.path.startswith("/api/options/"):
            return self.update_option(parsed)
        return self.send_error(404)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/bookings/"):
            return self.delete_row("bookings", parsed)
        if parsed.path.startswith("/api/expenses/"):
            return self.delete_row("expenses", parsed)
        if parsed.path.startswith("/api/options/"):
            return self.delete_option(parsed)
        return self.send_error(404)

    def create_booking(self):
        if not self.authorized():
            return self.send_json({"error": "Unauthorized"}, 401)
        booking = normalize_booking(self.read_json())
        if booking["status"] == "Completed":
            booking["status"] = "Pending"
        error = booking_error(booking)
        if error:
            return self.send_json({"error": error}, 400)
        keys = ", ".join(booking.keys())
        placeholders = ", ".join([f":{key}" for key in booking])
        backup_database("booking-create")
        with db() as conn:
            cur = conn.execute(f"INSERT INTO bookings ({keys}) VALUES ({placeholders})", booking)
            saved = conn.execute("SELECT * FROM bookings WHERE id = ?", (cur.lastrowid,)).fetchone()
        saved_booking = row_to_dict(saved)
        if not saved_booking or not saved_booking.get("id"):
            return self.send_json({"error": "Η κράτηση δεν επιβεβαιώθηκε στη βάση."}, 500)
        persist_booking_audit(saved_booking["id"], "created")
        return self.send_json(saved_booking, 201)

    def list_bookings(self, parsed):
        if not self.authorized():
            return self.send_json({"error": "Unauthorized"}, 401)
        query = parse_qs(parsed.query)
        history = query.get("history", ["0"])[0] == "1"
        where = []
        params = {}
        has_date_filter = False
        if query.get("date", [""])[0]:
            where.append("date = :date")
            params["date"] = normalize_date(query["date"][0])
            has_date_filter = True
        if query.get("start", [""])[0] and query.get("end", [""])[0]:
            where.append("date BETWEEN :start AND :end")
            params["start"] = normalize_date(query["start"][0])
            params["end"] = normalize_date(query["end"][0])
            has_date_filter = True
        if query.get("q", [""])[0]:
            where.append("(CAST(id AS TEXT) LIKE :q OR customerName LIKE :q OR phone LIKE :q OR hotel LIKE :q OR date LIKE :q OR pickupTime LIKE :q OR flightNumber LIKE :q OR route LIKE :q)")
            params["q"] = f"%{query['q'][0]}%"
        if query.get("tax", [""])[0] in TAX_STATUSES:
            where.append("taxStatus = :tax")
            params["tax"] = query["tax"][0]
        if history:
            where.append("status = 'Completed'")
        else:
            where.append("status NOT IN ('Completed', 'Cancelled')")
            if not has_date_filter:
                where.append("date >= :today")
                params["today"] = app_today().isoformat()
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
        backup_database("booking-update")
        with db() as conn:
            existing = conn.execute("SELECT status FROM bookings WHERE id = ?", (booking_id,)).fetchone()
            if not existing:
                return self.send_json({"error": "Δεν βρέθηκε η κράτηση."}, 404)
            if booking["status"] == "Completed" and existing["status"] != "Completed":
                booking["status"] = existing["status"] if existing["status"] in BOOKING_STATUSES else "Pending"
            cur = conn.execute(
                f"UPDATE bookings SET {assignments}, updatedAt=CURRENT_TIMESTAMP WHERE id=:id",
                {**booking, "id": booking_id},
            )
            if cur.rowcount == 0:
                return self.send_json({"error": "Δεν βρέθηκε η κράτηση."}, 404)
            saved = conn.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()
        persist_booking_audit(booking_id, "updated")
        return self.send_json(row_to_dict(saved))

    def totals(self, parsed):
        if not self.authorized():
            return self.send_json({"error": "Unauthorized"}, 401)
        query = parse_qs(parsed.query)
        start = normalize_date(query.get("start", [""])[0])
        end = normalize_date(query.get("end", [""])[0])
        with db() as conn:
            row = conn.execute(
                """
                SELECT
                  COUNT(*) AS bookings,
                  COALESCE(SUM(CASE WHEN paymentMethod = 'Μετρητά' THEN price ELSE 0 END), 0) AS cash,
                  COALESCE(SUM(CASE WHEN paymentMethod IN ('Κάρτα', 'Πίστωση') THEN price ELSE 0 END), 0) AS card,
                  COALESCE(SUM(price), 0) AS total
                FROM bookings
                WHERE date BETWEEN ? AND ?
                  AND status NOT IN ('Completed', 'Cancelled')
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
        backup_database("expense-create")
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
        backup_database("expense-update")
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
                    SELECT date, description, category, amount, vehicle
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
                    payment_method = booking["paymentMethod"] or "Μετρητά"
                    is_cash = payment_method == "Μετρητά"
                    is_card = payment_method in ("Κάρτα", "Πίστωση")
                    is_credit = payment_method == "Πίστωση"
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
                        "cash": price if is_cash else 0,
                        "card": price if is_card else 0,
                        "expenses": 0,
                        "description": "Πίστωση" if is_credit else "",
                    })
                for expense in expenses:
                    amount = float(expense["amount"] or 0)
                    expense_total += amount
                    description = expense["description"] or expense["category"] or ""
                    if expense["vehicle"]:
                        description = f"{description} · {expense['vehicle']}" if description else expense["vehicle"]
                    entries.append({
                        "type": "expense",
                        "date": expense["date"],
                        "time": "",
                        "route": "",
                        "customer": "",
                        "cash": 0,
                        "card": 0,
                        "expenses": amount,
                        "description": description,
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

    def option_table(self, kind):
        return {
            "vehicles": "vehicles",
            "drivers": "drivers",
            "sources": "booking_sources",
        }.get(kind)

    def options(self):
        if not self.authorized():
            return self.send_json({"error": "Unauthorized"}, 401)
        with db() as conn:
            return self.send_json({
                "vehicles": active_option_names(conn, "vehicles"),
                "drivers": active_option_names(conn, "drivers"),
                "bookingSources": active_option_names(conn, "booking_sources"),
                "optionDetails": {
                    "vehicles": active_option_rows(conn, "vehicles"),
                    "drivers": active_option_rows(conn, "drivers"),
                    "sources": active_option_rows(conn, "booking_sources"),
                },
                "paymentMethods": ["Μετρητά", "Κάρτα", "Πίστωση"],
                "taxStatuses": ["Καταχωρημένο", "Μη Καταχωρημένο"],
            })

    def create_option(self):
        if not self.authorized():
            return self.send_json({"error": "Unauthorized"}, 401)
        kind = self.path.rsplit("/", 1)[-1]
        table = self.option_table(kind)
        if not table:
            return self.send_json({"error": "Άγνωστη επιλογή."}, 404)
        name = str(self.read_json().get("name") or "").strip()
        if not name:
            return self.send_json({"error": "Το όνομα είναι υποχρεωτικό."}, 400)
        if kind == "sources":
            name = name.upper()
        backup_database(f"option-create-{kind}")
        with db() as conn:
            upsert_option(conn, table, name)
            saved = conn.execute(f"SELECT * FROM {table} WHERE name = ?", (name,)).fetchone()
        return self.send_json(row_to_dict(saved), 201)

    def update_option(self, parsed):
        if not self.authorized():
            return self.send_json({"error": "Unauthorized"}, 401)
        parts = parsed.path.strip("/").split("/")
        if len(parts) != 4:
            return self.send_json({"error": "Λάθος διεύθυνση επιλογής."}, 404)
        _, _, kind, item_id = parts
        table = self.option_table(kind)
        if not table:
            return self.send_json({"error": "Άγνωστη επιλογή."}, 404)
        name = str(self.read_json().get("name") or "").strip()
        if not name:
            return self.send_json({"error": "Το όνομα είναι υποχρεωτικό."}, 400)
        if kind == "sources":
            name = name.upper()
        backup_database(f"option-update-{kind}")
        with db() as conn:
            cur = conn.execute(
                f"UPDATE {table} SET name = ?, active = 1, updatedAt = CURRENT_TIMESTAMP WHERE id = ?",
                (name, item_id),
            )
            if cur.rowcount == 0:
                return self.send_json({"error": "Δεν βρέθηκε η επιλογή."}, 404)
            saved = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (item_id,)).fetchone()
        return self.send_json(row_to_dict(saved))

    def delete_option(self, parsed):
        if not self.authorized():
            return self.send_json({"error": "Unauthorized"}, 401)
        parts = parsed.path.strip("/").split("/")
        if len(parts) != 4:
            return self.send_json({"error": "Λάθος διεύθυνση επιλογής."}, 404)
        _, _, kind, item_id = parts
        table = self.option_table(kind)
        if not table:
            return self.send_json({"error": "Άγνωστη επιλογή."}, 404)
        backup_database(f"option-delete-{kind}")
        with db() as conn:
            cur = conn.execute(
                f"UPDATE {table} SET active = 0, updatedAt = CURRENT_TIMESTAMP WHERE id = ?",
                (item_id,),
            )
        if cur.rowcount == 0:
            return self.send_json({"error": "Δεν βρέθηκε η επιλογή."}, 404)
        self.send_response(204)
        self.end_headers()

    def update_booking_tax_status(self, parsed):
        if not self.authorized():
            return self.send_json({"error": "Unauthorized"}, 401)
        booking_id = parsed.path.strip("/").split("/")[-2]
        tax_status = str(self.read_json().get("taxStatus") or "").strip()
        if tax_status not in TAX_STATUSES:
            return self.send_json({"error": "Λάθος κατάσταση ΑΑΔΕ."}, 400)
        backup_database("booking-tax-status")
        with db() as conn:
            cur = conn.execute(
                "UPDATE bookings SET taxStatus = ?, updatedAt = CURRENT_TIMESTAMP WHERE id = ?",
                (tax_status, booking_id),
            )
            if cur.rowcount == 0:
                return self.send_json({"error": "Δεν βρέθηκε η κράτηση."}, 404)
            saved = conn.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()
            audit_booking(conn, booking_id, "tax_status_updated")
        return self.send_json(row_to_dict(saved))

    def update_booking_status(self, parsed):
        if not self.authorized():
            return self.send_json({"error": "Unauthorized"}, 401)
        booking_id = parsed.path.strip("/").split("/")[-2]
        status = str(self.read_json().get("status") or "").strip()
        if status not in BOOKING_STATUSES:
            return self.send_json({"error": "Λάθος κατάσταση κράτησης."}, 400)
        backup_database("booking-status")
        with db() as conn:
            cur = conn.execute(
                "UPDATE bookings SET status = ?, updatedAt = CURRENT_TIMESTAMP WHERE id = ?",
                (status, booking_id),
            )
            if cur.rowcount == 0:
                return self.send_json({"error": "Δεν βρέθηκε η κράτηση."}, 404)
            saved = conn.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()
            audit_booking(conn, booking_id, "status_updated")
        return self.send_json(row_to_dict(saved))

    def admin_debug(self, parsed):
        if not self.authorized():
            return self.send_json({"error": "Unauthorized"}, 401)
        query = parse_qs(parsed.query)
        today = app_today().isoformat()
        start = normalize_date(query.get("start", [""])[0]) or today
        end = normalize_date(query.get("end", [""])[0]) or "9999-12-31"
        q = query.get("q", [""])[0].strip()
        tax = query.get("tax", [""])[0]
        driver = query.get("driver", [""])[0].strip()
        visible_where = ["date BETWEEN :start AND :end", "status NOT IN ('Completed', 'Cancelled')"]
        active_range_where = list(visible_where)
        params = {"start": start, "end": end}
        if q:
            visible_where.append("(CAST(id AS TEXT) LIKE :q OR customerName LIKE :q OR phone LIKE :q OR hotel LIKE :q OR date LIKE :q OR pickupTime LIKE :q OR flightNumber LIKE :q OR route LIKE :q)")
            params["q"] = f"%{q}%"
        if tax in TAX_STATUSES:
            visible_where.append("taxStatus = :tax")
            params["tax"] = tax
        if driver:
            visible_where.append("driver = :driver")
            params["driver"] = driver
        visible_sql = "SELECT COUNT(*) AS total FROM bookings WHERE " + " AND ".join(visible_where)
        active_range_sql = "SELECT COUNT(*) AS total FROM bookings WHERE " + " AND ".join(active_range_where)
        with db() as conn:
            db_rows = conn.execute("SELECT COUNT(*) AS total FROM bookings").fetchone()["total"]
            upcoming = conn.execute(
                "SELECT COUNT(*) AS total FROM bookings WHERE date >= ? AND status NOT IN ('Completed', 'Cancelled')",
                (today,),
            ).fetchone()["total"]
            completed = conn.execute("SELECT COUNT(*) AS total FROM bookings WHERE status = 'Completed'").fetchone()["total"]
            cancelled = conn.execute("SELECT COUNT(*) AS total FROM bookings WHERE status = 'Cancelled'").fetchone()["total"]
            active_in_range = conn.execute(active_range_sql, {"start": start, "end": end}).fetchone()["total"]
            visible = conn.execute(visible_sql, params).fetchone()["total"]
            audit_rows = conn.execute("SELECT COUNT(*) AS total FROM booking_audit_log").fetchone()["total"]
            matches = []
            if q:
                match_where = ["(CAST(id AS TEXT) LIKE :q OR customerName LIKE :q OR phone LIKE :q OR hotel LIKE :q OR date LIKE :q OR pickupTime LIKE :q OR flightNumber LIKE :q OR route LIKE :q)"]
                match_params = {"q": f"%{q}%"}
                if tax in TAX_STATUSES:
                    match_where.append("taxStatus = :tax")
                    match_params["tax"] = tax
                if driver:
                    match_where.append("driver = :driver")
                    match_params["driver"] = driver
                matches = [
                    row_to_dict(row)
                    for row in conn.execute(
                        "SELECT id, date, pickupTime, customerName, route, status, driver, taxStatus, updatedAt FROM bookings WHERE "
                        + " AND ".join(match_where)
                        + " ORDER BY date DESC, pickupTime DESC LIMIT 20",
                        match_params,
                    ).fetchall()
                ]
        return self.send_json({
            "totalBookings": db_rows,
            "upcoming": upcoming,
            "completed": completed,
            "cancelled": cancelled,
            "activeInCurrentRange": active_in_range,
            "visibleWithCurrentFilters": visible,
            "hiddenByFilters": max(active_in_range - visible, 0),
            "databaseRowsCount": db_rows,
            "auditRowsCount": audit_rows,
            "matches": matches,
            "range": {"start": start, "end": end},
        })

    def delete_row(self, table, parsed):
        if not self.authorized():
            return self.send_json({"error": "Unauthorized"}, 401)
        item_id = parsed.path.rsplit("/", 1)[-1]
        backup_database(f"{table}-delete")
        with db() as conn:
            if table == "bookings":
                # Store full snapshot in audit log before permanent deletion
                audit_booking(conn, item_id, "deleted")
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
