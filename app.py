import os
import datetime as dt
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_jwt_extended import (
    JWTManager, create_access_token, jwt_required, get_jwt_identity
)
from dotenv import load_dotenv

# ---------------- App setup -------------
load_dotenv()
app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev")
app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "devjwt")
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = dt.timedelta(hours=24)
app.config["JWT_ALGORITHM"] = "HS256"

CORS(app)
jwt = JWTManager(app)

# ---------------- Demo Data -------------
USER = {
    "id": 1,
    "name": "Demo User",
    "mobile": "1234567890",
    "password": "password123",  # plain-text for demo
    "points": 100,
    "bottles": 10,
    "created_at": dt.datetime.utcnow().isoformat()
}

TRANSACTIONS = [
    {"id": 1, "type": "earn", "points": 50, "brand_id": None, "machine_id": "M001", "created_at": dt.datetime.utcnow().isoformat()},
    {"id": 2, "type": "redeem", "points": 30, "brand_id": 1, "machine_id": None, "created_at": dt.datetime.utcnow().isoformat()},
]

MACHINES = [
    {
        "id": 1, "machine_id": "M001", "name": "RVM Station A", "city": "Test City",
        "lat": 10.82, "lng": 78.70, "current_bottles": 20, "max_capacity": 100,
        "available_space": 80, "is_full": False, "last_emptied": None
    },
    {
        "id": 2, "machine_id": "M002", "name": "RVM Station B", "city": "Test City",
        "lat": 12.93, "lng": 77.62, "current_bottles": 50, "max_capacity": 100,
        "available_space": 50, "is_full": False, "last_emptied": None
    }
]

BRANDS = [
    {"id": 1, "name": "Amazon", "min_points": 200},
    {"id": 2, "name": "Flipkart", "min_points": 150},
    {"id": 3, "name": "Swiggy", "min_points": 100},
]


# ---------------- Auth -------------------
@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    mobile = str(data.get("mobile", ""))
    password = data.get("password", "")

    if mobile == USER["mobile"] and password == USER["password"]:
        token = create_access_token(identity=str(USER["id"]), additional_claims={"mobile": USER["mobile"], "name": USER["name"]})
        return jsonify(
            access_token=token,
            user={k: v for k, v in USER.items() if k != "password"}
        )
    return jsonify(message="Invalid credentials"), 401


# ---------------- User endpoints ---------
@app.route("/api/users/me", methods=["GET"])
@jwt_required()
def me():
    return jsonify({k: v for k, v in USER.items() if k != "password"})


# ---------------- Transactions -----------
@app.route("/api/transactions", methods=["GET"])
@jwt_required()
def transactions():
    return jsonify(items=TRANSACTIONS)


@app.route("/api/points/summary", methods=["GET"])
@jwt_required()
def points_summary():
    return jsonify(
        total_points=USER["points"],
        recent=TRANSACTIONS[-10:]
    )


# ---------------- Redeem -----------------
@app.route("/api/redeem/brands", methods=["GET"])
@jwt_required()
def redeem_brands():
    return jsonify(items=BRANDS)


@app.route("/api/redeem/request", methods=["POST"])
@jwt_required()
def redeem_request():
    data = request.get_json() or {}
    brand_id = data.get("brand_id")
    pts = int(data.get("points", 0))
    brand = next((b for b in BRANDS if b["id"] == brand_id), None)

    if not brand:
        return jsonify(message="Invalid brand"), 400
    if pts < brand["min_points"]:
        return jsonify(message=f"Minimum required for this brand is {brand['min_points']}"), 400
    if USER["points"] < pts:
        return jsonify(message="Not enough points"), 400

    USER["points"] -= pts
    trx_id = len(TRANSACTIONS) + 1
    trx = {"id": trx_id, "type": "redeem", "points": pts, "brand_id": brand_id, "machine_id": None, "created_at": dt.datetime.utcnow().isoformat()}
    TRANSACTIONS.append(trx)

    coupon = f"{brand['name'][:3].upper()}-{USER['id']}-{str(trx_id).zfill(4)}"
    return jsonify(message="Redeem successful", coupon=coupon)


# ---------------- Machines ---------------
@app.route("/api/machines", methods=["GET"])
def list_machines():
    return jsonify(items=MACHINES)


# ---------------- Run --------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
