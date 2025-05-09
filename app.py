from flask import Flask, render_template, request, jsonify, flash, url_for, redirect, session
import mysql.connector
from datetime import datetime
from functools import wraps
from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer, AutoModelForCausalLM
import torch
import faiss
import numpy as np
import json
import logging
import mysql

app = Flask(__name__)
app.secret_key = 'qwertyuiop'

# Database configuration
db_config = {
    "pool_name": "mypool",
    "pool_size": 5,
    "host": "localhost",
    "user": "root",
    "password": "12345",
    "database": "car_rental"
}

# Create connection pool
connection_pool = mysql.connector.pooling.MySQLConnectionPool(**db_config)


# Load Q&A knowledge base
try:
    with open("combined_knowledge_base.json", "r") as f:
        knowledge_data = json.load(f)
    
    if not isinstance(knowledge_data, list):
        raise ValueError("Knowledge base must be a list of question-answer pairs")
    
    questions = [item["question"] for item in knowledge_data]
    answers = [item["answer"] for item in knowledge_data]
except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
    logging.error(f"Error loading knowledge base: {str(e)}")
    questions = []
    answers = []

# Load embedding model
embedder = SentenceTransformer('all-MiniLM-L6-v2')
question_embeddings = embedder.encode(questions)

# Build FAISS index
index = faiss.IndexFlatL2(question_embeddings.shape[1])
index.add(np.array(question_embeddings))

# Load DistilGPT2
tokenizer = AutoTokenizer.from_pretrained("distilgpt2")
model = AutoModelForCausalLM.from_pretrained("distilgpt2")

# RAG pipeline
def get_context(user_input):
    user_embedding = embedder.encode([user_input])
    distances, indices = index.search(np.array(user_embedding), k=1)
    
    # Add distance threshold to ensure relevant matches
    if distances[0][0] < 2.0:  # Adjust threshold as needed
        return answers[indices[0][0]]
    return None

def generate_response(user_input):
    context = get_context(user_input)
    
    if context:
        response = f"{context}"
    else:
        response = "I apologize, but I don't have specific information about that. Please contact our customer service for more detailed assistance."
    
    return response

# Fix: Remove the duplicate chat route and keep only one
@app.route("/chat", methods=["POST"])
def chat():
    user_input = request.json.get("message", "").strip()
    if not user_input:
        return jsonify({"response": "Please ask a question."})
    
    try:
        bot_response = generate_response(user_input)
        return jsonify({"response": bot_response})
    except Exception as e:
        logging.error(f"Chat error: {str(e)}")
        return jsonify({"response": "I apologize, but I encountered an error. Please try again."})

# Remove this duplicate route definition
# @app.route("/chat", methods=["POST"])
# def chat():
#     user_input = request.json.get("message")
#     bot_response = generate_response(user_input)
#     return jsonify({"response": bot_response})

# Database connection decorator
def db_connection(f):
    @wraps(f)
    def decorator(*args, **kwargs):
        conn = connection_pool.get_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            result = f(cursor, conn, *args, **kwargs)
            return result
        except Exception as e:
            conn.rollback()
            logging.error(f"Database error: {str(e)}")
            return jsonify({"error": "Database error occurred"}), 500
        finally:
            cursor.close()
            conn.close()
    return decorator

@app.route('/admin')
def admin_page():
    if not session.get('is_admin'):
        return redirect(url_for('admin_login_page'))
    return redirect(url_for('admin_dashboard'))

# Admin authentication decorator
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'):
            if request.is_json:
                return jsonify({"error": "Admin access required"}), 403
            return redirect(url_for('admin_login_page'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/admin/login_page')
def admin_login_page():
    if session.get('is_admin'):
        return redirect(url_for('admin_dashboard'))
    return render_template('admin_login.html')

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    try:
        return render_template('admin_dashboard.html')
    except Exception as e:
        logging.error(f"Admin dashboard error: {str(e)}")
        return jsonify({"error": "Failed to load dashboard"}), 500
    

@app.route('/customers', methods=['GET', 'POST'])
@db_connection
def manage_customers(cursor, conn):
    if request.method == 'GET':
        cursor.execute("SELECT * FROM Customers")
        return jsonify(cursor.fetchall())
    
    if request.method == 'POST':
        data = request.json
        required_fields = ['first_name', 'last_name', 'email', 'phone', 'address']
        if not all(field in data for field in required_fields):
            return jsonify({"error": "Missing required fields"}), 400

        cursor.execute("""
            INSERT INTO Customers (first_name, last_name, email, phone, address) 
            VALUES (%s, %s, %s, %s, %s)
        """, (data['first_name'], data['last_name'], data['email'], data['phone'], data['address']))
        conn.commit()
        return jsonify({"message": "Customer added successfully", "id": cursor.lastrowid})

@app.route('/login', methods=['GET', 'POST'])
@db_connection
def login(cursor, conn):
    if request.method == 'GET':
        if session.get('customer_id'):
            return redirect(url_for('serve_frontend'))
        return render_template('login.html')
    
    try:
        data = request.json
        if not data or 'email' not in data or 'password' not in data:
            return jsonify({"error": "Email and password are required"}), 400

        # Direct comparison with hashed password in database
        cursor.execute("""
            SELECT * FROM Customers 
            WHERE email = %s AND password = SHA2(%s, 256)
        """, (data['email'], data['password']))
        
        customer = cursor.fetchone()
        if customer:
            session['customer_id'] = customer['customer_id']
            session['customer_name'] = f"{customer['first_name']} {customer['last_name']}"
            return jsonify({
                "message": "Login successful",
                "customer_name": session['customer_name']
            })
        
        return jsonify({"error": "Invalid credentials"}), 401
    except Exception as e:
        logging.error(f"Login error: {str(e)}")
        return jsonify({"error": "Login failed"}), 500

@app.route('/cars', methods=['GET'])
@db_connection
def display_cars(cursor, conn):
    cursor.execute("""
        SELECT * FROM Cars 
        WHERE status = 'Available'
        ORDER BY price_per_day
    """)
    cars = cursor.fetchall()
    return render_template('cars.html', cars=cars, 
                          customer_name=session.get('customer_name'),
                          customer_id=session.get('customer_id'))

# Rename the existing cars API endpoint
@app.route('/api/cars', methods=['GET'])
@db_connection
def get_available_cars(cursor, conn):
    cursor.execute("""
        SELECT * FROM Cars 
        WHERE status = 'Available'
        ORDER BY price_per_day
    """)
    return jsonify(cursor.fetchall())

@app.route('/rentals', methods=['POST'])
@db_connection
def rent_car(cursor, conn):
    data = request.json
    required_fields = ['car_id', 'customer_id', 'start_date', 'end_date']
    if not all(field in data for field in required_fields):
        return jsonify({"error": "Missing required fields"}), 400

    try:
        start_date = datetime.strptime(data['start_date'], "%Y-%m-%d")
        end_date = datetime.strptime(data['end_date'], "%Y-%m-%d")
        days = (end_date - start_date).days
        if days < 1:
            return jsonify({"error": "Invalid date range"}), 400

        # Use transaction for atomic operations
        cursor.execute("START TRANSACTION")
        
        cursor.execute("SELECT price_per_day, status FROM Cars WHERE car_id = %s FOR UPDATE", (data['car_id'],))
        car = cursor.fetchone()
        if not car:
            cursor.execute("ROLLBACK")
            return jsonify({"error": "Car not found"}), 404
        if car['status'] != 'Available':
            cursor.execute("ROLLBACK")
            return jsonify({"error": "Car is not available"}), 400

        total_cost = car['price_per_day'] * days

        cursor.execute("""
            INSERT INTO Rentals (customer_id, car_id, start_date, end_date, total_cost, status) 
            VALUES (%s, %s, %s, %s, %s, 'Ongoing')
        """, (data['customer_id'], data['car_id'], data['start_date'], data['end_date'], total_cost))

        cursor.execute("UPDATE Cars SET status = 'Rented' WHERE car_id = %s", (data['car_id'],))
        
        cursor.execute("COMMIT")
        return jsonify({"message": "Car rented successfully", "total_cost": total_cost, "rental_id": cursor.lastrowid})

    except ValueError:
        return jsonify({"error": "Invalid date format"}), 400

@app.route('/complete_rental/<int:rental_id>', methods=['PUT'])
@db_connection
def complete_rental(cursor, conn, rental_id):
    cursor.execute("START TRANSACTION")
    
    cursor.execute("SELECT * FROM Rentals WHERE rental_id = %s FOR UPDATE", (rental_id,))
    rental = cursor.fetchone()
    if not rental or rental['status'] != 'Ongoing':
        cursor.execute("ROLLBACK")
        return jsonify({"error": "Invalid rental or already completed"}), 400

    cursor.execute("UPDATE Rentals SET status = 'Completed' WHERE rental_id = %s", (rental_id,))
    cursor.execute("""
        UPDATE Cars 
        SET status = 'Available' 
        WHERE car_id = (SELECT car_id FROM Rentals WHERE rental_id = %s)
    """, (rental_id,))
    
    cursor.execute("COMMIT")
    return jsonify({"message": "Rental completed"})


@app.route('/')
def serve_frontend():
    return render_template('home.html', 
                         customer_name=session.get('customer_name'),
                         customer_id=session.get('customer_id'))

# Fix the index.html route to serve the home template directly instead of redirecting
#@app.route('/index.html')
#def index_page():
    return render_template('home.html', 
                         customer_name=session.get('customer_name'),
                         customer_id=session.get('customer_id'))

@app.route('/admin/customers')
@admin_required
@db_connection
def admin_view_customers(cursor, conn):
    cursor.execute("""
        SELECT customer_id, first_name, last_name, email, phone, address 
        FROM Customers
        ORDER BY customer_id DESC
    """)
    customers = cursor.fetchall()
    return render_template('admin/customers.html', customers=customers)

@app.route('/admin/rentals/active')
@admin_required
@db_connection
def admin_active_rentals(cursor, conn):
    cursor.execute("""
        SELECT r.*, c.first_name, c.last_name, cars.model
        FROM Rentals r
        JOIN Customers c ON r.customer_id = c.customer_id
        JOIN Cars cars ON r.car_id = cars.car_id
        WHERE r.status = 'Ongoing'
        ORDER BY r.start_date DESC
    """)
    rentals = cursor.fetchall()
    return render_template('admin/active_rentals.html', rentals=rentals)

@app.route('/admin/cars/manage', methods=['GET'])
@admin_required
@db_connection
def admin_manage_cars(cursor, conn):
    cursor.execute("SELECT * FROM Cars ORDER BY car_id DESC")
    cars = cursor.fetchall()
    return render_template('admin/cars.html', cars=cars)

@app.route('/admin/rentals/history')
@admin_required
@db_connection
def rental_history(cursor, conn):
    cursor.execute("""
        SELECT r.*, c.first_name, c.last_name, cars.model
        FROM Rentals r
        JOIN Customers c ON r.customer_id = c.customer_id
        JOIN Cars cars ON r.car_id = cars.car_id
        ORDER BY r.start_date DESC
    """)
    rentals = cursor.fetchall()
    return render_template('admin/rental_history.html', rentals=rentals)

@app.route('/admin/statistics')  # Added @ symbol
@admin_required
@db_connection
def get_statistics(cursor, conn):
    # Get total revenue
    cursor.execute("SELECT COALESCE(SUM(total_cost), 0) as total_revenue FROM Rentals WHERE status = 'Completed'")
    revenue = cursor.fetchone()['total_revenue']

    # Get active rentals count
    cursor.execute("SELECT COUNT(*) as active_rentals FROM Rentals WHERE status = 'Ongoing'")
    active_rentals = cursor.fetchone()['active_rentals']

    # Get available cars count
    cursor.execute("SELECT COUNT(*) as available_cars FROM Cars WHERE status = 'Available'")
    available_cars = cursor.fetchone()['available_cars']

    # Get popular cars (most rented)
    cursor.execute("""
        SELECT c.model, COUNT(r.rental_id) as rental_count
        FROM Cars c
        LEFT JOIN Rentals r ON c.car_id = r.car_id
        GROUP BY c.car_id, c.model
        ORDER BY rental_count DESC
        LIMIT 5
    """)
    popular_cars = cursor.fetchall()

    return render_template('admin/statistics.html', stats={
        "total_revenue": revenue,
        "active_rentals": active_rentals,
        "available_cars": available_cars,
        "popular_cars": popular_cars
    })

@app.route('/admin/search', methods=['POST'])
@admin_required
@db_connection
def admin_search(cursor, conn):
    data = request.json
    search_term = f"%{data['search']}%"
    
    if data['type'] == 'customers':
        cursor.execute("""
            SELECT * FROM Customers 
            WHERE first_name LIKE %s 
            OR last_name LIKE %s 
            OR email LIKE %s
        """, (search_term, search_term, search_term))
    elif data['type'] == 'cars':
        cursor.execute("""
            SELECT * FROM Cars 
            WHERE model LIKE %s 
            OR status LIKE %s
        """, (search_term, search_term))
    elif data['type'] == 'rentals':
        cursor.execute("""
            SELECT r.*, c.first_name, c.last_name, cars.model
            FROM Rentals r
            JOIN Customers c ON r.customer_id = c.customer_id
            JOIN Cars cars ON r.car_id = cars.car_id
            WHERE c.first_name LIKE %s 
            OR c.last_name LIKE %s 
            OR cars.model LIKE %s
        """, (search_term, search_term, search_term))
    
    return jsonify(cursor.fetchall())


@app.route('/admin/cars', methods=['POST', 'PUT', 'DELETE'])
@admin_required
@db_connection
def manage_cars(cursor, conn):
    if request.method == 'POST':
        data = request.json
        required_fields = ['model', 'year', 'price_per_day', 'status']
        if not all(field in data for field in required_fields):
            return jsonify({"error": "Missing required fields"}), 400

        cursor.execute("""
            INSERT INTO Cars (model, year, price_per_day, status) 
            VALUES (%s, %s, %s, %s)
        """, (data['model'], data['year'], data['price_per_day'], data['status']))
        conn.commit()
        return jsonify({"message": "Car added successfully", "id": cursor.lastrowid})

    if request.method == 'PUT':
        data = request.json
        cursor.execute("""
            UPDATE Cars 
            SET model = %s, year = %s, price_per_day = %s, status = %s 
            WHERE car_id = %s
        """, (data['model'], data['year'], data['price_per_day'], data['status'], data['car_id']))
        conn.commit()
        return jsonify({"message": "Car updated successfully"})

    if request.method == 'DELETE':
        car_id = request.args.get('car_id')
        cursor.execute("DELETE FROM Cars WHERE car_id = %s", (car_id,))
        conn.commit()
        return jsonify({"message": "Car deleted successfully"})


@app.route('/admin/login', methods=['GET', 'POST'])
@db_connection
def admin_login(cursor, conn):
    if request.method == 'GET':
        return render_template('admin_login.html')
        
    data = request.json
    if not data or 'username' not in data or 'password' not in data:
        return jsonify({"error": "Username and password are required"}), 400

    try:
        # Hash the password before comparison
        cursor.execute("SELECT * FROM Admins WHERE username = %s AND password = SHA2(%s, 256)", 
                      (data['username'], data['password']))
        admin = cursor.fetchone()
        
        if admin:
            session['is_admin'] = True
            session['admin_username'] = admin['username']
            return jsonify({"message": "Login successful"})
        return jsonify({"error": "Invalid credentials"}), 401
    except Exception as e:
        logging.error(f"Admin login error: {str(e)}")
        return jsonify({"error": "Login failed"}), 500

@app.route('/register', methods=['GET', 'POST'])
@db_connection
def register(cursor, conn):
    if request.method == 'GET':
        return render_template('register.html')
    
    data = request.json
    required_fields = ['first_name', 'last_name', 'email', 'phone', 'address', 'password']
    if not all(field in data for field in required_fields):
        return jsonify({"error": "Missing required fields"}), 400

    try:
        # Add email duplicate check
        cursor.execute("SELECT customer_id FROM Customers WHERE email = %s", (data['email'],))
        if cursor.fetchone():
            return jsonify({"error": "Email already registered"}), 400
            
        # Hash the password before storing
        cursor.execute("SELECT SHA2(%s, 256) as hashed_password", (data['password'],))
        hashed_result = cursor.fetchone()
        hashed_password = hashed_result['hashed_password']
            
        cursor.execute("""
            INSERT INTO Customers (first_name, last_name, email, phone, address, password) 
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (data['first_name'], data['last_name'], data['email'], 
              data['phone'], data['address'], hashed_password))
        conn.commit()
        return jsonify({"message": "Registration successful", "id": cursor.lastrowid})
    except mysql.connector.Error as e:
        logging.error(f"Database error during registration: {str(e)}")
        return jsonify({"error": "Registration failed"}), 500


@app.route('/rent/<int:car_id>', methods=['GET', 'POST'])
@db_connection
def rent_page(cursor, conn, car_id):
    if not session.get('customer_id'):
        return redirect(url_for('login'))
    
    if request.method == 'GET':
        # Get car details to display in the form
        cursor.execute("SELECT * FROM Cars WHERE car_id = %s", (car_id,))
        car = cursor.fetchone()
        if not car:
            return redirect(url_for('serve_frontend'))
        return render_template('rent_form.html', car_id=car_id, car=car)
    
    return redirect(url_for('serve_frontend'))


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('serve_frontend'))



@app.route('/profile', methods=['GET', 'POST'])
@db_connection
def profile(cursor, conn):
    if not session.get('customer_id'):
        return redirect(url_for('login'))
    
    customer_id = session.get('customer_id')
    
    if request.method == 'GET':
        cursor.execute("SELECT customer_id, first_name, last_name, email, phone, address FROM Customers WHERE customer_id = %s", (customer_id,))
        customer = cursor.fetchone()
        if not customer:
            return redirect(url_for('logout'))
        
        # Get rental history
        cursor.execute("""
            SELECT r.*, c.model, c.make 
            FROM Rentals r
            JOIN Cars c ON r.car_id = c.car_id
            WHERE r.customer_id = %s
            ORDER BY r.start_date DESC
        """, (customer_id,))
        rentals = cursor.fetchall()
        
        return render_template('profile.html', 
                              customer=customer, 
                              rentals=rentals,
                              customer_name=session.get('customer_name'))
    
    if request.method == 'POST':
        data = request.json
        
        # Update customer information
        cursor.execute("""
            UPDATE Customers 
            SET first_name = %s, last_name = %s, phone = %s, address = %s
            WHERE customer_id = %s
        """, (data['first_name'], data['last_name'], data['phone'], data['address'], customer_id))
        
        # Update password if provided and old password matches
        if 'password' in data and data['password'] and 'old_password' in data:
            # Verify old password
            cursor.execute("""
                SELECT customer_id FROM Customers 
                WHERE customer_id = %s AND password = SHA2(%s, 256)
            """, (customer_id, data['old_password']))
            
            if cursor.fetchone():
                cursor.execute("UPDATE Customers SET password = SHA2(%s, 256) WHERE customer_id = %s", 
                              (data['password'], customer_id))
            else:
                return jsonify({"error": "Incorrect old password"}), 400
        
        conn.commit()
        
        # Update session name
        session['customer_name'] = f"{data['first_name']} {data['last_name']}"
        
        return jsonify({"message": "Profile updated successfully"})


if __name__ == '__main__':
    logging.basicConfig(level=logging.ERROR)
    app.run(debug=True)
