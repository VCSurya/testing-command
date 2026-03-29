from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import os
from utils import get_db_connection, login_required, encrypt_password, get_redirect_url
from flask_cors import CORS
from flask_socketio import SocketIO, disconnect

# import blueprints
from manager import manager_bp
from sales import sales_bp
from packing import packaging_bp
from transport import transport_bp
from account import account_bp
from admin import admin_bp

app = Flask(__name__)
CORS(app)
app.secret_key = os.getenv('FLASK_SECRET_KEY')
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY')

socketio = SocketIO(app, manage_session=False)
user_sockets = {}

# Registered blueprints
app.register_blueprint(manager_bp)
app.register_blueprint(sales_bp)
app.register_blueprint(packaging_bp)
app.register_blueprint(transport_bp)
app.register_blueprint(account_bp)
app.register_blueprint(admin_bp)

# Routes
@app.route('/')
def index():
    if 'user_id' in session:
        # User is already logged in, redirect to appropriate dashboard
        return redirect(url_for('dashboard'))
    return render_template('index.html')  # Your main login page

@app.route('/login_page')
def login_page():
    return render_template('index.html')

@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username')
    password = request.form.get('password')

    if not username or not password:
        return jsonify({'success': False, 'message': 'Username and password are required'})

    # Connect to database
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Connection Error'})
    
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Query the database for the user
        cursor.execute("SELECT * FROM users WHERE username = %s AND active = 1", (username,))
        user = cursor.fetchone()
        
        if not user:
            return jsonify({'success': False, 'message': 'User Not Found!'})
        
        # Check password
        stored_password = user['password'] # type: ignore
        if encrypted_password_matches(password, stored_password):
            # Store user info in session
            session['user_id'] = user['id'] # type: ignore
            session['username'] = user['username'] # type: ignore
            session['role'] = user['role'] # type: ignore
            # Determine redirect based on role
            redirect_url = get_redirect_url(user['role']) # type: ignore
            return jsonify({
                'success': True, 
                'message': 'Login successful',
                'redirect': redirect_url
            })
        else:
            return jsonify({'success': False, 'message': 'Invalid Password!'})
    
    except Exception as err:
        print(f"Database error: {err}")
        return jsonify({'success': False, 'message': 'Database error'})
    
    finally:
        cursor.close()
        conn.close()

def encrypted_password_matches(raw_password, stored_encrypted_password):
    # Encrypt the provided password and compare with stored password
    encrypted_input = encrypt_password(raw_password)
    return encrypted_input == stored_encrypted_password

@app.route('/dashboard')
@login_required()
def dashboard():
    # Generic dashboard - redirects to specific role-based dashboard
    role = session.get('role', '')
    return redirect(get_redirect_url(role))

# Admin Dashboard - Only accessible by Admin role
@app.route('/admin/dashboard')
@login_required(['Admin'])
def admin_dashboard():
    return render_template('dashboards/admin/admin.html')


# Packaging Dashboard - Only accessible by Packaging role
@app.route('/packaging/dashboard')
@login_required(['Packaging'])
def packaging_dashboard():
    return render_template('dashboards/packaging/packaging.html')

# Transport Dashboard - Only accessible by Transport role
@app.route('/transport/dashboard')
@login_required(['Transport'])
def transport_dashboard():
    return render_template('dashboards/transport/transport.html')

# Account Dashboard - Only accessible by Account role
@app.route('/account/dashboard')
@login_required(['Account'])
def account_dashboard():
    return render_template('dashboards/account/account.html')

# Builty Dashboard - Only accessible by Builty role
@app.route('/builty/dashboard')
@login_required(['Builty'])
def builty_dashboard():
    return render_template('dashboards/builty/builty.html')

# Retail Dashboard - Only accessible by Retail role
@app.route('/retail/dashboard')
@login_required(['Retail'])
def retail_dashboard():
    return render_template('dashboards/retail/retail.html')

# Logout route
@app.route('/logout')
def logout():
    # Clear the session
    session.clear()
    return redirect(url_for('index'))


@socketio.on('connect')
def handle_connect():
    user_id = session.get('user_id')

    if not user_id:
        disconnect()
        return

    if user_id in user_sockets:
        deactivate_user(user_id)

    user_sockets[user_id] = request.sid


@socketio.on('disconnect')
def handle_disconnect():
    user_id = session.get('user_id')

    if user_id and user_sockets.get(user_id) == request.sid:
        del user_sockets[user_id]

def deactivate_user(user_id):
    # 1. Emit logout event
    if user_id in user_sockets:
        socketio.emit('force_logout', to=user_sockets[user_id])

def deactivate_all_user():
    # 1. Emit logout events
    for i in list(user_sockets.values()):
        socketio.emit('force_logout', to=i)

app.deactivate_user = deactivate_user
app.deactivate_all_user = deactivate_all_user

if __name__ == '__main__':
    # app.run(debug=True,host='0.0.0.0',port=5000)  # Set debug=False in production
    socketio.run(app, debug=True,host='0.0.0.0',port=5005)
    # app.run()