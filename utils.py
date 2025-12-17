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

def get_invoice_id(invoice_number=None):
    connection = get_db_connection()
    if connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM invoices WHERE invoice_number = %s", (invoice_number,))
        invoice_id = cursor.fetchone()
        cursor.close()
        connection.close()
        if invoice_id:
            return {'status': True, 'invoice_id': invoice_id[0]}
        else:
            return {'status': False, 'invoice_id': None}

    return {'status': False, 'invoice_id': None}

def invoice_detailes(invoice_number=None):

    connection = get_db_connection()
    if connection:
        cursor = connection.cursor(dictionary=True)
        
        querry_1 = """
        
                    SELECT 

                    invoices.invoice_number AS INVOICE,
                    invoices.created_at AS INVOICE_DATE,
                    invoices.delivery_mode AS DELIVERY_MODE,
                    su.username AS SALES_USER,
                    invoices.completed AS COMPLETED,
                    invoices.invoice_number AS INVOICE_NUMBER,
                    invoices.grand_total as GRAND_TOTAL,


                    -- Event Information
                    market_events.name AS EVENT_NAME,
                    market_events.location AS EVENT_LOCATION,
                    market_events.start_date AS EVENT_START_DATE,
                    market_events.end_date AS EVENT_END_DATE,

                    -- Customer Information
                    cu.name AS CUSTOMER_NAME,
                    cu.mobile AS CUSTOMER_MOBILE,
                    cu.pincode AS CUSTOMER_PINCODE,
                    cu.address AS CUSTOMER_ADDRESS,
                    cu.state AS CUSTOMER_STATE,

                    -- Payment Transactions Detailes
                    invoices.payment_mode as PAYMENT_1_MODE,
                    invoices.paid_amount AS PAID_AMOUNT,
                    invoices.left_to_paid AS LEFT_TO_PAID,
                    invoices.payment_note AS PAYMENT_NOTE_1,
                    invoices.gst_included AS GST,
                    live_order_track.payment_confirm_status AS PAYMENT_CONFIRM,
                    live_order_track.payment_note as PAYMENT_NOTE_2,
                    live_order_track.payment_date_time AS PAYMENT_2_DATE,
                    live_order_track.left_to_paid_mode AS PAYMENT_2_MODE,
                    payu.username AS PAYMENT_VERIFY_BY,

                    -- Tracking Stages

                    live_order_track.sales_proceed_for_packing AS SALES,
                    live_order_track.sales_date_time AS SALES_DATE,

                    live_order_track.packing_proceed_for_transport as PACKING,
                    live_order_track.packing_date_time AS PACKING_DATE,
                    packu.username AS PACKING_USER,

                    live_order_track.transport_proceed_for_builty AS TRANSPORT,
                    live_order_track.transport_date_time as TRANSPORT_DATE,
                    invoices.transport_company_name AS TRANSPORT_COMPANY,
                    tu.username AS TRANSPORT_USER,


                    live_order_track.builty_received AS BUILTY,
                    live_order_track.builty_date_time as BUILTY_DATE,
                    bu.username AS BUILTY_USER,

                    live_order_track.verify_by_manager AS VERIFYED,
                    live_order_track.verify_manager_date_time as VERIFYED_DATE,
                    vu.username AS VERIFYED_USER,

                    -- Notes 
                    invoices.sales_note AS SALES_NOTE,
                    live_order_track.packing_note AS PACKING_NOTE,
                    live_order_track.transport_note AS TRANSPORT_NOTE,
                    live_order_track.builty_note AS BUILTY_NOTE,

                    -- Cancellation Details
                    invoices.cancel_order_status AS CANCEL_1,
                    live_order_track.cancel_order_status AS CANCEL_2,
                    cancelled_orders.cancelled_at as CANCEL_AT_DATE,
                    cancelled_orders.reason as CANCEL_REASON,
                    cancelled_orders.confirm_at AS CONFIRN_CANCEL_DATE,
                    cancelled_orders.confirm_by_saler AS CANCEL_CONFIRM_BY_SALER,
                    cancelu.username AS CANCEL_USER
                    
                    FROM invoices
                    JOIN live_order_track 
                    ON invoices.id = live_order_track.invoice_id
                    LEFT JOIN market_events 
                    ON invoices.event_id = market_events.id
                    AND invoices.event_id IS NOT NULL
                    LEFT JOIN cancelled_orders
                    ON invoices.id = cancelled_orders.invoice_id
                    LEFT JOIN buddy cu ON invoices.customer_id = cu.id
                    LEFT JOIN users su ON invoices.invoice_created_by_user_id = su.id
                    LEFT JOIN users payu ON live_order_track.payment_verify_by = payu.id
                    LEFT JOIN users packu ON live_order_track.packing_proceed_by = packu.id
                    LEFT JOIN users tu ON live_order_track.transport_proceed_by = tu.id
                    LEFT JOIN users bu ON live_order_track.builty_proceed_by = bu.id
                    LEFT JOIN users vu ON live_order_track.verify_by_manager_id = vu.id
                    LEFT JOIN users cancelu ON cancelled_orders.cancelled_by = cancelu.id

                    WHERE invoices.invoice_number = %s
                    AND live_order_track.sales_proceed_for_packing = 1;

        """
        
        cursor.execute(querry_1, (invoice_number,))
        data = cursor.fetchone()
        
        if data:
            querry_2 = """

                SELECT 

                products.name AS ITEM_NAME,
                invoice_items.quantity AS ITEM_QTY,
                invoice_items.price AS ITEM_PRICE,
                invoice_items.gst_tax_amount AS ITEM_TAX_AMOUNT,
                invoice_items.total_amount as ITEM_TOTAL_AMOUNT

                from invoices
                LEFT JOIN invoice_items
                ON invoices.id = invoice_items.invoice_id
                JOIN products
                ON invoice_items.product_id = products.id
                WHERE invoices.invoice_number = %s;

            """

            cursor.execute(querry_2, (invoice_number,))
            items = cursor.fetchall()

            querry_3 = """
                
                SELECT 
                packing_images.uploaded_at AS IMAGE_UPLOAD_AT,
                packing_images.image_url AS IMAGE_URL

                from invoices
                JOIN packing_images ON invoices.id = packing_images.invoice_id
                WHERE invoices.invoice_number = %s;

            """

            cursor.execute(querry_3, (invoice_number,))
            images = cursor.fetchall()

            cursor.close()
            connection.close()
            return {'status': True, 'data': data,'items':items,'images':images}
        else:
            cursor.close()
            connection.close()
            return {'status': False, 'data': None}

    return {'status': False, 'data': None}

