from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(128), nullable=False)
    fullname = db.Column(db.String(100))
    address = db.Column(db.String(200))
    pincode = db.Column(db.String(10))
    role = db.Column(db.String(10), default='user')  # 'user' or 'admin'

class ParkingLot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    address = db.Column(db.String(200))
    pincode = db.Column(db.String(10))
    hourly_rate = db.Column(db.Float, nullable=False)
    max_spots = db.Column(db.Integer, nullable=False)
    spots = db.relationship('ParkingSpot', backref='lot', lazy=True)

class ParkingSpot(db.Model):
    id = db.Column(db.Integer, primary_key=True,autoincrement=True)
    lot_id = db.Column(db.Integer, db.ForeignKey('parking_lot.id'), nullable=False)
    status = db.Column(db.String(10), default='free')  # 'free' or 'occupied'
    current_user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    start_time = db.Column(db.DateTime)
    release_time = db.Column(db.DateTime)
    total_cost = db.Column(db.Float)

    user = db.relationship('User')
class Booking(db.Model):
    __tablename__ = 'booking'

    id               = db.Column(db.Integer, primary_key=True,autoincrement=True)

    # → never changes, always keeps the “historical” ID
    original_lot_id  = db.Column(db.Integer, nullable=False)
    original_spot_id = db.Column(db.Integer, nullable=False)

    # → a live foreign‑key, only used when the lot/spot still exists
    lot_id           = db.Column(
                          db.Integer,
                          db.ForeignKey('parking_lot.id', ondelete='SET NULL'),
                          nullable=True
                      )
    spot_id          = db.Column(
                          db.Integer,
                          db.ForeignKey('parking_spot.id', ondelete='SET NULL'),
                          nullable=True
                      )

    user_id          = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    vehicle_number   = db.Column(db.String(20), nullable=False)
    start_time       = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    release_time     = db.Column(db.DateTime, nullable=True)
    duration_hours   = db.Column(db.Float, nullable=True)
    total_cost       = db.Column(db.Float, nullable=True)
    pending_payment = db.Column(db.Boolean, default=True)


    user             = db.relationship('User', backref='bookings')
    lot              = db.relationship('ParkingLot', backref='bookings', passive_deletes=True)
    spot             = db.relationship('ParkingSpot', backref='bookings', passive_deletes=True)



