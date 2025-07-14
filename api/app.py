from flask import Flask, render_template, redirect, url_for, request, session, flash
from config import Config
from functools import wraps
from flask import make_response
from models.models import db, User, ParkingLot, ParkingSpot,Booking
from datetime import datetime
from flask import flash, redirect, session, url_for
from datetime import datetime
import pytz
import io
import base64
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from sqlalchemy import func
import matplotlib
matplotlib.use('Agg')
from werkzeug.security import generate_password_hash
from werkzeug.security import check_password_hash


app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

# Create database tables
with app.app_context():
    db.create_all()

@app.route('/')
def index():
    return redirect(url_for('login'))
def no_cache(view):
    @wraps(view)
    def no_cache_wrapper(*args, **kwargs):
        response = make_response(view(*args, **kwargs))
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '-1'
        return response
    return no_cache_wrapper

# Signup route
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        fullname = request.form['fullname']
        email = request.form['email']
        password = request.form['password']
        confirm = request.form['confirm']
        address = request.form['address']
        pincode = request.form['pincode']
        role = request.form['role']

        if password != confirm:
            flash('Passwords do not match!')
            return redirect(url_for('signup'))

        if User.query.filter_by(email=email).first():
            flash('Email already registered.')
            return redirect(url_for('signup'))

        # ✅ Hash the password securely
        hashed_password = generate_password_hash(password)

        user = User(
            fullname=fullname,
            email=email,
            password=hashed_password,
            address=address,
            pincode=pincode,
            role=role
        )
        db.session.add(user)
        db.session.commit()

        flash('Signup successful! Please log in.')
        return redirect(url_for('login'))

    return render_template('signup.html')

# Login route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['role'] = user.role
            session['fullname'] = user.fullname

            if user.role == 'admin':
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('user_dashboard'))
        else:
            flash('Invalid email or password.')
            return redirect(url_for('login'))

    return render_template('login.html')
# Admin dashboard
@app.route('/admin')
@no_cache

def admin_dashboard():
    if 'user_id' not in session:
        flash('Please log in to continue.')
        return redirect(url_for('login'))
    if session.get('role') != 'admin':
        flash('Unauthorized access')
        return redirect(url_for('login'))

    fullname = session.get('fullname')
    lots = ParkingLot.query.all()

    lot_data = []
    for lot in lots:
        filled_spots = ParkingSpot.query.filter_by(lot_id=lot.id, status='occupied').count()
        total_spots = ParkingSpot.query.filter_by(lot_id=lot.id).count()

        lot_data.append({
            'id': lot.id,
            'name': lot.name,
            'max_spots': total_spots,
            'filled_spots': filled_spots,
            'spots': lot.spots
        })
        pending_payments_count = Booking.query \
        .filter_by(pending_payment=True) \
        .filter(Booking.duration_hours.isnot(None)) \
        .count()

    return render_template(
        'admin_dashboard.html',
        fullname=fullname,
        lots=lot_data,
        pending_payments_count=pending_payments_count 
    )
@app.route('/edit-profile', methods=['GET', 'POST'])
def edit_profile():
    if 'user_id' not in session:
        flash('Please log in first.')
        return redirect(url_for('login'))

    user = User.query.get_or_404(session['user_id'])

    if request.method == 'POST':
        user.fullname = request.form['fullname']
        user.email = request.form['email']
        user.address = request.form['address']
        user.pincode = request.form['pincode']

        db.session.commit()
        flash('Profile updated successfully.')
        session['fullname'] = user.fullname  # update session
        return redirect(url_for('edit_profile'))

    return render_template('edit_profile.html', user=user)

#admin_users
@app.route('/users')
def admin_users():
    if session.get('role') != 'admin':
        flash('Unauthorized access')
        return redirect(url_for('login'))

    users = User.query.filter(User.role != 'admin').all()
    fullname = session.get('fullname')
    return render_template('admin_users.html', users=users, fullname=fullname)
#admin_search
@app.route('/admin/search', methods=['GET', 'POST'])
def admin_search():
    if session.get('role') != 'admin':
        flash('Unauthorized access')
        return redirect(url_for('login'))

    query = request.args.get('q', '').strip()
    search_type = request.args.get('type', '')

    results = []

    if query and search_type:
        if search_type == 'location':
            results = ParkingLot.query.filter(ParkingLot.address.ilike(f'%{query}%')).all()
        elif search_type == 'userid':
            results = ParkingSpot.query.filter_by(current_user_id=query).all()
        # Add more filters if needed

    return render_template('admin_search.html', query=query, search_type=search_type, results=results)
@app.route('/admin/summary')
@no_cache
def admin_summary():
    # — auth & role check —
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Unauthorized')
        return redirect(url_for('login'))

    # — 1) Total revenue per lot (bar chart) —
    # Pull every booking with a cost
    # Query revenue data from Booking table
    rev_qs = (
        Booking.query
        .filter(Booking.total_cost.isnot(None))
        .with_entities(
            Booking.original_lot_id.label('lot_id'),
            func.sum(Booking.total_cost).label('revenue')
        )
        .group_by(Booking.original_lot_id)
        .all()
    )

    # Create DataFrame
    rev_df = pd.DataFrame(rev_qs, columns=['lot_id', 'revenue'])

    # Query existing lots to map lot_id -> name
    lots_all = ParkingLot.query.with_entities(
        ParkingLot.id.label('lot_id'),
        ParkingLot.name
    ).all()

    lots_df = pd.DataFrame(lots_all, columns=['lot_id', 'name'])

    # Merge to map names; lots that no longer exist will have NaN -> use lot_id as fallback
    rev_df = rev_df.merge(lots_df, on='lot_id', how='left')
    rev_df['name'] = rev_df['name'].fillna(rev_df['lot_id'].astype(str))

    # Now plot the bar chart
    fig, ax = plt.subplots()
    rev_df.set_index('name')['revenue'].plot(kind='bar', ax=ax, color='#3498db')

    ax.set_title('Total Revenue by Lot')
    ax.set_ylabel('Revenue (₹)')
    ax.set_xlabel('Parking Lot')
    plt.xticks(rotation=45)
    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format='png', bbox_inches='tight')
    revenue_chart_b64 = base64.b64encode(buf.getvalue()).decode()
    bar_revenue = revenue_chart_b64
    plt.close(fig)


    # — 2) Daily total revenue (time-series) —
    daily_qs = (
        Booking.query
        .filter(Booking.total_cost.isnot(None))
        .with_entities(
            func.date(Booking.release_time).label('d'),
            func.sum(Booking.total_cost).label('revenue')
        )
        .group_by(func.date(Booking.release_time))
        .order_by(func.date(Booking.release_time))
        .all()
    )
    daily_df = pd.DataFrame(daily_qs, columns=['date','revenue'])
    if not daily_df.empty:
        daily_df['date'] = pd.to_datetime(daily_df['date'])
        fig2, ax2 = plt.subplots()
        ax2.plot(daily_df['date'], daily_df['revenue'], marker='o')
        ax2.xaxis.set_major_locator(mdates.DayLocator(interval=1))
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        ax2.set_title('Daily Aggregate Revenue')
        ax2.set_xlabel('Date')
        ax2.set_ylabel('Revenue')
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()
        buf = io.BytesIO()
        fig2.savefig(buf, format='png', bbox_inches='tight')
        ts_revenue = base64.b64encode(buf.getvalue()).decode('ascii')
        plt.close(fig2)
    else:
        ts_revenue = None

    # — 3) Pie: users by pincode (excluding admins) —
    users = (
        User.query
        .filter(User.role != 'admin')
        .with_entities(User.pincode, func.count(User.id))
        .group_by(User.pincode)
        .all()
    )
    users_df = pd.DataFrame(users, columns=['pincode','count'])
    fig3, ax3 = plt.subplots()
    ax3.pie(
        users_df['count'],
        labels=users_df['pincode'],
        autopct='%.1f%%',
        startangle=90
    )
    ax3.set_title('Users by Pincode')
    buf = io.BytesIO()
    fig3.savefig(buf, format='png', bbox_inches='tight')
    pie_users = base64.b64encode(buf.getvalue()).decode('ascii')
    plt.close(fig3)

    # — 4) 100% Stacked bar: % occupied vs free per lot —
    spots = (
        ParkingSpot.query
        .with_entities(ParkingSpot.lot_id, ParkingSpot.status, func.count(ParkingSpot.id))
        .group_by(ParkingSpot.lot_id, ParkingSpot.status)
        .all()
    )
    # Create DataFrame from the query result
    spots_df = pd.DataFrame(spots, columns=['lot_id', 'status', 'count'])

    # Pivot to get counts per lot, with `status` as columns (e.g., 'free', 'occupied')
    pivot = spots_df.pivot(index='lot_id', columns='status', values='count').fillna(0)

    # Ensure both 'free' and 'occupied' columns exist, even if no data for one
    pivot['free'] = pivot.get('free', 0)
    pivot['occupied'] = pivot.get('occupied', 0)

    # Normalize to 100% (you can add more statuses if you want to expand this)
    pivot_pct = pivot.div(pivot.sum(axis=1), axis=0) * 100

    # Map lot names
    names = pd.DataFrame(lots_all, columns=['lot_id', 'name'])
    pivot_pct = pivot_pct.merge(names, on='lot_id', how='left').set_index('name')

    # Plotting the Stacked Bar Chart
    fig4, ax4 = plt.subplots()
    pivot_pct[['free', 'occupied']].plot(kind='bar', stacked=True, ax=ax4)
    ax4.set_ylabel('% of Spots')
    ax4.set_xlabel('Lot')
    ax4.set_title('Lot Utilization (Free vs Occupied)')
    ax4.legend(title='Status', loc='upper right')

    # Save to buffer and encode as PNG
    buf = io.BytesIO()
    fig4.savefig(buf, format='png', bbox_inches='tight')
    stacked_util = base64.b64encode(buf.getvalue()).decode('ascii')
    plt.close(fig4)


    return render_template(
        'admin_summary.html',
        bar_revenue=bar_revenue,
        ts_revenue=ts_revenue,
        pie_users=pie_users,
        stacked_util=stacked_util,
        fullname=session.get('fullname')
    )
@app.route('/admin/spot/<int:spot_id>')
def view_spot(spot_id):
    spot = ParkingSpot.query.get_or_404(spot_id)  # ✅ Now spot is defined before we use it
    if spot.status == 'occupied':
        booking = Booking.query.filter_by(spot_id=spot.id, release_time=None).order_by(Booking.start_time.desc()).first()
        return render_template('occupied_spot_details.html', spot=spot, booking=booking)
    else:
        return render_template('free_spot_details.html', spot=spot)

@app.route('/admin/lots/<int:lot_id>/delete', methods=['POST'])
def delete_lot(lot_id):
    if session.get('role') != 'admin':
        flash('Unauthorized access')
        return redirect(url_for('login'))

    lot = ParkingLot.query.get_or_404(lot_id)

    occupied_count = ParkingSpot.query.filter_by(lot_id=lot.id, status='occupied').count()
    if occupied_count > 0:
        flash('Cannot delete: some spots still occupied.', 'danger')
    else:
        # first delete all free spots
        ParkingSpot.query.filter_by(lot_id=lot.id).delete()
        db.session.delete(lot)
        db.session.commit()
        flash(f'Lot #{lot_id} deleted; bookings retain original_lot_id={lot_id}.', 'success')

    return redirect(url_for('admin_dashboard'))

# Add Lot
@app.route('/admin/lots/add', methods=['GET', 'POST'])
def add_lot():
    if session.get('role') != 'admin':
        flash('Unauthorized access')
        return redirect(url_for('login'))

    if request.method == 'POST':
        name = request.form['name']
        address = request.form['address']
        pincode = request.form['pincode']
        hourly_rate = float(request.form['hourly_rate'])
        max_spots = int(request.form['max_spots'])

        lot = ParkingLot(
            name=name,
            address=address,
            pincode=pincode,
            hourly_rate=hourly_rate,
            max_spots=max_spots
        )
        db.session.add(lot)
        db.session.commit()

        # Create parking spots
        for _ in range(max_spots):
            spot = ParkingSpot(lot_id=lot.id)
            db.session.add(spot)
        db.session.commit()

        flash('Parking lot added successfully.')
        return redirect(url_for('admin_dashboard'))

    return render_template('add_lot.html')

# Edit Lot
@app.route('/admin/lots/edit/<int:lot_id>', methods=['GET', 'POST'])
def edit_lot(lot_id):
    if session.get('role') != 'admin':
        flash('Unauthorized access')
        return redirect(url_for('login'))

    lot = ParkingLot.query.get_or_404(lot_id)
    if request.method == 'POST':
        lot.name = request.form['name']
        lot.address = request.form['address']
        lot.pincode = request.form['pincode']
        lot.hourly_rate = float(request.form['hourly_rate'])
        lot.max_spots = int(request.form['max_spots'])
        db.session.commit()
        flash('Parking lot updated.')
        return redirect(url_for('admin_dashboard'))

    return render_template('edit_lot.html', lot=lot)

# Manage Spots (view)
@app.route('/admin/lots/<int:lot_id>/spots')
def manage_spots(lot_id):
    lot = ParkingLot.query.get_or_404(lot_id)
    return render_template('manage_spot.html', lot=lot)

#delete spot
@app.route('/admin/spots/<int:spot_id>/delete', methods=['POST'])
def delete_spot(spot_id):
    if session.get('role') != 'admin':
        flash('Unauthorized access')
        return redirect(url_for('login'))

    spot = ParkingSpot.query.get_or_404(spot_id)

    if spot.status == 'occupied':
        flash('Cannot delete an occupied spot.', 'danger')
    else:
        db.session.delete(spot)
        db.session.commit()
        flash(f'Spot #{spot_id} deleted; all bookings keep original_spot_id={spot_id}.', 'success')

    return redirect(url_for('admin_dashboard', lot_id=spot.lot_id))


# Summary (placeholder)
@app.route('/admin/summary')
def summary():
    if session.get('role') != 'admin':
        flash('Unauthorized access')
        return redirect(url_for('login'))

    # Placeholder data
    data = {}
    return render_template('summary.html', data=data)

# User dashboard
@app.route('/user')
@no_cache
def user_dashboard():
    if 'user_id' not in session:
        flash('Please log in to continue.')
        return redirect(url_for('login'))
    if session.get('role') != 'user':
        flash('Unauthorized access')
        return redirect(url_for('login'))

    user_id = session.get('user_id')

    # ✅ Get active booking (if any)
    current_booking = (
        Booking.query
        .filter_by(user_id=user_id, release_time=None)
        .order_by(Booking.start_time.desc())
        .first()
    )

    # ✅ Get last 2 completed bookings
    recent_bookings = (
        Booking.query
        .filter_by(user_id=user_id)
        .filter(Booking.release_time.isnot(None))
        .order_by(Booking.release_time.desc())
        .limit(2)
        .all()
    )

    # ✅ Lot search
    q = request.args.get('q', '').strip()
    if q:
        lots = ParkingLot.query.filter(
            (ParkingLot.address.ilike(f'%{q}%')) |
            (ParkingLot.pincode.ilike(f'%{q}%'))
        ).all()
    else:
        lots = ParkingLot.query.all()

    return render_template(
        'user_dashboard.html',
        current_booking=current_booking,
        recent_bookings=recent_bookings,
        lots=lots,
        fullname=session.get('fullname')
    )
#user_summary
@app.route('/user/summary')
@no_cache
def user_summary():
    # — auth & role check
    if 'user_id' not in session:
        flash('Please log in to continue.')
        return redirect(url_for('login'))
    if session.get('role') != 'user':
        flash('Unauthorized access')
        return redirect(url_for('login'))
    user_id = session['user_id']

    # — pull all completed bookings for this user
    records = (
        Booking.query
        .filter_by(user_id=user_id)
        .filter(Booking.release_time.isnot(None))
        .join(ParkingLot, Booking.lot_id == ParkingLot.id)
        .with_entities(
            Booking.start_time,
            Booking.release_time,
            ParkingLot.name.label('lot_name'),
            ParkingLot.hourly_rate
        )
        .all()
    )
    df = pd.DataFrame(records, columns=['start_time','release_time','lot_name','hourly_rate'])

    # placeholders
    pie_b64 = bar_b64 = ts_b64 = None

    if not df.empty:
        df['duration_h'] = (df.release_time - df.start_time).dt.total_seconds() / 3600
        df['date']       = df.release_time.dt.date
        df['cost']       = df.duration_h * df.hourly_rate

        # Pie: usage %
        pie = df['lot_name'].value_counts(normalize=True) * 100
        fig1, ax1 = plt.subplots()
        ax1.pie(pie, labels=pie.index, autopct='%.1f%%', startangle=90)
        ax1.set_title('Parking Usage % by Lot')
        buf = io.BytesIO(); fig1.savefig(buf, format='png', bbox_inches='tight')
        pie_b64 = base64.b64encode(buf.getvalue()).decode()
        plt.close(fig1)

        # Bar: hourly rate
        all_lots = ParkingLot.query.with_entities(
            ParkingLot.name.label('lot_name'),
            ParkingLot.hourly_rate
        ).all()

        # 2) Turn into a small DataFrame
        lots_df = pd.DataFrame(all_lots, columns=['lot_name','hourly_rate'])

        # 3) Plot
        fig2, ax2 = plt.subplots()
        lots_df.set_index('lot_name')['hourly_rate'].plot(kind='bar', ax=ax2)
        ax2.set_ylabel('Hourly Rate')
        ax2.set_xlabel('Lot')
        ax2.set_title('Hourly Rate by Lot')

        # 4) Encode as PNG
        bar_buf = io.BytesIO()
        fig2.savefig(bar_buf, format='png', bbox_inches='tight')
        bar_b64 = base64.b64encode(bar_buf.getvalue()).decode('ascii')
        plt.close(fig2)

        # Time‑series: daily cost
        daily_expense= df.groupby('date')['cost'].sum()
        daily_expense.index = pd.to_datetime(daily_expense.index)

        fig, ax = plt.subplots()
        ax.plot(daily_expense.index, daily_expense.values, marker='o')

        # 1) Major ticks: every day
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))

        # 2) Formatter: YYYY‑MM‑DD
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))

        ax.set_title('Daily Parking Cost')
        ax.set_xlabel('Date')
        ax.set_ylabel('Total Cost')
        plt.xticks(rotation=45)
        buf = io.BytesIO(); fig.savefig(buf, format='png', bbox_inches='tight')
        ts_b64 = base64.b64encode(buf.getvalue()).decode()
        plt.close(fig)

    return render_template(
        'summary.html',
        pie_chart=pie_b64,
        bar_chart=bar_b64,
        ts_chart=ts_b64,
        fullname=session.get('fullname')
    )
# Book spot
IST = pytz.timezone('Asia/Kolkata')

@app.route('/user/book/<int:spot_id>', methods=['GET', 'POST'])
def book_spot(spot_id):
    # --- Authorization ---
    if session.get('role') != 'user':
        flash('Unauthorized access')
        return redirect(url_for('admin_dashboard'))

    spot = ParkingSpot.query.get_or_404(spot_id)
    if spot.status != 'free':
        flash('Spot already occupied.')
        return redirect(url_for('user_dashboard'))

    if request.method == 'POST':
        vehicle_number = request.form['vehicle_number'].strip()
        if not vehicle_number:
            flash('Vehicle number is required.')
            return redirect(url_for('book_spot', spot_id=spot_id))

        # IST‐aware start_time
        start_ist = datetime.now(IST)

        # Create Booking record
        booking = Booking(
            user_id          = session['user_id'],
            # live FKs
            lot_id           = spot.lot_id,
            spot_id          = spot.id,
            # historical copy
            original_lot_id  = spot.lot_id,
            original_spot_id = spot.id,

            vehicle_number   = vehicle_number,
            start_time       = start_ist
        )
        # mark spot occupied…
        spot.status          = 'occupied'
        spot.current_user_id = session['user_id']
        spot.start_time      = start_ist

        db.session.add(booking)
        db.session.commit()

        flash(f'Spot #{spot.id} booked at {start_ist.strftime("%Y-%m-%d %H:%M:%S")} IST')
        return redirect(url_for('user_dashboard'))

        # GET → show booking form
    return render_template('book_spot.html', spot=spot)

@app.route('/user/release/confirm/<int:spot_id>', methods=['GET'])
def show_release_form(spot_id):
    if session.get('role') != 'user':
        flash('Unauthorized access')
        return redirect(url_for('login'))

    spot = ParkingSpot.query.get_or_404(spot_id)
    booking = Booking.query.filter_by(
        spot_id=spot.id,
        user_id=session['user_id'],
        release_time=None
    ).order_by(Booking.start_time.desc()).first()

    if not booking:
        flash('No active booking found.')
        return redirect(url_for('user_dashboard'))

    now = datetime.now(IST)  # This is an aware datetime
    start = booking.start_time

    # Ensure start_time is timezone-aware (localize if it's naive)
    if start.tzinfo is None:
        start = IST.localize(start)

    # Calculate duration
    duration_hours = round((now - start).total_seconds() / 3600.0, 2)
    lot = ParkingLot.query.get(spot.lot_id)
    estimated_cost = round(duration_hours * lot.hourly_rate, 2)

    return render_template(
        'release_form.html',
        spot=spot,
        booking=booking,
        now=now,
        estimated_cost=estimated_cost
    )



@app.route('/user/release/<int:spot_id>', methods=['POST'])
def release_spot(spot_id):
    if session.get('role') != 'user':
        flash('Unauthorized access')
        return redirect(url_for('admin_dashboard'))

    spot = ParkingSpot.query.get_or_404(spot_id)

    if spot.status != 'occupied' or spot.current_user_id != session['user_id']:
        flash('Cannot release this spot.')
        return redirect(url_for('user_dashboard'))

    booking = Booking.query.filter_by(
        spot_id=spot.id,
        user_id=session['user_id'],
        release_time=None
    ).first()

    if not booking:
        flash('No active booking found.')
        return redirect(url_for('user_dashboard'))

    start = booking.start_time
    if start.tzinfo is None:  # If start time is naive, localize it
        start = IST.localize(start)

    now = datetime.now(IST)  # Make sure `now` is aware as well

    # Calculate duration
    duration_hours = round((now - start).total_seconds() / 3600.0, 2)
    lot = ParkingLot.query.get(spot.lot_id)
    total_cost = round(duration_hours * lot.hourly_rate, 2)

    # Update booking
    booking.duration_hours = duration_hours
    booking.total_cost = total_cost
    booking.payment_pending = True

    db.session.commit()
    return redirect(url_for('checkout_page', booking_id=booking.id))
# @app.route('/admin/spot/<int:spot_id>',methods=['GET'])
# def occupied_spot_details(spot_id):
#     # -- only admins --
#     if session.get('role') != 'admin':
#         flash('Unauthorized access')
#         return redirect(url_for('login'))

#     # fetch the spot
#     spot = ParkingSpot.query.get_or_404(spot_id)

#     # find its active booking (no release_time yet)
#     booking = (
#         Booking.query
#                .filter_by(spot_id=spot.id, release_time=None)
#                .order_by(Booking.start_time.desc())
#                .first_or_404()
#     )

#     # ensure start_time is IST‑aware
#     start = booking.start_time
#     if start.tzinfo is None:
#         start = IST.localize(start)

#     # now in IST
#     now = datetime.now(IST)

#     # compute hours parked
#     duration_hours = (now - start).total_seconds() / 3600.0

#     # lookup the lot’s rate
#     lot = ParkingLot.query.get_or_404(spot.lot_id)
#     estimated_cost = round(duration_hours * lot.hourly_rate, 2)

#     # pass it into the template
#     return render_template(
#         'occupied_spot_details.html',
#         spot=spot,
#         booking=booking,
#         estimated_cost=estimated_cost
#     )

@app.route('/user/checkout/<int:booking_id>')
def checkout_page(booking_id):
    booking = Booking.query.get_or_404(booking_id)

    if not booking.pending_payment:
        flash('Payment has been confirmed—thank you!')
        return redirect(url_for('user_dashboard'))

    qr_code_url = url_for('static', filename='css/qr_codes/athpay.jpeg')

    return render_template('checkout.html', booking=booking, qr_code_url=qr_code_url)
@app.route('/admin/payments')
def admin_payments():
    if session.get('role') != 'admin':
        flash('Unauthorized access')
        return redirect(url_for('login'))

    pending_bookings = Booking.query.filter_by(pending_payment=True).filter(Booking.duration_hours != None).all()

    return render_template('admin_payments.html', bookings=pending_bookings)

@app.route('/admin/confirm_payment/<int:booking_id>', methods=['POST'])
def confirm_payment(booking_id):
    if session.get('role') != 'admin':
        flash('Unauthorized access')
        return redirect(url_for('login'))

    booking = Booking.query.get_or_404(booking_id)
    spot = ParkingSpot.query.get_or_404(booking.spot_id)

    if not booking.pending_payment:
        flash('No pending payment for this booking.')
        return redirect(url_for('admin_payments'))

    now = datetime.now(IST)

    booking.release_time = now
    booking.pending_payment = False

    spot.status = 'free'
    spot.current_user_id = None
    spot.release_time = now

    db.session.commit()

    flash(f'Payment confirmed. Spot {spot.id} released.')
    return redirect(url_for('admin_payments'))

# Logout
@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.')
    return redirect(url_for('login'))
@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

if __name__ == '__main__':
    app.run(debug=True)

