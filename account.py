from flask import Blueprint, render_template, jsonify, request, session
from utils import get_db_connection, login_required, encrypt_password,decrypt_password
import mysql.connector
from datetime import datetime
import pytz
from utils import get_invoice_id

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
    
    def get_additional_charges(self,invoice_id):
        
        query = '''
            SELECT charge_name,amount FROM `additional_charges` WHERE invoice_id = %s;
        '''

        self.cursor.execute(query, (invoice_id,))
        additional_charges = self.cursor.fetchall()

        if not additional_charges:
            return []

        return additional_charges

    def merge_orders_products(self,data):
    
        merged = {}

        for item in data:

            # change created_at date formate 
            item['created_at'] = item['created_at'].strftime("%d/%m/%Y %I:%M %p") 
            # passed tracking status with date            
            trackingStatus = 0
            trackingDates = []

            if item['sales_proceed_for_packing']:

                if item['sales_date_time']:
                    item['sales_date_time'] = item['sales_date_time'].strftime("%d/%m/%Y %I:%M %p")
                    trackingDates.append(item['sales_date_time'])
                else:
                    trackingDates.append('')
                trackingStatus = 1                
                
            
                if item['packing_proceed_for_transport']:
                    
                    if item['packing_proceed_for_transport']:
                        item['packing_date_time'] = item['packing_date_time'].strftime("%d/%m/%Y %I:%M %p")
                        trackingDates.append(item['packing_date_time'])
                    else:
                        trackingDates.append('')
                    trackingStatus = 2                
                
                    if item['transport_proceed_for_builty']:
                        
                        if item['transport_proceed_for_builty']:
                            item['transport_date_time'] = item['transport_date_time'].strftime("%d/%m/%Y %I:%M %p")
                            trackingDates.append(item['transport_date_time'])
                        else:
                            trackingDates.append('')
                        trackingStatus = 3
            
                        
                        if item['builty_received']:

                            if item['builty_received']:
                                item['builty_date_time'] = item['builty_date_time'].strftime("%d/%m/%Y %I:%M %p")
                                trackingDates.append(item['builty_date_time'])
                            else:
                                trackingDates.append('')
                            trackingStatus = 4
            
                            if item['verify_by_manager']:
                                
                                if item['verify_by_manager']:
                                    item['verify_manager_date_time'] = item['verify_manager_date_time'].strftime("%d/%m/%Y %I:%M %p")
                                    trackingDates.append(item['verify_manager_date_time'])
                                else:
                                    trackingDates.append('')
                                trackingStatus = 5


            item['trackingStatus'] = trackingStatus
            item['trackingDates'] = trackingDates


            # merge products
            order_id = item["id"]
            product_info = {
                "name": item["name"],
                "qty": item["quantity"],
                "price": float(item["price"]),
                "tax_amount": float(item["gst_tax_amount"]),
                "total": float(item["total_amount"]),
            }

            if order_id not in merged:
                # Create a new entry if the id doesn't exist yet
                merged[order_id] = {
                    **{k: v for k, v in item.items() if k not in ["name", "quantity", "price", "gst_tax_amount", "total_amount", "invoices_items_id", "product_id", "products_id"]},
                    "products": [product_info],
                }
            else:
                # If it already exists, just append the product info
                merged[order_id]["products"].append(product_info)

        return list(merged.values())

    def fetch_orders_payments(self):
        query = f"""
               SELECT 
                0 AS transaction,
                inv.id, 
                inv.invoice_number,
                DATE_FORMAT(
                        CONVERT_TZ(lot.sales_date_time, '+00:00', '+05:30'),
                        '%d/%m/%Y %h:%i %p'
                    ) AS sales_date_time
                FROM invoices inv 
                LEFT JOIN live_order_track lot ON inv.id = lot.invoice_id 
                where lot.verify_by_manager = 0 
                AND lot.cancel_order_status = 0 
                AND lot.sales_proceed_for_packing = 1 
                AND payment_confirm_status = 0
                AND inv.completed = 0 
                ORDER BY inv.created_at DESC;
        """
        
        self.cursor.execute(query)
        all_order_data = self.cursor.fetchall()


        transacton_query = f"""

            SELECT 
            id, 
            DATE_FORMAT(
                        CONVERT_TZ(payment_received_at, '+00:00', '+05:30'),
                        '%d/%m/%Y %h:%i %p'
                    ) AS sales_date_time

            FROM `payment_transations`
            WHERE 
            active = 1
            AND payment_verified_by IS NULL
            AND payment_received_by IS NOT NULL
            ORDER BY payment_received_at DESC;  

        """

        self.cursor.execute(transacton_query,)
        results = self.cursor.fetchall()

        for item in results:
            item["transaction"] = 1
            item["invoice_number"] = ""

        return all_order_data + results 

    def fetch_orders_payment_details(self, invoiceNumber):
        query = """
                SELECT 
                    0 AS transaction,
                    inv.id, 
                    inv.invoice_number, 
                    inv.customer_id, 
                    inv.grand_total, 
                    inv.payment_mode, 
                    inv.paid_amount, 
                    inv.left_to_paid,
                    inv.payment_note, 
                    inv.gst_included, 
                    inv.delivery_mode, 
                    b.name AS customer, 
                    b.mobile,  
                    u.username, 
                    DATE_FORMAT(
                        CONVERT_TZ(lot.sales_date_time, '+00:00', '+05:30'),
                        '%d/%m/%Y %h:%i %p'
                    ) AS sales_date_time

                    FROM invoices inv 

                    LEFT JOIN buddy b ON inv.customer_id = b.id 
                    LEFT JOIN live_order_track lot ON inv.id = lot.invoice_id 

                    LEFT JOIN users u ON inv.invoice_created_by_user_id = u.id 
                    
                    where lot.verify_by_manager = 0 
                    AND lot.cancel_order_status = 0 
                    AND lot.sales_proceed_for_packing = 1 
                    AND payment_confirm_status = 0
                    AND inv.completed = 0 
                    AND inv.id = %s
                ORDER BY inv.created_at DESC;
        """
        
        self.cursor.execute(query, (invoiceNumber,))
        order_data = self.cursor.fetchone()
        print(f"Order Data: {order_data}")  # Debug print
        return order_data

    def fetch_payment_transaction_details(self,transactionNumber):
        
        transacton_query = """

            SELECT 
            pt.id, 
            pt.payment_method,
            pt.payment_received_at,
            ur.username as received_by,
            pt.amount,
            pt.note,
            b.name as customer_name,
            b.mobile as customer_mobile
            
            FROM `payment_transations` pt
            LEFT JOIN users ur ON ur.id = payment_received_by
            LEFT JOIN buddy b ON b.id = pt.customer_id 
            WHERE 
            pt.active = 1
            AND pt.payment_verified_by IS NULL
            AND pt.payment_received_by IS NOT NULL
            AND pt.id = %s
            ORDER BY pt.payment_received_at DESC;  

        """

        self.cursor.execute(transacton_query, (transactionNumber,))
        results = self.cursor.fetchall()
        
        formatted_results = []

        for item in results:
            received_at = item.get("payment_received_at")

            formatted_item = {
                'transaction': 1,
                "id": f"{item['id']}",
                "amount": float(item["amount"]),
                "mode": item["payment_method"],
                "received_by": item["received_by"],
                "customer_mobile": item["customer_mobile"],
                "customer_name": item["customer_name"],
                "note":item["note"],
                "received_date": received_at.strftime("%d/%m/%Y") if received_at else None,
                "received_time": received_at.strftime("%I:%M %p") if received_at else None,
            }

            formatted_results.append(formatted_item)

        if not formatted_results:
            formatted_results = []

        return formatted_results[0]


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

    def cancel_order(self,data):
        try:
            
            lot_id_querry = """

            SELECT live_order_track.id as lot_id,live_order_track.invoice_id from live_order_track WHERE live_order_track.invoice_id = (SELECT invoices.id from invoices WHERE invoice_number = %s);
            """
            self.cursor.execute(lot_id_querry, (data.get('invoiceNumber'),))
            result = self.cursor.fetchone()
            
            if result.get('lot_id') is None or result.get('lot_id') == "":
                return {"success": False, "message": f"Somthing went wrong to cancel order"}
            
            if result.get('invoice_id') is None or result.get('invoice_id') == "":
                return {"success": False, "message": f"Somthing went wrong to cancel order"}
            

            update_query = """

            UPDATE live_order_track
            SET cancel_order_status = 1
            WHERE id = %s;
            """
            self.cursor.execute(update_query, (result.get('lot_id'),))
            self.conn.commit()  # commit on connection, not cursor
            
            update_query = """

            UPDATE invoices
            SET cancel_order_status = 1
            WHERE id = %s;
            """
            self.cursor.execute(update_query, ((result.get('invoice_id'),)))
            self.conn.commit()  # commit on connection, not cursor
            

            insert_query = """
                
                INSERT INTO cancelled_orders (
                    invoice_id,cancelled_by, reason,live_order_track_id 
                ) VALUES (%s, %s, %s,%s)
            """

            self.cursor.execute(insert_query, (result.get('invoice_id'),session.get('user_id'),data.get('reason'),result.get('lot_id'),))
            self.conn.commit()  # commit on connection, not cursor
            
            return {"success": True, "message": f"Order successfully Cancel"}
            
        except Exception as e:
            self.conn.rollback()  # rollback on connection, not cursor
            return {"success": False, "message": f"Somthing went wrong to cancel order"}

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
def cancel_order():
    try:
        data = request.get_json()
        invoiceNumber = data.get('invoiceNumber') #reason
        if not invoiceNumber or not data.get('invoiceNumber'):
            return jsonify({"success": False, "message": "Invalid Order!"}), 400
        
        for_cancel_order = AccountModel()
        response = for_cancel_order.cancel_order(data)

        if response.get('success'):
            return jsonify({"success": True, "message": "Order Cancelled Successfully"}), 200
        
        for_cancel_order.close()
        return {"success": False, "message": f"Somthing went wrong!"},500

    except Exception as e:
        return jsonify({"success": False, "message": f"From Server Side: {e}"}), 500

@account_bp.route('/account/account-dasebored-orders', methods=['GET'])
@login_required('Account')
def builty_dasebored():
    try:
        my_pack = AccountModel()
        orders = my_pack.get_dasebored_data(session.get('user_id'))
        return jsonify(orders)

    except Exception as e:
        print(f"Error fetching orders: {e}")
        return jsonify({'error': 'Failed to fetch orders'}), 500

    finally:
        my_pack.close()  