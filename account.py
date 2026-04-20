from flask import Blueprint, render_template, jsonify, request, session
from utils import get_db_connection, login_required, cancel_order
from datetime import datetime
import pytz

ist = pytz.timezone('Asia/Kolkata')
now_ist = datetime.now(ist)
formatted_time = now_ist.strftime("%d-%m-%Y %H:%M")

# Create a Blueprint for packaging routes
account_bp = Blueprint('account', __name__)

@account_bp.route('/account/dashboard')
@login_required('Account')
def account_dashboard():
    return render_template('dashboards/account/account.html')

@account_bp.route('/account/verify-payment')
@login_required('Account')
def verify_payment():
    return render_template('dashboards/account/verify_payment.html')


class AccountModel:
    def __init__(self):
        self.conn = get_db_connection()
        if not self.conn:
            raise Exception("Database connection failed")
        self.cursor = self.conn.cursor(dictionary=True)
    
    def fetch_orders_payments(self):
        self.cursor.callproc('fetch_orders_and_payments')
        
        results = []
        
        for result in self.cursor.stored_results():
            results = result.fetchall()
        
        return results

    def fetch_orders_payment_details(self, invoiceNumber):
        self.cursor.callproc('get_invoice_payment_details', (invoiceNumber,))
        
        result = None
        
        for res in self.cursor.stored_results():
            result = res.fetchone()
        
        return result

    def fetch_payment_transaction_details(self, transactionNumber):
        self.cursor.callproc('get_payment_transaction_details', (transactionNumber,))
        
        result = None
        
        for res in self.cursor.stored_results():
            result = res.fetchone()
        
        return result

    def payment_recived(self,data):
        try:
            update_query = """
            UPDATE live_order_track SET payment_confirm_status = 1, payment_note = %s, payment_verify_by  = %s,left_to_paid_mode = %s,payment_date_time = NOW() WHERE invoice_id = %s;
            """
            self.cursor.execute(update_query, (data['accountNote'],session.get('user_id'),data['paymentMethod'],data['inv_id'],))
            self.conn.commit() 
            return {"success": True}
            
        except Exception as e:
            self.conn.rollback()  # rollback on connection, not cursor
            return {"success": False,"msg":e}

    def payment_verify(self,data):
        try:
            update_query = """
            
            UPDATE `payment_transations`
            SET payment_verified_by = %s , payment_verified_at = CURRENT_TIMESTAMP,verify_note = %s 
            WHERE active = 1 and payment_verified_by is null and id = %s;
            
            """
            self.cursor.execute(update_query, (session.get('user_id'),data.get('accountNote',None),data['id'],))
            self.conn.commit() 
            return {"success": True}
            
        except Exception as e:
            self.conn.rollback()  # rollback on connection, not cursor
            return {"success": False,"msg":e}

    def get_dasebored_data(self,user_id):

        query = "CALL get_payment_order_stats(%s)"
        self.cursor.execute(query, (user_id,))

        result = self.cursor.fetchone()
        self.conn.close()

        return result

    def close(self):
        self.cursor.close()
        self.conn.close() # type: ignore
    
@account_bp.route('/account/orders-payment-list', methods=['GET'])
@login_required('Account')
def orders_payment_list():
    """
    Fetch the list of orders for the logged-in transport user.
    """    
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'User not logged in'}), 401
        
        my_pay = AccountModel()
        orders = my_pay.fetch_orders_payments()
        
        my_pay.close()

        if not orders:
            return jsonify([]), 200
        
        return jsonify(orders)

    except Exception as e:
        print(f"Error fetching orders: {e}")
        return jsonify({'error': 'Failed to fetch orders'}), 500

    finally:
        my_pay.close()


@account_bp.route('/account/invoice_details/<invoiceNumber>', methods=['GET'])
@login_required('Account')
def invoice_details(invoiceNumber):
    """
    Fetch the details of a specific invoice.
    """    
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'User not logged in'}), 401
        
        my_pay = AccountModel()
        orders = my_pay.fetch_orders_payment_details(invoiceNumber)
        
        my_pay.close()

        if not orders:
            return jsonify([]), 200
        
        return jsonify(orders)

    except Exception as e:
        print(f"Error fetching orders: {e}")
        return jsonify({'error': 'Failed to fetch orders'}), 500

    finally:
        my_pay.close()

@account_bp.route('/account/invoice_details_by_transaction/<transactionNumber>', methods=['GET'])
@login_required('Account')
def invoice_details_by_transaction(transactionNumber):
    """
    Fetch the details of a specific invoice.
    """    
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'User not logged in'}), 401
        
        my_pay = AccountModel()
        orders = my_pay.fetch_payment_transaction_details(transactionNumber)
        
        my_pay.close()

        if not orders:
            return jsonify([]), 200
        
        return jsonify(orders)

    except Exception as e:
        print(f"Error fetching orders: {e}")
        return jsonify({'error': 'Failed to fetch orders'}), 500

    finally:
        my_pay.close()


@account_bp.route('/builty/ready-to-go')
@login_required('Builty')
def send_for_builty():
    return render_template('dashboards/builty/ready_builty.html')

@account_bp.route('/account/payment-recived', methods=['POST'])
@login_required('Account')
def payment_recived():
    try:
        data = request.get_json()

        if not data.get('inv_id') or not data.get('paymentMethod'):
            return jsonify({'error': 'Missing Some IMP Information!'}), 400

        if data.get('paymentMethod') not in ['cash', 'card', 'online','not_paid']:
            return jsonify({'error': 'Invalid Payment Method!'}), 400

        pay_obj = AccountModel()
        response = pay_obj.payment_recived(data)

        if response.get('success'):
            return jsonify({"success": True, "message": "Payment Recived Successfully"}),200

        pay_obj.close()
        return jsonify({"success": False, "error": f"Somthing went wrong!"}),500
    
    except Exception as e:
        return jsonify({"success": False, "error": f"From Server Side: {e}"}), 500

@account_bp.route('/account/payment-verifyed', methods=['POST'])
@login_required('Account')
def payment_verify():
    try:
        data = request.get_json()

        if not data.get('id'):
            return jsonify({'error': 'Missing Some Information!'}), 400

        pay_obj = AccountModel()
        response = pay_obj.payment_verify(data)

        if response.get('success'):
            return jsonify({"success": True, "message": "Payment Recived Successfully"}),200

        pay_obj.close()
        return jsonify({"success": False, "error": f"Somthing went wrong!"}),500
    
    except Exception as e:
        return jsonify({"success": False, "error": f"From Server Side: {e}"}), 500

@account_bp.route('/account/cancel_order', methods=['POST'])
@login_required('Account')
def account_cancel_order():
    try:
        data = request.get_json()
        invoiceNumber = data.get('invoiceNumber')

        if not invoiceNumber:
            return jsonify({"success": False, "message": "Invalid Invoice Number"}), 400

        response = cancel_order(
            invoiceNumber, data.get('reason')
        )

        if response.get('success') == 1:
            return jsonify({"success": True, "message": "Order Cancelled Successfully"}), 200

        return {"success": False, "message": response.get('message')}, 500

    except Exception as e:
        return jsonify({"success": False, "message": "Internal server error"}), 500

@account_bp.route('/account/account-dasebored-orders', methods=['GET'])
@login_required('Account')
def builty_dasebored():
    my_pack = AccountModel()
    try:
        orders = my_pack.get_dasebored_data(session.get('user_id'))
        return jsonify(orders)

    except Exception as e:
        print(f"Error fetching orders: {e}")
        return jsonify({'error': 'Failed to fetch orders'}), 500

    finally:
        my_pack.close()