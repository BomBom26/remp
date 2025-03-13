from flask import Flask, request, render_template, redirect, url_for, session, flash, send_file
import sqlite3
from datetime import datetime, timedelta
import csv
import io

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Змініть на унікальний ключ (наприклад, 'mysecretkey123')

# Пароль для доступу до сайту
SITE_PASSWORD = '12345678'

# Ініціалізація бази даних
def init_db():
    conn = sqlite3.connect('business.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS products 
                 (id INTEGER PRIMARY KEY, name TEXT UNIQUE, stock INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS sales 
                 (id INTEGER PRIMARY KEY, date TEXT, client_name TEXT, instagram TEXT, 
                  post_office TEXT, prepayment REAL, cod REAL, products TEXT, ttn TEXT, 
                  status TEXT, comment TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS expenses 
                 (id INTEGER PRIMARY KEY, date TEXT, amount REAL, description TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS withdrawals 
                 (id INTEGER PRIMARY KEY, date TEXT, amount REAL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS stock_history 
                 (id INTEGER PRIMARY KEY, date TEXT, product_name TEXT, change_amount INTEGER, 
                  action TEXT, sale_id INTEGER)''')
    conn.commit()
    conn.close()

# Функція для перевірки авторизації
def login_required(f):
    def wrap(*args, **kwargs):
        if 'logged_in' not in session or not session['logged_in']:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    wrap.__name__ = f.__name__
    return wrap

# Маршрут для входу
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form['password']
        if password == SITE_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('index'))
        else:
            flash('Неправильний пароль')
    return render_template('login.html')

# Маршрут для виходу
@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    flash('Ви вийшли з системи')
    return redirect(url_for('login'))

# Головна сторінка
@app.route('/', methods=['GET', 'POST'])
@login_required
def index():
    conn = sqlite3.connect('business.db')
    c = conn.cursor()
    
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    
    if request.method == 'POST':
        start_date = request.form.get('start_date', start_date)
        end_date = request.form.get('end_date', end_date)
    
    c.execute("SELECT name, stock, id FROM products")
    products = c.fetchall()
    
    # Перевірка низького запасу
    low_stock_products = [p for p in products if p[1] < 5]
    
    c.execute("SELECT COUNT(*) FROM sales WHERE status = 'Очікує' AND date BETWEEN ? AND ?", (start_date, end_date))
    on_post = c.fetchone()[0] or 0
    
    c.execute("SELECT SUM(prepayment + cod) FROM sales WHERE status = 'Очікує' AND date BETWEEN ? AND ?", (start_date, end_date))
    on_post_cost = c.fetchone()[0] or 0
    
    c.execute("SELECT SUM(amount) FROM withdrawals WHERE date BETWEEN ? AND ?", (start_date, end_date))
    withdrawn = c.fetchone()[0] or 0
    
    c.execute("SELECT SUM(prepayment + cod) FROM sales WHERE status = 'Забрали' AND date BETWEEN ? AND ?", (start_date, end_date))
    total_income = c.fetchone()[0] or 0
    
    conn.close()
    return render_template('index.html', products=products, on_post=on_post, on_post_cost=on_post_cost, 
                          total_income=total_income, start_date=start_date, end_date=end_date, 
                          withdrawn=withdrawn, low_stock_products=low_stock_products)

# Сторінка замовлень
@app.route('/purchases', methods=['GET', 'POST'])
@login_required
def purchases():
    conn = sqlite3.connect('business.db')
    c = conn.cursor()
    
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    status_filter = request.form.get('status_filter', 'all')
    
    if request.method == 'POST':
        if 'start_date' in request.form:
            start_date = request.form.get('start_date', start_date)
            end_date = request.form.get('end_date', end_date)
            status_filter = request.form.get('status_filter', 'all')
        else:
            # Додавання замовлення
            date = request.form['date']
            client_name = request.form['client_name']
            instagram = request.form['instagram']
            post_office = request.form['post_office']
            prepayment = float(request.form.get('prepayment', 0))
            cod = float(request.form.get('cod', 0))
            products = request.form.getlist('products')
            ttn = request.form.get('ttn', '')
            status = request.form.get('status', 'Очікує')
            comment = request.form.get('comment', '')
            products_str = ", ".join(products) if products else ''
            c.execute("INSERT INTO sales (date, client_name, instagram, post_office, prepayment, cod, products, ttn, status, comment) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                      (date, client_name, instagram, post_office, prepayment, cod, products_str, ttn, status, comment))
            for product in products:
                name, qty = product.split(" (")[0], int(product.split(" (")[1].split(" ")[0])
                if status != 'Повернення':
                    c.execute("UPDATE products SET stock = stock - ? WHERE name = ?", (qty, name))
                    c.execute("INSERT INTO stock_history (date, product_name, change_amount, action, sale_id) VALUES (?, ?, ?, ?, ?)", 
                              (date, name, -qty, 'Продаж', c.lastrowid))
            conn.commit()
    
    query = "SELECT id, date, client_name, instagram, post_office, products, prepayment, cod, ttn, status, comment FROM sales WHERE date BETWEEN ? AND ?"
    params = [start_date, end_date]
    if status_filter != 'all':
        query += " AND status = ?"
        params.append(status_filter)
    query += " ORDER BY date"
    c.execute(query, params)
    sales = c.fetchall()
    
    c.execute("SELECT name, stock FROM products")
    products = c.fetchall()
    product_counts = {}
    for sale in sales:
        for product in sale[5].split(", ") if sale[5] else []:
            name = product.split(" (")[0]
            product_counts[name] = product_counts.get(name, 0) + 1
    
    totals = {'Забрали': 0, 'Очікує': 0, 'Повернення': 0}
    for sale in sales:
        if sale[9] in totals:
            totals[sale[9]] += sale[6] + sale[7]
    
    conn.close()
    return render_template('purchases.html', sales=sales, products=products, product_counts=product_counts, 
                          totals=totals, start_date=start_date, end_date=end_date, status_filter=status_filter)

# Сторінка статистики
@app.route('/reports', methods=['GET', 'POST'])
@login_required
def reports():
    conn = sqlite3.connect('business.db')
    c = conn.cursor()
    
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    
    if request.method == 'POST':
        start_date = request.form.get('start_date', start_date)
        end_date = request.form.get('end_date', end_date)
    
    c.execute("SELECT date, client_name, instagram, ttn, products, prepayment, cod, status FROM sales WHERE date BETWEEN ? AND ? ORDER BY date", 
              (start_date, end_date))
    sales = c.fetchall()
    
    c.execute("SELECT date, description, amount FROM expenses WHERE date BETWEEN ? AND ?", (start_date, end_date))
    expenses = c.fetchall()
    
    conn.close()
    return render_template('reports.html', sales=sales, expenses=expenses, start_date=start_date, end_date=end_date)

# Сторінка додавання витрат
@app.route('/add_expense', methods=['GET', 'POST'])
@login_required
def add_expense():
    if request.method == 'POST':
        date = request.form['date']
        amount = float(request.form['amount'])
        description = request.form['description']
        conn = sqlite3.connect('business.db')
        c = conn.cursor()
        c.execute("INSERT INTO expenses (date, amount, description) VALUES (?, ?, ?)", (date, amount, description))
        conn.commit()
        conn.close()
        return '<script>alert("Витрати додано!"); window.location="/";</script>'
    return render_template('add_expense.html')

# Сторінка додавання товару
@app.route('/add_product', methods=['GET', 'POST'])
@login_required
def add_product():
    if request.method == 'POST':
        name = request.form['name']
        stock = request.form['stock']
        conn = sqlite3.connect('business.db')
        c = conn.cursor()
        try:
            c.execute("INSERT INTO products (name, stock) VALUES (?, ?)", (name, in
