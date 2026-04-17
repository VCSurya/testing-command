import mysql.connector
import os
from functools import wraps
from flask import json,redirect, url_for, session
from dotenv import load_dotenv
from base64 import b64encode
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from Crypto.Util.Padding import unpad
from base64 import b64decode
from functools import wraps
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
    'database': os.getenv('DB_NAME'),
    'port': os.getenv('DB_PORT','3306')
}

def get_db_connection():
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        return connection
    except mysql.connector.Error as err:
        print(f"Database connection error: {err}")
        return None

def login_required(required_roles=None):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('login_page'))
            
            if required_roles:
                user_role = session.get('role')
                
                # Ensure required_roles is iterable
                if isinstance(required_roles, str):
                    roles = [required_roles]
                else:
                    roles = required_roles
                
                if user_role not in roles:
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

def get_invoice_id(invoice_number=None):
    connection = get_db_connection()
    if not connection:
        return {'status': False, 'invoice_id': None}
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM invoices WHERE invoice_number = %s", (invoice_number,))
        invoice_id = cursor.fetchone()
        if invoice_id:
            return {'status': True, 'invoice_id': invoice_id[0]}
        else:
            return {'status': False, 'invoice_id': None}
    finally:
        cursor.close()
        connection.close()

def invoice_detailes(invoice_number=None):
    connection = get_db_connection()
    if not connection:
        return {'status': False, 'data': None}

    try:
        cursor = connection.cursor(dictionary=True)

        cursor.callproc('get_invoice_details', (invoice_number,))

        results = []
        for result in cursor.stored_results():
            results.append(result.fetchall())
                
        if results and results[0]:
            return {
                'status': True,
                'data': results[0][0],   # main data
                'items': results[1],
                'images': results[2],
                'charges': results[3]
            }
        else:
            return {'status': False, 'data': None}

    finally:
        cursor.close()
        connection.close()
                
def delete_user_log(data):
    try:
        with open('static/delete_logs.json', 'r') as f:
            logs = json.load(f)
        logs.append(data)
        with open('static/delete_logs.json', 'w') as f:
            json.dump(logs, f, indent=4)
    except Exception as e:
        print(f"Error in delete_user_log: {e}")

def cancel_order(invoice_number,reason):

    connection = get_db_connection()
    if not connection:
        return {'status': False, 'message': "Database connection failed"}

    try:
        cursor = connection.cursor(dictionary=True)

        cursor.callproc(
            'cancel_order_by_invoice_number',
            (invoice_number, session.get('user_id'), reason)
        )

        response = None
        for result in cursor.stored_results():
            response = result.fetchone()

        return response

    except Exception as e:
        return {"success": False, "message": str(e)}
    
    finally:
        cursor.close()
        connection.close()