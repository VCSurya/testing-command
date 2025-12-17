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
                inv.id, 
                inv.invoice_number, 
                inv.customer_id, 
                inv.grand_total, 
                inv.payment_mode, 
                inv.paid_amount, 
                inv.left_to_paid, 
                inv.transport_company_name,
                inv.invoice_created_by_user_id, 
                inv.payment_note, 
                inv.gst_included, 
                inv.created_at, 
                inv.delivery_mode, 
                b.id AS buddy_id, 
                b.name AS customer, 
                b.address, 
                b.state, 
                b.pincode, 
                b.mobile, 

                u.id AS users_id, 
                u.username, 

                up.id AS pu_id, 
                up.username AS pu_name, 

                ut.id AS tu_id, 
                ut.username AS tu_name, 

                ub.id AS bu_id, 
                ub.username AS bu_name, 

                ii.id AS invoices_items_id, 

                ii.product_id, 
                ii.quantity, 
                ii.price, 
                ii.gst_tax_amount, 
                ii.total_amount, 
                ii.created_at, 

                p.id AS products_id, 
                p.name, 

                lot.id AS live_order_track_id,
                lot.sales_proceed_for_packing,
                lot.sales_date_time,
                lot.packing_proceed_for_transport,
                lot.packing_date_time,
                lot.packing_proceed_by,
                lot.transport_proceed_for_builty,
                lot.transport_date_time,
                lot.transport_proceed_by,
                lot.builty_proceed_by,
                lot.builty_received,
                lot.builty_date_time,
                lot.payment_confirm_status,
                lot.cancel_order_status,
                lot.verify_by_manager,
                lot.payment_date_time

                FROM invoices inv 

                LEFT JOIN buddy b ON inv.customer_id = b.id 
                LEFT JOIN invoice_items ii ON inv.id = ii.invoice_id 
                LEFT JOIN products p ON ii.product_id = p.id 
                LEFT JOIN live_order_track lot ON inv.id = lot.invoice_id 

                LEFT JOIN users u ON inv.invoice_created_by_user_id = u.id 
                LEFT JOIN users up ON lot.packing_proceed_by = up.id 
                LEFT JOIN users ut ON lot.transport_proceed_by = ut.id 
                LEFT JOIN users ub ON lot.builty_proceed_by = ub.id 

                where lot.verify_by_manager = 0 
                AND lot.cancel_order_status = 0 
                AND lot.sales_proceed_for_packing = 1 
                AND payment_confirm_status = 0
                AND inv.completed = 0 
                ORDER BY inv.created_at DESC;
        """
        
        self.cursor.execute(query)
        all_order_data = self.cursor.fetchall()
        
        if not all_order_data:
            return []

    
        # Merge products into orders
        merged_orders = self.merge_orders_products(all_order_data)

        return merged_orders

    def payment_recived(self,data):
        try:
            print(data)
            update_query = """
            UPDATE live_order_track SET payment_confirm_status = 1, payment_note = %s, payment_verify_by  = %s,left_to_paid_mode = %s,payment_date_time = NOW() WHERE invoice_id = %s;
            """
            self.cursor.execute(update_query, (data['accountNote'],session.get('user_id'),data['paymentMethod'],data['inv_id'],))
            self.conn.commit() 
            return {"success": True}
            
        except Exception as e:
            self.conn.rollback()  # rollback on connection, not cursor
            return {"success": False,"msg":e}

    def get_dasebored_data(self,user_id):
        query = f"""
            
            SELECT 
                -- Total Draft Builty Order
                COUNT(CASE WHEN sales_proceed_for_packing = 1 
               		AND cancel_order_status = 0 
               		AND payment_confirm_status = 0
          		THEN 1 END) AS total_draft_payment_order,

                -- Total Proceed Builty Order From User
                COUNT(CASE WHEN sales_proceed_for_packing = 1 
                        AND payment_confirm_status = 1 
                        AND cancel_order_status = 0 
                        AND payment_verify_by = {user_id}
                THEN 1 END) AS total_proceed_payment_order_from_user,

                -- Total Today Order Builty By User
                COUNT(CASE WHEN sales_proceed_for_packing = 1 
                        AND payment_confirm_status = 1 
      					AND payment_verify_by = {user_id}
                        AND DATE(payment_date_time) = CURRENT_DATE 
                THEN 1 END) AS total_today_payment_order_by_user

            FROM live_order_track;
            
        """

        self.cursor.execute(query,)
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

        result = get_invoice_id(data.get('inv_id'))
        invoice_id = None
        if result['status']:
            data['inv_id'] = result['invoice_id']
        else:
            return jsonify({'error': 'Invoice not found'}), 404
        
        pay_obj = AccountModel()
        response = pay_obj.payment_recived(data)
        print(response)
        if response.get('success'):
            return jsonify({"success": True, "message": "Payment Recived Successfully"}),200

        pay_obj.close()
        return jsonify({"success": False, "message": f"Somthing went wrong!"}),500
    
    except Exception as e:
        return jsonify({"success": False, "message": f"From Server Side: {e}"}), 500

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