from flask import Blueprint, render_template, jsonify, request, session
from utils import get_db_connection, login_required, encrypt_password,decrypt_password
import mysql.connector
from datetime import datetime
import pytz

ist = pytz.timezone('Asia/Kolkata')
now_ist = datetime.now(ist)
formatted_time = now_ist.strftime("%d-%m-%Y %H:%M")



# Create a Blueprint for manager routes
manager_bp = Blueprint('manager', __name__)

# Manager Dashboard


@manager_bp.route('/manager/dashboard')
@login_required('Manager')
def manager_dashboard():
    return render_template('dashboards/manager/manager.html')

# User Management Routes


@manager_bp.route('/manager/users')
@login_required('Manager')
def manager_users():
    return render_template('dashboards/manager/users.html')


@manager_bp.route('/manager/users/data')
@login_required('Manager')
def get_users_data():
    conn = get_db_connection()
    if not conn:
        return jsonify([])

    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
        SELECT id, name, username, role, created_by, updated_by
        FROM users WHERE boss = 0 AND active = 1""")
        
        users = cursor.fetchall()
        return jsonify(users)
    
    finally:
        cursor.close()
        conn.close()


@manager_bp.route('/manager/users/add', methods=['POST'])
@login_required('Manager')
def add_user():
    data = request.json
    name = data.get('name')
    username = data.get('username')
    password = data.get('password')
    role = data.get('role')
    created_by = session.get('username')  # Get current user's ID from session

    if not all([name, username, password, role]):
        return jsonify({'success': False, 'message': 'Required fields are missing'})

    # Encrypt password
    encrypted_password = encrypt_password(password)

    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database connection error'})

    cursor = conn.cursor()

    try:
        # Check if username already exists
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        existing_user = cursor.fetchone()
        if existing_user:
            return jsonify({'success': False, 'message': f'{username}: Username already exists'})

        # Insert new user
        cursor.execute("""
            INSERT INTO users (name, username, password, role, created_by, updated_by, active ,created_at ,updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, 1,%s, %s)
        """, (name, username, encrypted_password, role, created_by, created_by, formatted_time, formatted_time))
        conn.commit()
        return jsonify({'success': True, 'message': 'User added successfully'})
    except mysql.connector.Error as err:
        return jsonify({'success': False, 'message': str(err)})
    finally:
        cursor.close()
        conn.close()


@manager_bp.route('/manager/users/<int:user_id>')
@login_required('Manager')
def get_user(user_id):
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database connection error'})

    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT id, name, username, role ,password
            FROM users
            WHERE id = %s AND boss = 0 AND active = 1
        """, (user_id,))
        user = cursor.fetchone()
        
        user['password'] = decrypt_password(user['password'])
        
        if user:
            return jsonify(user)
        return jsonify({'success': False, 'message': 'User not found'})
    finally:
        cursor.close()
        conn.close()



@manager_bp.route('/manager/users/<int:user_id>/update', methods=['PUT'])
@login_required('Manager')
def update_user(user_id):
    data = request.json
    name = data.get('name')
    username = data.get('username')
    role = data.get('role')
    password = data.get('password')
    updated_by = session.get('username')  # Get current user's username from session
    

    # Validate required fields
    if not all([name, username, role,password]):
        return jsonify({'success': False, 'message': 'Required fields are missing'})
    
    # Get database connection
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database connection error'})
    
    cursor = conn.cursor()
    try:
        # Get current timestamp for updated_at
        formatted_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        password = encrypt_password(password) if password else None
        
        # Update user in database
        cursor.execute("""
            UPDATE users
            SET name = %s, username = %s, role = %s, updated_by = %s, updated_at = %s,password = %s
            WHERE id = %s AND boss = 0 AND active = 1
        """, (name, username,role, updated_by, formatted_time, password,user_id))
        conn.commit()
        return jsonify({'success': True, 'message': 'User updated successfully'})
    except mysql.connector.Error as err:
        return jsonify({'success': False, 'message': str(err)})
    finally:
        cursor.close()
        conn.close()


@manager_bp.route('/manager/users/<int:user_id>/delete', methods=['DELETE'])
@login_required('Manager')
def delete_user(user_id):
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database connection error'})

    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE users
            SET active = 0
            WHERE id = %s AND boss = 0
        """, (user_id,))
        conn.commit()
        return jsonify({'success': True, 'message': 'User deleted successfully'})
    
    except mysql.connector.Error as err:
        return jsonify({'success': False, 'message': str(err)})
    
    finally:
        cursor.close()
        conn.close()
