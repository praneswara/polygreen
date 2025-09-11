# models.py
from flask_sqlalchemy import SQLAlchemy
import datetime as dt
from passlib.hash import bcrypt

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120))
    mobile = db.Column(db.Integer, unique=True, index=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    points = db.Column(db.Integer, default=0)
    bottles = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=dt.datetime.utcnow)

    def set_password(self, pw):
        self.password_hash = bcrypt.hash(pw)

    def check_password(self, pw):
        return bcrypt.verify(pw, self.password_hash)

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True)
    type = db.Column(db.String(10))
    points = db.Column(db.Integer, default=0)
    bottles = db.Column(db.Integer, default=0)
    machine_id = db.Column(db.String(64))
    brand_id = db.Column(db.Integer, db.ForeignKey("reward_brand.id"))
    created_at = db.Column(db.DateTime, default=dt.datetime.utcnow)

class RewardBrand(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120))
    min_points = db.Column(db.Integer, default=100)
    active = db.Column(db.Boolean, default=True)

class Machine(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    machine_id = db.Column(db.String(64), unique=True, index=True)
    name = db.Column(db.String(120))
    city = db.Column(db.String(120))
    lat = db.Column(db.Float)
    lng = db.Column(db.Float)
    current_bottles = db.Column(db.Integer, default=0)
    max_capacity = db.Column(db.Integer, default=100)
    total_bottles = db.Column(db.Integer, default=0)
    is_full = db.Column(db.Boolean, default=False)
    last_emptied = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=dt.datetime.utcnow)
