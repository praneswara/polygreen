import os
import datetime as dt
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, redirect, url_for, flash, session, abort, send_file
from functools import wraps
from dotenv import load_dotenv
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont

pdfmetrics.registerFont(UnicodeCIDFont("HYSMyeongJo-Medium"))
pdfmetrics.registerFont(UnicodeCIDFont("HYGothic-Medium"))


load_dotenv()

admin_app = Flask(__name__, template_folder="templates")
admin_app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev")


def get_db_connection():
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        raise ValueError("DATABASE_URL not set in .env")

    # psycopg2 requires "postgresql://" not "postgres://"
    if dsn.startswith("postgres://"):
        dsn = dsn.replace("postgres://", "postgresql://", 1)

    # connect using the URL
    conn = psycopg2.connect(dsn, cursor_factory=RealDictCursor)
    return conn

def serialize_row(row):
    """Convert datetime/date fields in a RealDict row to ISO strings for templates/JSON."""
    if not row:
        return row
    for k, v in list(row.items()):
        if isinstance(v, (dt.datetime, dt.date)):
            row[k] = v.isoformat()
    return row

def generate_pdf(title, lines):
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)

    # Use Korean-safe font
    p.setFont("HYGothic-Medium", 16)
    y = 750
    p.drawString(50, y, title)

    p.setFont("HYGothic-Medium", 12)
    y -= 40

    for line in lines:
        p.drawString(50, y, str(line))
        y -= 20

        if y < 50:
            p.showPage()
            p.setFont("HYGothic-Medium", 12)
            y = 750

    p.save()
    buffer.seek(0)
    return buffer


# ---------------- Auth Decorator ----------------
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated_function

@admin_app.route('/')
def home():
    return render_template("admin/index.html")
    
# ---------------- Login ----------------
@admin_app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        # simple fixed credential check (keep as-is)
        if username == "polygreen" and password == "poly123":
            session["admin_logged_in"] = True
            return redirect(url_for("admin_dashboard"))
        else:
            flash("Invalid credentials", "error")
    return render_template("admin/login.html")


# ---------------- Dashboard ----------------
@admin_app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) AS total_users FROM users;")
        total_users = cur.fetchone()["total_users"]

        cur.execute("SELECT COUNT(*) AS total_machines FROM machines;")
        total_machines = cur.fetchone()["total_machines"]

        cur.execute("SELECT COUNT(*) AS total_transactions FROM transactions;")
        total_transactions = cur.fetchone()["total_transactions"]

    except Exception as e:
        # Debugging help: flash or log the DB error
        flash(f"Database error: {e}", "danger")
        total_users = total_machines = total_transactions = 0

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

    stats = {
        "total_users": total_users,
        "total_machines": total_machines,
        "total_transactions": total_transactions,
    }
    return render_template("admin/dashboard.html", stats=stats)



# ---------------- Users ----------------
@admin_app.route("/admin/users")
@admin_required
def admin_users():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT user_id, name, mobile, points, bottles, created_at
            FROM users
            ORDER BY created_at DESC;
        """)
        users = cur.fetchall()
        users = [serialize_row(u) for u in users]
    finally:
        cur.close()
        conn.close()

    return render_template("admin/users.html", users=users)


@admin_app.route("/admin/users/<string:user_id>")
@admin_required
def admin_user_detail(user_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT user_id, name, mobile, points, bottles, created_at
            FROM users WHERE user_id = %s;
        """, (user_id,))
        user = cur.fetchone()
        if not user:
            abort(404)

        cur.execute("""
            SELECT id, type, points, bottles, machine_id, brand_id, created_at
            FROM transactions
            WHERE user_id = %s
            ORDER BY created_at DESC;
        """, (user_id,))
        transactions = cur.fetchall()
        transactions = [serialize_row(t) for t in transactions]
        user = serialize_row(user)
    finally:
        cur.close()
        conn.close()

    return render_template("admin/user_detail.html", user=user, transactions=transactions)


# ---------------- Machines ----------------
@admin_app.route("/admin/machines")
@admin_required
def admin_machines():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, machine_id, name, city, lat, lng, current_bottles, max_capacity, total_bottles, is_full, last_emptied, created_at
            FROM machines
            ORDER BY id;
        """)
        machines = cur.fetchall()
        machines = [serialize_row(m) for m in machines]
    finally:
        cur.close()
        conn.close()

    return render_template("admin/machines.html", machines=machines)


@admin_app.route("/admin/machines/<string:machine_id>")
@admin_required
def admin_machine_detail(machine_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT id, machine_id, name, city, lat, lng, current_bottles, max_capacity, total_bottles, is_full, last_emptied, created_at
            FROM machines WHERE machine_id = %s;
        """, (machine_id,))
        machine = cur.fetchone()
        if not machine:
            abort(404)

        cur.execute("""
            SELECT id, user_id, type, points, bottles, machine_id, created_at
            FROM transactions
            WHERE machine_id = %s
            ORDER BY created_at DESC;
        """, (machine["machine_id"],))
        transactions = cur.fetchall()
        transactions = [serialize_row(t) for t in transactions]
        machine = serialize_row(machine)
    finally:
        cur.close()
        conn.close()

    fill_percentage = 0
    try:
        max_cap = machine.get("max_capacity") or 0
        current = machine.get("current_bottles") or 0
        fill_percentage = (current / max_cap) * 100 if max_cap else 0
    except Exception:
        fill_percentage = 0

    return render_template(
        "admin/machine_detail.html",
        machine=machine,
        transactions=transactions,
        fill_percentage=fill_percentage
    )

@admin_app.route("/admin/users/report")
@admin_required
def admin_users_pdf():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT user_id, name, mobile, points, bottles, created_at
        FROM users ORDER BY created_at DESC;
    """)
    rows = cur.fetchall()

    cur.close()
    conn.close()

    lines = []
    for u in rows:
        lines.append(
            f"{u['user_id']} | {u['name']} | {u['mobile']} | Points:{u['points']} | Bottles:{u['bottles']}"
        )

    pdf = generate_pdf("Users Report", lines)
    return send_file(pdf, as_attachment=True, download_name="users_report.pdf",
                     mimetype="application/pdf")

@admin_app.route("/admin/users/<string:user_id>/report")
@admin_required
def admin_user_detail_pdf(user_id):
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM users WHERE user_id=%s;", (user_id,))
    user = cur.fetchone()
    if not user:
        abort(404)

    cur.execute("""
        SELECT type, points, bottles, machine_id, created_at
        FROM transactions WHERE user_id=%s ORDER BY created_at DESC;
    """, (user_id,))
    transactions = cur.fetchall()

    cur.close()
    conn.close()

    lines = [
        f"USER REPORT",
        f"User ID: {user['user_id']}",
        f"Name: {user['name']}",
        f"Mobile: {user['mobile']}",
        f"Points: {user['points']}",
        f"Bottles: {user['bottles']}",
        "",
        "TRANSACTIONS:"
    ]

    for t in transactions:
        lines.append(
            f"{t['created_at']} | {t['type']} | +{t['points']}pts | {t['bottles']} bottles | Machine:{t['machine_id']}"
        )

    pdf = generate_pdf(f"User Report - {user['name']}", lines)
    return send_file(pdf, as_attachment=True,
                     download_name=f"{user_id}_report.pdf",
                     mimetype="application/pdf")
    
@admin_app.route("/admin/machines/<string:machine_id>/report")
@admin_required
def admin_machine_detail_pdf(machine_id):
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM machines WHERE machine_id=%s;", (machine_id,))
    machine = cur.fetchone()
    if not machine:
        abort(404)

    cur.execute("""
        SELECT user_id, type, points, bottles, created_at
        FROM transactions WHERE machine_id=%s ORDER BY created_at DESC;
    """, (machine_id,))
    transactions = cur.fetchall()

    cur.close()
    conn.close()

    lines = [
        f"Machine ID: {machine['machine_id']}",
        f"Name: {machine['name']}",
        f"City: {machine['city']}",
        f"Bottles: {machine['current_bottles']} / {machine['max_capacity']}",
        "",
        "TRANSACTIONS:"
    ]

    for t in transactions:
        lines.append(
            f"{t['created_at']} | User:{t['user_id']} | {t['type']} | +{t['points']}pts | {t['bottles']} bottles"
        )

    pdf = generate_pdf(f"Machine Report - {machine_id}", lines)
    return send_file(pdf, as_attachment=True,
                     download_name=f"{machine_id}_report.pdf",
                     mimetype="application/pdf")


@admin_app.route("/admin/machines/report")
@admin_required
def admin_machines_pdf():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT machine_id, name, city, current_bottles, max_capacity
        FROM machines ORDER BY id;
    """)
    rows = cur.fetchall()

    cur.close()
    conn.close()

    lines = []
    for m in rows:
        lines.append(
            f"{m['machine_id']} | {m['name']} | {m['city']} | {m['current_bottles']}/{m['max_capacity']} bottles"
        )

    pdf = generate_pdf("Machines Report", lines)
    return send_file(pdf, as_attachment=True,
                     download_name="machines_report.pdf",
                     mimetype="application/pdf")


# ---------------- Empty Machine ----------------
@admin_app.route("/admin/machine/<string:machine_id>/empty", methods=["POST"])
@admin_required
def admin_empty_machine(machine_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # Get machine first
        cur.execute("SELECT id, machine_id, name, current_bottles FROM machines WHERE machine_id = %s;", (machine_id,))
        machine = cur.fetchone()
        if not machine:
            abort(404)

        previous_count = machine.get("current_bottles") or 0

        cur.execute("""
            UPDATE machines
            SET current_bottles = 0,
                is_full = FALSE,
                last_emptied = NOW()
            WHERE machine_id = %s;
        """, (machine_id,))
        conn.commit()
    finally:
        cur.close()
        conn.close()

    flash(f"Machine '{machine.get('name')}' emptied successfully! Bottles collected: {previous_count}", "success")
    return redirect(url_for("admin_machine_detail", machine_id=machine_id))


# ---------------- ADD Machine ----------------
@admin_app.route("/admin/machines/add", methods=["GET", "POST"])
@admin_required
def admin_add_machine():
    if request.method == "POST":
        machine_id = request.form.get("machine_id")
        name = request.form.get("name")
        city = request.form.get("city")
        lat = request.form.get("lat", type=float)
        lng = request.form.get("lng", type=float)
        max_capacity = request.form.get("max_capacity", type=int)

        try:
            conn = get_db_connection()
            cur = conn.cursor()
            # check uniqueness
            cur.execute("SELECT 1 FROM machines WHERE machine_id = %s;", (machine_id,))
            if cur.fetchone():
                flash(f"Machine ID '{machine_id}' already exists.", "danger")
                return redirect(url_for("admin_add_machine"))

            cur.execute("""
                INSERT INTO machines (machine_id, name, city, lat, lng, max_capacity, current_bottles, total_bottles, is_full, created_at)
                VALUES (%s,%s,%s,%s,%s,%s,0,0,FALSE,NOW());
            """, (machine_id, name, city, lat, lng, max_capacity))
            conn.commit()
        finally:
            cur.close()
            conn.close()

        flash(f"Machine '{name}' added successfully!", "success")
        return redirect(url_for("admin_machines"))

    return render_template("admin/add_machine.html")

@admin_app.route("/admin/transactions/report", methods=["POST"])
@admin_required
def export_filtered_transactions():

    pdfmetrics.registerFont(UnicodeCIDFont("HeiseiMin-W3"))

    data = request.get_json().get("data", [])

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    styles["Normal"].fontName = "HeiseiMin-W3"
    styles["Heading1"].fontName = "HeiseiMin-W3"

    elements = []
    elements.append(Paragraph("필터링된 거래 보고서", styles["Heading1"]))
    elements.append(Spacer(1, 12))

    table_data = [["ID", "User", "Type", "Points", "Bottles", "Machine", "Date"]]

    for t in data:
        table_data.append([
            t["id"], t["user_id"], t["type"], t["points"],
            t["bottles"], t["machine_id"], t["created_at"]
        ])

    table = Table(table_data, repeatRows=1)
    table.setStyle(TableStyle([
        ("FONTNAME", (0,0), (-1,-1), "HeiseiMin-W3"),
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#006d71")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("ALIGN", (0,0), (-1,-1), "CENTER"),
        ("GRID", (0,0), (-1,-1), 0.7, colors.black)
    ]))

    elements.append(table)
    doc.build(elements)

    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name="filtered_transactions.pdf",
        mimetype="application/pdf"
    )


# ---------------- Logout ----------------
@admin_app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("admin_login"))


if __name__ == "__main__":
    # Quick DB connection check
    try:
        c = get_db_connection()
        c.close()
        print("✅ Connected to Neon/Postgres successfully")
    except Exception as e:
        print("❌ DB connection failed:", e)

    admin_app.run(debug=True, port=5001)









