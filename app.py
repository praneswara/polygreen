import os
import datetime as dt
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, request, jsonify, abort
from flask_cors import CORS
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from dotenv import load_dotenv
from passlib.hash import bcrypt

# Load env
load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev")
app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "devjwt")

# JWT Configuration
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = dt.timedelta(hours=24)
app.config["JWT_ALGORITHM"] = "HS256"

CORS(app)
jwt = JWTManager(app)

# ---------------- DB CONNECTION ----------------
def get_db():
    uri = os.getenv("DATABASE_URL")
    if not uri:
        raise ValueError("DATABASE_URL is not set")
    # psycopg2 connection
    conn = psycopg2.connect(uri, cursor_factory=RealDictCursor)
    return conn

# Helper: convert datetime fields to isoformat for JSON
def serialize_row(row):
    if not row:
        return row
    for k, v in list(row.items()):
        if isinstance(v, (dt.datetime, dt.date)):
            row[k] = v.isoformat()
    return row

# ------------- Init & seeds --------------
def init_db():
    """Seed initial data if tables exist and are empty. Will not create tables."""
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                # Seed reward_brand
                cur.execute("SELECT COUNT(*) AS cnt FROM reward_brand")
                cnt = cur.fetchone()["cnt"]
                if cnt == 0:
                    cur.execute("""
                        INSERT INTO reward_brand (name, min_points, active)
                        VALUES
                        (%s, %s, %s),
                        (%s, %s, %s),
                        (%s, %s, %s)
                    """, (
                        "Amazon", 200, True,
                        "Flipkart", 150, True,
                        "Swiggy", 100, True
                    ))

                # Seed machines
                cur.execute("SELECT COUNT(*) AS cnt FROM machines")
                cnt = cur.fetchone()["cnt"]
                if cnt == 0:
                    cur.execute("""
                        INSERT INTO machines (machine_id, name, city, lat, lng, current_bottles, max_capacity, total_bottles, is_full)
                        VALUES
                        (%s,%s,%s,%s,%s,%s,%s,%s,%s),
                        (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """, (
                        "M001", "RVM Station A", "jim,korea", 10.823879417459477, 78.70024710440879, 0, 100, 0, False,
                        "M002", "RVM Station B", "jim,korea", 12.9352, 77.6245, 0, 100, 0, False
                    ))

                # Seed default user (try to insert explicitly with id=0 like your original; if fails, insert without id)
                cur.execute("SELECT COUNT(*) AS cnt FROM users")
                cnt = cur.fetchone()["cnt"]
                if cnt == 0:
                    try:
                        cur.execute("""
                            INSERT INTO users (id, name, mobile, password_hash, points, bottles)
                            VALUES (%s,%s,%s,%s,%s,%s)
                        """, (
                            0,
                            "BUSANTECH",
                            1234567890,
                            "$2b$12$MyPFgq8vz.EiUK2PlqG3BeWzTjhg9.f8y9W60tpfZ4aQEQ9F6JcBW",
                            100,
                            10
                        ))
                    except Exception:
                        # fallback: insert without id
                        cur.execute("""
                            INSERT INTO users (name, mobile, password_hash, points, bottles)
                            VALUES (%s,%s,%s,%s,%s)
                        """, (
                            "BUSANTECH",
                            1234567890,
                            "$2b$12$MyPFgq8vz.EiUK2PlqG3BeWzTjhg9.f8y9W60tpfZ4aQEQ9F6JcBW",
                            100,
                            10
                        ))
            conn.commit()
    except psycopg2.errors.UndefinedTable:
        # Tables don't exist yet — user should create them manually in Neon console
        print("init_db: tables not found. Create tables in Neon console before running init_db().")
    except Exception as e:
        print("init_db: unexpected error:", str(e))


# -------------- Helpers ------------------
def get_user_or_404(uid):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE id=%s", (uid,))
            user = cur.fetchone()
    if not user:
        abort(404, description="User not found")
    return user

# -------------- Routes -------------------
@app.route("/api", methods=["GET"])
def api():
    return jsonify(message="WELCOME TO POLYGREEN"), 201

# ---------------- Auth -------------------
@app.route("/api/auth/register", methods=["POST"])
def register():
    data = request.get_json() or {}
    name = data.get("name")
    mobile = data.get("mobile")
    password = data.get("password")
    if not (name and mobile and password):
        return jsonify(message="Missing fields"), 400

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE mobile=%s", (mobile,))
            if cur.fetchone():
                return jsonify(message="mobile already used"), 400
            password = password[:72]
            password_hash = bcrypt.hash(password)
            cur.execute("""
                INSERT INTO users (name, mobile, password_hash, points, bottles, created_at)
                VALUES (%s,%s,%s,%s,%s, NOW())
                RETURNING id
            """, (name, mobile, password_hash, 0, 0))
            new_id = cur.fetchone()["id"]
        conn.commit()

    return jsonify(message="Registered", id=new_id), 201


@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    mobile = data.get("mobile")
    password = data.get("password", "")

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE mobile=%s", (mobile,))
            u = cur.fetchone()

    if not u or not bcrypt.verify(password, u["password_hash"]):
        return jsonify(message="Invalid credentials"), 401

    token = create_access_token(
        identity=str(u["id"]),
        additional_claims={"mobile": u["mobile"], "name": u["name"]}
    )
    return jsonify(
        access_token=token,
        user={"id": u["id"], "name": u["name"], "mobile": u["mobile"], "points": u["points"], "bottles": u["bottles"]}
    )

# --------------- User endpoints -----------
@app.route("/api/users/me", methods=["GET"])
@jwt_required()
def me():
    uid_str = get_jwt_identity()
    uid = int(uid_str)
    u = get_user_or_404(uid)
    u = serialize_row(u)
    return jsonify(
        id=u["id"],
        name=u["name"],
        mobile=u["mobile"],
        points=u["points"],
        bottles=u["bottles"],
        created_at=u.get("created_at")
    )

# ------------- Points & transactions -------
@app.route("/api/points/summary", methods=["GET"])
@jwt_required()
def points_summary():
    uid_str = get_jwt_identity()
    uid = int(uid_str)
    u = get_user_or_404(uid)

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, points, type, created_at
                FROM transactions
                WHERE user_id=%s
                ORDER BY created_at DESC
                LIMIT 5
            """, (u["id"],))
            recent = cur.fetchall()

    recent = [serialize_row(r) for r in recent]
    return jsonify(
        total_points=u["points"],
        recent=[{"id": r["id"], "points": r["points"], "created_at": r["created_at"], "type": r["type"]} for r in recent]
    )

@app.route("/api/transactions", methods=["GET"])
@jwt_required()
def transactions():
    uid_str = get_jwt_identity()
    uid = int(uid_str)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, type, points, brand_id, machine_id, created_at
                FROM transactions
                WHERE user_id=%s
                ORDER BY created_at DESC
            """, (uid,))
            rows = cur.fetchall()
    rows = [serialize_row(r) for r in rows]
    return jsonify(
        items=[{"id": r["id"], "type": r["type"], "points": r["points"], "brand_id": r.get("brand_id"), "machine_id": r.get("machine_id"), "created_at": r["created_at"]} for r in rows]
    )

# --------------- Redeem ------------------
@app.route("/api/redeem/brands", methods=["GET"])
@jwt_required()
def redeem_brands():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, min_points FROM reward_brand WHERE active = TRUE")
            rows = cur.fetchall()
    return jsonify(items=[{"id": r["id"], "name": r["name"], "min_points": r["min_points"]} for r in rows])


@app.route("/api/redeem/request", methods=["POST"])
@jwt_required()
def redeem_request():
    uid_str = get_jwt_identity()
    uid = int(uid_str)
    u = get_user_or_404(uid)

    data = request.get_json() or {}
    brand_id = data.get("brand_id")
    pts = int(data.get("points", 0))

    with get_db() as conn:
        with conn.cursor() as cur:
            # check brand
            cur.execute("SELECT * FROM reward_brand WHERE id=%s", (brand_id,))
            brand = cur.fetchone()
            if not brand or not brand["active"]:
                return jsonify(message="Invalid brand"), 400
            if pts < brand["min_points"]:
                return jsonify(message=f"Minimum required for this brand is {brand['min_points']}"), 400
            # refresh user points
            cur.execute("SELECT points FROM users WHERE id=%s", (u["id"],))
            user_row = cur.fetchone()
            if not user_row or user_row["points"] < pts:
                return jsonify(message="Not enough points"), 400

            # deduct points and insert transaction
            cur.execute("UPDATE users SET points = points - %s WHERE id=%s", (pts, u["id"]))
            cur.execute("""
                INSERT INTO transactions (user_id, type, points, brand_id, created_at)
                VALUES (%s, %s, %s, %s, NOW())
                RETURNING id
            """, (u["id"], "redeem", pts, brand["id"]))
            trx_id = cur.fetchone()["id"]
        conn.commit()

    coupon = f"{brand['name'][:3].upper()}-{u['id']}-{str(trx_id).zfill(4)}"
    return jsonify(message="Redeem successful", coupon=coupon)

# -------------- Machines list -------------
@app.route("/api/machines", methods=["GET"])
@jwt_required()
def list_machines():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM machines")
            rows = cur.fetchall()

    out = []
    for r in rows:
        r = serialize_row(r)
        max_capacity = r.get("max_capacity") or 0
        current = r.get("current_bottles") or 0
        out.append({
            "id": r.get("id"),
            "machine_id": r.get("machine_id"),
            "name": r.get("name"),
            "city": r.get("city"),
            "lat": r.get("lat"),
            "lng": r.get("lng"),
            "current_bottles": current,
            "max_capacity": max_capacity,
            "available_space": max_capacity - current,
            "is_full": bool(r.get("is_full")),
            "last_emptied": r.get("last_emptied")
        })
    return jsonify(items=out)

# -------------- Machine endpoints ----------
# Machine reports earned points (no auth for demo; in prod secure with machine key)

@app.route("/api/user/fetch", methods=["POST"])
def fetchuser():
    data = request.get_json() or {}
    mobile = data.get("mobile")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, mobile FROM users WHERE mobile=%s", (mobile,))
            u = cur.fetchone()
    if not u:
        return jsonify(message="User Not Found & Register in Mobile app"), 401

    return jsonify(
        user_id=u["id"],
        name=u["name"],
        mobile=u["mobile"]
    )


@app.route("/api/machine/insert", methods=["POST"])
def machine_insert():
    data = request.get_json() or {}
    machine_id = data.get("machine_id")
    user_id = data.get("user_id")
    bottle_count = int(data.get("bottle_count", 1))
    points_per_bottle = int(data.get("points_per_bottle", 10))

    if not (machine_id and user_id):
        return jsonify(message="machine_id and user_id required"), 400

    with get_db() as conn:
        with conn.cursor() as cur:
            # Get user
            cur.execute("SELECT * FROM users WHERE id=%s", (user_id,))
            user = cur.fetchone()
            if not user:
                return jsonify(message="User not found"), 404

            # Get machine by machine_id (string identifier)
            cur.execute("SELECT * FROM machines WHERE machine_id=%s", (machine_id,))
            machine = cur.fetchone()
            if not machine:
                return jsonify(message="Machine not found"), 404

            available_space = (machine.get("max_capacity") or 0) - (machine.get("current_bottles") or 0)
            if bottle_count > available_space:
                return jsonify(
                    message=f"Machine is full! Only {available_space} bottles can be accepted",
                    available_space=available_space,
                    requested=bottle_count
                ), 400

            # Determine if machine becomes full
            new_current = (machine.get("current_bottles") or 0) + bottle_count
            will_be_full = new_current >= (machine.get("max_capacity") or 0)

            earned_points = bottle_count * points_per_bottle

            # Update user points & bottles
            cur.execute("UPDATE users SET points = points + %s, bottles = bottles + %s WHERE id=%s",
                        (earned_points, bottle_count, user_id))

            # Update machine counters
            cur.execute("""
                UPDATE machines
                SET current_bottles = current_bottles + %s,
                    total_bottles = total_bottles + %s,
                    is_full = %s
                WHERE machine_id = %s
            """, (bottle_count, bottle_count, will_be_full, machine_id))

            # Create transaction
            cur.execute("""
                INSERT INTO transactions (user_id, type, points, bottles, machine_id, created_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
                RETURNING id
            """, (user_id, "earn", earned_points, bottle_count, machine_id))
            trx_id = cur.fetchone()["id"]
        conn.commit()

    # fetch updated user and machine to return accurate values
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, points, bottles FROM users WHERE id=%s", (user_id,))
            new_user = cur.fetchone()
            cur.execute("SELECT current_bottles, max_capacity, is_full FROM machines WHERE machine_id=%s", (machine_id,))
            new_machine = cur.fetchone()

    return jsonify(
        message="Points and bottles added successfully",
        earned_points=earned_points,
        bottles_added=bottle_count,
        user_total_points=new_user["points"],
        user_total_bottles=new_user["bottles"],
        machine_current_bottles=new_machine["current_bottles"],
        machine_available_space=new_machine["max_capacity"] - new_machine["current_bottles"],
        machine_is_full=bool(new_machine["is_full"])
    )

# -------------- Run -----------------------
if __name__ == "__main__":
    # Ensure app context exists when initializing DB
    try:
        with app.app_context():
            init_db()  # safely create tables and seed
    except Exception as e:
        print("init_db error:", e)
    app.run(host="0.0.0.0", port=5000, debug=True)








# # NEW: API to empty a machine (for maintenance/collection)
# @app.route("/api/machine/<string:machine_id>/empty", methods=["POST"])
# @jwt_required()  # Assuming only authorized personnel can empty machines
# def empty_machine(machine_id):
#     machine = Machine.query.filter_by(machine_id=machine_id).first()
#     if not machine:
#         return jsonify(message="Machine not found"), 404
    
#     previous_count = machine.current_bottles
#     machine.current_bottles = 0
#     machine.is_full = False
#     machine.last_emptied = dt.datetime.utcnow()
    
#     db.session.commit()
    
#     return jsonify(
#         message="Machine emptied successfully",
#         bottles_collected=previous_count,
#         machine_id=machine_id,
#         emptied_at=machine.last_emptied.isoformat()
#     )

# # NEW: API to get machine status
# @app.route("/api/machine/<string:machine_id>/status", methods=["GET"])
# def machine_status(machine_id):
#     machine = Machine.query.filter_by(machine_id=machine_id).first()
#     if not machine:
#         return jsonify(message="Machine not found"), 404
    
#     return jsonify(
#         machine_id=machine.machine_id,
#         name=machine.name,
#         city=machine.city,
#         current_bottles=machine.current_bottles,
#         max_capacity=machine.max_capacity,
#         available_space=machine.max_capacity - machine.current_bottles,
#         is_full=machine.is_full,
#         total_bottles_processed=machine.total_bottles,
#         last_emptied=machine.last_emptied.isoformat() if machine.last_emptied else None
#     )


