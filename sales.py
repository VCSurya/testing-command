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

sales_bp.add_url_rule('/sales/', view_func=sales_dashboard)

