import mysql.connector
import os
from functools import wraps
from flask import redirect, url_for, session
from dotenv import load_dotenv
from base64 import b64encode
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from Crypto.Util.Padding import unpad
from base64 import b64decode

# Load environment variables
load_dotenv()

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

def get_db_connection():
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        return connection
    except mysql.connector.Error as err:
        print(f"Database connection error: {err}")
        return None

def login_required(required_role=None):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('login_page'))
            
            if required_role:
                user_role = session.get('role')
                if user_role != required_role:
                    return redirect(get_redirect_url(user_role))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def get_redirect_url(role):
    role_redirects = {
        'Admin': '/admin/dashboard',
        'Manager': '/manager/dashboard',
        'Sales': '/sales/dashboard',
        'Packaging': '/packaging/dashboard',
        'Transport': '/transport/dashboard',
        'Account': '/account/dashboard',
        'Builty': '/builty/dashboard',
        'Retail': '/retail/dashboard'
    }
    return role_redirects.get(role, '/dashboard')

def encrypt_password(raw_password):
    # Create an AES cipher
    key = SECRET_KEY.encode('utf-8')[:16].ljust(16, b'\0')
    iv = SECRET_IV.encode('utf-8')[:16].ljust(16, b'\0')
    cipher = AES.new(key, AES.MODE_CBC, iv)
    
    # Pad the password and encrypt it
    padded_password = pad(raw_password.encode('utf-8'), AES.block_size)
    encrypted_password = cipher.encrypt(padded_password)
    
    # Return base64 encoded string
    return b64encode(encrypted_password).decode('utf-8') 

def decrypt_password(encrypted_password):
    # Prepare key and IV
    key = SECRET_KEY.encode('utf-8')[:16].ljust(16, b'\0')
    iv = SECRET_IV.encode('utf-8')[:16].ljust(16, b'\0')
    cipher = AES.new(key, AES.MODE_CBC, iv)
    
    # Decode from base64 and decrypt
    encrypted_bytes = b64decode(encrypted_password)
    decrypted_padded = cipher.decrypt(encrypted_bytes)
    
    # Unpad and return the original password
    return unpad(decrypted_padded, AES.block_size).decode('utf-8')