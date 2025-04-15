from flask import Blueprint, render_template, jsonify, request, session
from utils import get_db_connection, login_required, encrypt_password,decrypt_password
import mysql.connector
from datetime import datetime
import pytz

ist = pytz.timezone('Asia/Kolkata')
now_ist = datetime.now(ist)
formatted_time = now_ist.strftime("%d-%m-%Y %H:%M")



# Create a Blueprint for manager routes
sales_bp = Blueprint('sales', __name__)

# Manager Dashboard


@sales_bp.route('/sales/dashboard')
@login_required('Sales')
def sales_dashboard():
    return render_template('dashboards/sales/main.html')

@sales_bp.route('/sales/sell')
@login_required('Sales')
def sales():
    return render_template('dashboards/sales/sell.html')

@sales_bp.route('/sales/customers', methods=['GET'])
def get_customers():
    conn = get_db_connection()
    if not conn:
        return jsonify([]), 500  # Return HTTP 500 if DB connection fails

    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM buddy")
        customers = cursor.fetchall()
        return jsonify([{
            'id': c['id'],
            'name': c['name'],
            'mobile': c['mobile'],
            'address': c['address']
        } for c in customers])
    except Exception as e:
        print(f"Error fetching customers: {e}")
        return jsonify({'error': 'Failed to fetch customers'}), 500
    finally:
        cursor.close()
        conn.close()

@sales_bp.route('/sales/products')
def get_products():
    conn = get_db_connection()
    if not conn:
        return jsonify([]), 500  # Return HTTP 500 if DB connection fails

    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM products")
        products = cursor.fetchall()
        return jsonify([{
            'id': p['id'],
            'name': p['name'],
            'price': float(p['selling_price'])
        } for p in products])
    
    except Exception as e:
        print(f"Error fetching customers: {e}")
        return jsonify({'error': 'Failed to fetch customers'}), 500
    
    finally:
        cursor.close()
        conn.close()
    

sales_bp.add_url_rule('/sales/', view_func=sales_dashboard)

