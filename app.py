from flask import Flask, request, jsonify, render_template
import sqlite3
from werkzeug.security import check_password_hash
import os

app = Flask(__name__)

# Database setup
def init_db():
    """Initialize the database with a users table if it doesn't exist"""
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL
    )
    ''')
    
    # Add a test user for demonstration
    cursor.execute('''
    INSERT OR IGNORE INTO users (username, password) 
    VALUES ('admin', 'pbkdf2:sha256:150000$KKgd0xN5$4bc40645c94f5696b2a50a3676c5d3e9eb950d26b113959ca225e02eda5c282a')
    ''')
    
    conn.commit()
    conn.close()

# Initialize database when app starts
with app.app_context():
    init_db()

@app.route('/')
def index():
    """Serve the login page"""
    return render_template('index.html')

@app.route('/login', methods=['POST'])
def login():
    """Handle login requests"""
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'success': False, 'message': 'Username and password are required'})
    
    try:
        # Connect to database
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        
        # Query user
        cursor.execute('SELECT username, password FROM users WHERE username = ?', (username,))
        user = cursor.fetchone()
        conn.close()
        
        # Check if user exists and password matches
        if user and check_password_hash(user[1], password):
            return jsonify({
                'success': True, 
                'message': 'Login successful',
                'redirect': '/dashboard'
            })
        else:
            return jsonify({'success': False, 'message': 'Invalid username or password'})
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'An error occurred: {str(e)}'})

@app.route('/dashboard')
def dashboard():
    """A simple dashboard page after successful login"""
    return '<h1>Welcome to Dashboard</h1><p>You have successfully logged in!</p>'

if __name__ == '__main__':
    # Make sure templates directory exists
    if not os.path.exists('templates'):
        os.makedirs('templates')
    
    # Create templates/index.html if it doesn't exist
    if not os.path.exists('templates/index.html'):
        with open('templates/index.html', 'w') as f:
            f.write('''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login Page</title>
    <!-- CSS and JavaScript are included in this file for simplicity -->
    <!-- In production, you should separate these files -->
    <!-- Rest of the HTML content here (copied from the frontend code) -->
</head>
<body>
    <!-- The login form content here -->
</body>
</html>''')
    
    # Run the Flask app
    app.run(debug=True)