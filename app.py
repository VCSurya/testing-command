from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import mysql.connector
from functools import wraps
import hashlib
import os
from base64 import b64encode, b64decode
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from dotenv import load_dotenv
from manager import manager_bp
from sales import sales_bp
from packaging import packaging_bp
from transport import transport_bp
from builty import builty_bp
from account import account_bp
from utils import get_db_connection, login_required, encrypt_password, get_redirect_url

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY')

# Constants for encryption
SECRET_KEY = os.getenv('ENCRYPTION_SECRET_KEY')
SECRET_IV = os.getenv('ENCRYPTION_SECRET_IV')

# Database configuration
DB_CONFIG = {
    'host': os.getenv('DB_HOST'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_NAME')
}

# Function to get database connection
def get_db_connection():
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        return connection
    except mysql.connector.Error as err:
        print(f"Database connection error: {err}")
        return None

# Password encryption/decryption functions
def encrypt_password(raw_password):
    # Create an AES cipher
    key = SECRET_KEY.encode('utf-8')[:16].ljust(16, b'\0') # type: ignore
    iv = SECRET_IV.encode('utf-8')[:16].ljust(16, b'\0') # type: ignore
    cipher = AES.new(key, AES.MODE_CBC, iv)
    
    # Pad the password and encrypt it
    padded_password = pad(raw_password.encode('utf-8'), AES.block_size)
    encrypted_password = cipher.encrypt(padded_password)
    
    # Return base64 encoded string
    return b64encode(encrypted_password).decode('utf-8')

def decrypt_password(encrypted_password):
    try:
        # Create an AES cipher
        key = SECRET_KEY.encode('utf-8')[:16].ljust(16, b'\0') # type: ignore
        iv = SECRET_IV.encode('utf-8')[:16].ljust(16, b'\0') # type: ignore
        cipher = AES.new(key, AES.MODE_CBC, iv)
        
        # Decode base64 and decrypt
        encrypted_bytes = b64decode(encrypted_password)
        decrypted_password = unpad(cipher.decrypt(encrypted_bytes), AES.block_size)
        
        return decrypted_password.decode('utf-8')
    except Exception as e:
        print(f"Decryption error: {e}")
        return None

# Enhanced login required decorator with role checking
def login_required(required_role=None):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Check if user is logged in
            if 'user_id' not in session:
                return redirect(url_for('login_page'))
            
            # If role is specified, check if user has the required role
            if required_role:
                user_role = session.get('role')
                if user_role != required_role:
                    # Redirect to user's own dashboard if trying to access another role's dashboard
                    return redirect(get_redirect_url(user_role))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Register the manager blueprint
app.register_blueprint(manager_bp)
app.register_blueprint(sales_bp)
app.register_blueprint(packaging_bp)
app.register_blueprint(transport_bp)
app.register_blueprint(builty_bp)
app.register_blueprint(account_bp)
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
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
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
    
    except mysql.connector.Error as err:
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
@login_required('Admin')
def admin_dashboard():
    return render_template('dashboards/admin/admin.html')


# Packaging Dashboard - Only accessible by Packaging role
@app.route('/packaging/dashboard')
@login_required('Packaging')
def packaging_dashboard():
    return render_template('dashboards/packaging/packaging.html')

# Transport Dashboard - Only accessible by Transport role
@app.route('/transport/dashboard')
@login_required('Transport')
def transport_dashboard():
    return render_template('dashboards/transport/transport.html')

# Account Dashboard - Only accessible by Account role
@app.route('/account/dashboard')
@login_required('Account')
def account_dashboard():
    return render_template('dashboards/account/account.html')

# Builty Dashboard - Only accessible by Builty role
@app.route('/builty/dashboard')
@login_required('Builty')
def builty_dashboard():
    return render_template('dashboards/builty/builty.html')

# Retail Dashboard - Only accessible by Retail role
@app.route('/retail/dashboard')
@login_required('Retail')
def retail_dashboard():
    return render_template('dashboards/retail/retail.html')

# Logout route
@app.route('/logout')
def logout():
    # Clear the session
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True,host='0.0.0.0',port=5000)  # Set debug=False in production