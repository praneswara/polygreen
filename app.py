import os
import datetime as dt
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from dotenv import load_dotenv
from models import db, User, Machine, Transaction,RewardBrand

# Load env
load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev")
app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "devjwt")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///rvm.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# JWT Configuration
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = dt.timedelta(hours=24)
app.config["JWT_ALGORITHM"] = "HS256"

CORS(app)
db.init_app(app)   
jwt = JWTManager(app)


# ------------- Init & seeds --------------
def init_db():
    """Initialize database and seed data"""
    with app.app_context():
        db.create_all()
        if RewardBrand.query.count() == 0:
            db.session.add_all([
                RewardBrand(name="Amazon", min_points=200),
                RewardBrand(name="Flipkart", min_points=150),
                RewardBrand(name="Swiggy", min_points=100),
            ])
        if Machine.query.count() == 0:
            db.session.add_all([
                Machine(machine_id="M001", name="RVM Station A", city="jim,korea",
                        lat=10.823879417459477, lng=78.70024710440879),
                Machine(machine_id="M002", name="RVM Station B", city="jim,korea",
                        lat=12.9352, lng=77.6245),
            ])
        if User.query.count() == 0:
            db.session.add_all([
                User(id="0", name="BUSANTECH", mobile=1234567890,
                     password_hash="$2b$12$MyPFgq8vz.EiUK2PlqG3BeWzTjhg9.f8y9W60tpfZ4aQEQ9F6JcBW",
                     points=100, bottles=10),
            ])
        db.session.commit()

# -------------- Helpers ------------------
def get_user_or_404(uid):
    user = User.query.get(uid)
    if not user:
        from flask import abort
        abort(404, description="User not found")
    return user

# ---------------- Auth -------------------
@app.route("/api/auth/register", methods=["POST"])
def register():
    data = request.get_json() or {}
    name = data.get("name")
    mobile = data.get("mobile")
    password = data.get("password")
    if not (name and mobile and password):
        return jsonify(message="Missing fields"), 400
    if User.query.filter_by(mobile=mobile).first():
        return jsonify(message="mobile already used"), 400
    u = User(name=name, mobile=mobile)
    u.set_password(password)
    db.session.add(u)
    db.session.commit()
    return jsonify(message="Registered"), 201

@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    mobile = data.get("mobile")
    password = data.get("password", "")
    u = User.query.filter_by(mobile=mobile).first()
    if not u or not u.check_password(password):
        return jsonify(message="Invalid credentials"), 401
    
    # FIXED: Ensure identity is a string
    token = create_access_token(
        identity=str(u.id),
        additional_claims={"mobile": u.mobile, "name": u.name}
    )
    return jsonify(
        access_token=token, 
        user={"id": u.id, "name": u.name, "mobile": u.mobile, "points": u.points, "bottles":u.bottles}
    )

# --------------- User endpoints -----------
@app.route("/api/users/me", methods=["GET"])
@jwt_required()
def me():
    uid_str = get_jwt_identity()
    uid = int(uid_str)  # Convert string back to int
    u = get_user_or_404(uid)
    return jsonify(
        id=u.id, 
        name=u.name, 
        mobile=u.mobile, 
        points=u.points, 
        bottles=u.bottles,
        created_at=u.created_at.isoformat()
    )

# ------------- Points & transactions -------
@app.route("/api/points/summary", methods=["GET"])
@jwt_required()
def points_summary():
    uid_str = get_jwt_identity()
    uid = int(uid_str)
    u = get_user_or_404(uid)
    recent = Transaction.query.filter_by(user_id=u.id).order_by(Transaction.created_at.desc()).limit(10).all()
    return jsonify(
        total_points=u.points,
        recent=[{"id": t.id, "points": t.points, "created_at": t.created_at.isoformat(), "type": t.type} for t in recent]
    )

@app.route("/api/transactions", methods=["GET"])
@jwt_required()
def transactions():
    uid_str = get_jwt_identity()
    uid = int(uid_str)
    rows = Transaction.query.filter_by(user_id=uid).order_by(Transaction.created_at.desc()).all()
    return jsonify(
        items=[{"id": r.id, "type": r.type, "points": r.points, "brand_id": r.brand_id, "machine_id": r.machine_id, "created_at": r.created_at.isoformat()} for r in rows]
    )

# --------------- Redeem ------------------
@app.route("/api/redeem/brands", methods=["GET"])
@jwt_required()
def redeem_brands():
    rows = RewardBrand.query.filter_by(active=True).all()
    return jsonify(items=[{"id": b.id, "name": b.name, "min_points": b.min_points} for b in rows])

@app.route("/api/redeem/request", methods=["POST"])
@jwt_required()
def redeem_request():
    uid_str = get_jwt_identity()
    uid = int(uid_str)
    u = get_user_or_404(uid)
    data = request.get_json() or {}
    brand_id = data.get("brand_id")
    pts = int(data.get("points", 0))
    brand = RewardBrand.query.get(brand_id)
    if not brand or not brand.active:
        return jsonify(message="Invalid brand"), 400
    if pts < brand.min_points:
        return jsonify(message=f"Minimum required for this brand is {brand.min_points}"), 400
    if u.points < pts:
        return jsonify(message="Not enough points"), 400

    u.points -= pts
    trx = Transaction(user_id=u.id, type="redeem", points=pts, brand_id=brand.id)
    db.session.add(trx)
    db.session.commit()

    # Simplified: return a fake coupon code for demo
    coupon = f"{brand.name[:3].upper()}-{u.id}-{str(trx.id).zfill(4)}"
    return jsonify(message="Redeem successful", coupon=coupon)

# -------------- Machine endpoints ----------
# Machine reports earned points (no auth for demo; in prod secure with machine key)
@app.route("/api/machine/insert", methods=["POST"])
def machine_insert():
    data = request.get_json() or {}
    machine_id = data.get("machine_id")
    user_id = data.get("user_id")
    bottle_count = int(data.get("bottle_count", 1))
    points_per_bottle = int(data.get("points_per_bottle", 10))
    
    if not (machine_id and user_id):
        return jsonify(message="machine_id and user_id required"), 400
    
    # Get user
    user = db.session.get(User, user_id)
    if not user:
        return jsonify(message="User not found"), 404
    
    # Get machine by machine_id (string identifier)
    machine = Machine.query.filter_by(machine_id=machine_id).first()
    if not machine:
        return jsonify(message="Machine not found"), 404
    
    # Check if machine has enough space
    available_space = machine.max_capacity - machine.current_bottles
    if bottle_count > available_space:
        return jsonify(
            message=f"Machine is full! Only {available_space} bottles can be accepted",
            available_space=available_space,
            requested=bottle_count
        ), 400
    
    # Check if this would make machine full
    if machine.current_bottles + bottle_count >= machine.max_capacity:
        machine.is_full = True
    
    earned_points = bottle_count * points_per_bottle
    
    # Update user
    user.points += earned_points
    user.bottles += bottle_count
    
    # Update machine
    machine.current_bottles += bottle_count
    machine.total_bottles += bottle_count
    
    # Create transaction
    trx = Transaction(
        user_id=user_id, 
        type="earn", 
        points=earned_points, 
        bottles=bottle_count,
        machine_id=machine_id
    )
    
    db.session.add(trx)
    db.session.commit()
    
    return jsonify(
        message="Points and bottles added successfully",
        earned_points=earned_points,
        bottles_added=bottle_count,
        user_total_points=user.points,
        user_total_bottles=user.bottles,
        machine_current_bottles=machine.current_bottles,
        machine_available_space=machine.max_capacity - machine.current_bottles,
        machine_is_full=machine.is_full
    )

# -------------- Machines list -------------
@app.route("/api/machines", methods=["GET"])
def list_machines():
    rows = Machine.query.all()
    
    return jsonify(items=[{
        "id": r.id, 
        "machine_id": r.machine_id, 
        "name": r.name,
        "city": r.city, 
        "lat": r.lat, 
        "lng": r.lng,
        "current_bottles": r.current_bottles,
        "max_capacity": r.max_capacity,
        "available_space": r.max_capacity - r.current_bottles,
        "is_full": r.is_full,
        "last_emptied": r.last_emptied.isoformat() if r.last_emptied else None
    } for r in rows])

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

# -------------- Run -----------------------
if __name__ == "__main__":
    with app.app_context():
        init_db() 
    app.run(host="0.0.0.0", port=5000, debug=True)