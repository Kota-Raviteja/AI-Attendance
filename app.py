import csv
import os
from datetime import datetime
from functools import wraps

import cv2
import numpy as np
import base64
from flask import (
    Flask, render_template, request, session, redirect, url_for,
    Response, jsonify, flash, send_from_directory
)

from recognition_logic import AttendanceSystem
import auth
import settings

app = Flask(__name__)
app.secret_key = os.environ.get("FACEID_SECRET_KEY", "dev-secret-key-change-in-production")

attendance_system = AttendanceSystem()

login_required = auth.login_required
admin_required = auth.admin_required

# In-memory event used by the live check-in page to show toast + sound feedback
last_event = {"name": None, "period": None, "status": None}


@app.context_processor
def inject_globals():
    """Values every template needs: current config + who's logged in."""
    return {
        "site": settings.load_config(),
        "current_role": session.get("role"),
        "current_username": session.get("username"),
        "current_display_name": session.get("display_name"),
    }


# --------------------------------------------------------------------- auth

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        account = auth.verify_login(username, password)
        if account:
            session['username'] = username
            session['role'] = account['role']
            session['display_name'] = account.get('display_name', username)
            return redirect(url_for('index'))
        return render_template('login.html', error='Invalid username or password.')
    if session.get('username'):
        return redirect(url_for('index'))
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ---------------------------------------------------------------- dashboard

@app.route('/')
@login_required
def index():
    now_date = datetime.now().strftime("%Y-%m-%d")

    if session.get('role') == 'admin':
        attendance_data = []
        today_count = 0
        if os.path.exists("attendance.csv"):
            with open("attendance.csv", 'r') as f:
                reader = csv.reader(f)
                next(reader, None)
                attendance_data = list(reader)
                for row in attendance_data:
                    if len(row) > 2 and row[2] == now_date and row[4] == 'SUCCESS':
                        today_count += 1
                attendance_data.reverse()

        registered_users = attendance_system.list_registered_users()
        trend = attendance_system.get_daily_trend(days=7)
        breakdown = attendance_system.get_status_breakdown()

        return render_template(
            'dashboard_admin.html',
            data=attendance_data[:50],
            todays_checkins=today_count,
            total_users=len(registered_users),
            trend=trend,
            breakdown=breakdown,
        )

    # Regular user: only their own data
    linked_user = None
    accounts = auth.list_accounts()
    account = accounts.get(session.get('username'), {})
    linked_user = account.get('linked_user')

    history = attendance_system.get_user_history(linked_user, limit=50) if linked_user else []
    today_status = any(
        row.get('Date') == now_date and row.get('Status') == 'SUCCESS' for row in history
    )
    shift_start = attendance_system.users.get(linked_user, "09:00") if linked_user else None

    return render_template(
        'dashboard_user.html',
        history=history,
        today_status=today_status,
        shift_start=shift_start,
        linked_user=linked_user,
    )


# ------------------------------------------------------------- registration

@app.route('/register')
@admin_required
def register_page():
    return render_template('register.html')


@app.route('/api/register', methods=['POST'])
@admin_required
def api_register():
    data = request.json or {}
    name = (data.get('name') or '').strip()
    start_time = data.get('start_time', '09:00')
    images = data.get('images', [])
    create_login = data.get('create_login', False)
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    if not name or not images:
        return jsonify({"error": "Missing name or images"}), 400

    if name in attendance_system.list_registered_users_names():
        return jsonify({"error": f"'{name}' is already registered."}), 400

    if create_login:
        if not username:
            return jsonify({"error": "Username is required to create a login."}), 400
        if auth.account_exists(username):
            return jsonify({"error": f"Username '{username}' is already taken."}), 400

    try:
        user_dir = os.path.join("faces", name)
        if not os.path.exists(user_dir):
            os.makedirs(user_dir)

        for i, image_data in enumerate(images):
            encoded_data = image_data.split(',')[1]
            nparr = np.frombuffer(base64.b64decode(encoded_data), np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            img_path = os.path.join(user_dir, f"{i + 1}.jpg")
            cv2.imwrite(img_path, img)

        attendance_system.users[name] = start_time
        attendance_system.save_users()
        attendance_system.train_model()

        login_info = None
        if create_login:
            generated_password = password if password else auth.generate_temp_password()
            auth.create_account(
                username=username,
                password=generated_password,
                role='user',
                display_name=name,
                linked_user=name,
            )
            login_info = {"username": username, "password": generated_password}

        return jsonify({"success": True, "login": login_info})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# -------------------------------------------------------------- management

@app.route('/manage')
@admin_required
def manage():
    users = attendance_system.list_registered_users()
    accounts = auth.list_accounts()
    linked_names = {a.get('linked_user') for a in accounts.values() if a.get('linked_user')}
    for u in users:
        u['has_login'] = u['name'] in linked_names
    return render_template('manage.html', users=users)


@app.route('/faces/<path:filename>')
@login_required
def face_image(filename):
    return send_from_directory('faces', filename)


@app.route('/api/vault/unlock', methods=['POST'])
@admin_required
def api_vault_unlock():
    data = request.json or {}
    config = settings.load_config()
    ok = data.get('passcode') == config.get('vault_passcode')
    return jsonify({"success": ok})


@app.route('/api/delete_user', methods=['POST'])
@admin_required
def api_delete_user():
    data = request.json or {}
    name = data.get('name')
    if not name:
        return jsonify({"error": "Missing name"}), 400
    try:
        attendance_system.delete_user(name)
        auth.delete_accounts_linked_to(name)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/create_login', methods=['POST'])
@admin_required
def api_create_login():
    data = request.json or {}
    name = data.get('name')
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    if not name or not username:
        return jsonify({"error": "Missing name or username"}), 400
    if auth.account_exists(username):
        return jsonify({"error": f"Username '{username}' is already taken."}), 400

    generated_password = password if password else auth.generate_temp_password()
    auth.create_account(
        username=username, password=generated_password,
        role='user', display_name=name, linked_user=name,
    )
    return jsonify({"success": True, "username": username, "password": generated_password})


# ---------------------------------------------------------------- settings

@app.route('/settings')
@admin_required
def settings_page():
    return render_template('settings.html', config=settings.load_config())


@app.route('/api/settings', methods=['POST'])
@admin_required
def api_settings():
    data = request.json or {}
    allowed_keys = {
        'brand_name', 'theme_color_start', 'theme_color_end',
        'shift_hours', 'recognition_threshold', 'vault_passcode',
        'sound_enabled_default',
    }
    partial = {k: v for k, v in data.items() if k in allowed_keys}
    if 'shift_hours' in partial:
        try:
            partial['shift_hours'] = max(1, min(24, int(partial['shift_hours'])))
        except (TypeError, ValueError):
            partial.pop('shift_hours', None)
    if 'recognition_threshold' in partial:
        try:
            partial['recognition_threshold'] = max(20, min(200, float(partial['recognition_threshold'])))
        except (TypeError, ValueError):
            partial.pop('recognition_threshold', None)

    config = settings.update_config(partial)
    attendance_system.reload_config()
    return jsonify({"success": True, "config": config})


# ----------------------------------------------------------------- profile

@app.route('/profile')
@login_required
def profile():
    accounts = auth.list_accounts()
    account = accounts.get(session['username'], {})
    return render_template('profile.html', account=account)


@app.route('/api/change_password', methods=['POST'])
@login_required
def api_change_password():
    data = request.json or {}
    current = data.get('current_password', '')
    new_password = data.get('new_password', '')

    if not new_password or len(new_password) < 4:
        return jsonify({"error": "New password must be at least 4 characters."}), 400

    account = auth.verify_login(session['username'], current)
    if not account:
        return jsonify({"error": "Current password is incorrect."}), 403

    auth.change_password(session['username'], new_password)
    return jsonify({"success": True})


# ------------------------------------------------------------- live camera

@app.route('/attendance')
@login_required
def attendance():
    return render_template('attendance.html')


def gen_frames():
    global last_event
    camera = cv2.VideoCapture(0)
    while True:
        success, frame = camera.read()
        if not success:
            break
        else:
            face_locations, recognized_names = attendance_system.process_frame(frame)

            for (top, right, bottom, left), name in zip(face_locations, recognized_names):
                top *= 4
                right *= 4
                bottom *= 4
                left *= 4

                cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)

                if name != "Unknown":
                    period = attendance_system.get_period(name)

                    if period == "OUT_OF_HOURS":
                        attendance_system.log_attendance(name, "OUT_OF_HOURS")
                        last_event = {"name": name, "period": "OUT_OF_HOURS", "status": "OUT_OF_HOURS"}
                        label = f"{name} (OUT OF HOURS)"
                        color = (0, 0, 255)
                    else:
                        logged, status = attendance_system.log_attendance(name, period)
                        if status == "SUCCESS":
                            last_event = {"name": name, "period": period, "status": "NEW"}
                        label = f"{name} (P{period})"
                        color = (0, 255, 0)
                else:
                    label = "Unknown"
                    color = (0, 0, 255)

                cv2.putText(frame, label, (left + 6, bottom - 6), cv2.FONT_HERSHEY_DUPLEX, 0.8, color, 1)

            ret, buffer = cv2.imencode('.jpg', frame)
            frame = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

    camera.release()


@app.route('/video_feed')
@login_required
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/api/poll')
@login_required
def api_poll():
    global last_event
    resp = jsonify(last_event)
    last_event = {"name": None, "period": None, "status": None}
    return resp


# ------------------------------------------------------------------ export

@app.route('/export/attendance.csv')
@admin_required
def export_attendance():
    return send_from_directory('.', 'attendance.csv', as_attachment=True,
                                download_name='attendance_export.csv')


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
