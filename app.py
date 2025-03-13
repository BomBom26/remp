from flask import Flask, request, render_template, redirect, url_for, session, flash
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
            c.execute("INSERT INTO products (name, stock) VALUES (?, ?)", (name, int(stock)))
            conn.commit()
            conn.close()
            return '<script>alert("Товар додано!"); window.location="/";</script>'
        except sqlite3.IntegrityError:
            conn.close()
            return '<script>alert("Товар з такою назвою вже існує!"); window.location="/add_product";</script>'
    return render_template('add_product.html')

# Сторінка редагування товару
@app.route('/edit_product/<int:product_id>', methods=['GET', 'POST'])
@login_required
def edit_product(product_id):
    conn = sqlite3.connect('business.db')
    c = conn.cursor()
    if request.method == 'POST':
        stock = request.form['stock']
        c.execute("UPDATE products SET stock = ? WHERE id = ?", (int(stock), product_id))
        conn.commit()
        conn.close()
        return '<script>alert("Запас оновлено!"); window.location="/";</script>'
    c.execute("SELECT name, stock FROM products WHERE id = ?", (product_id,))
    product = c.fetchone()
    conn.close()
    if product:
        return render_template('edit_product.html', product=product, product_id=product_id)
    return '<script>alert("Товар не знайдено!"); window.location="/";</script>'

# Сторінка видалення товару
@app.route('/delete_product/<int:product_id>', methods=['GET'])
@login_required
def delete_product(product_id):
    conn = sqlite3.connect('business.db')
    c = conn.cursor()
    try:
        c.execute("SELECT name FROM products WHERE id = ?", (product_id,))
        product = c.fetchone()
        if product:
            c.execute("DELETE FROM products WHERE id = ?", (product_id,))
            conn.commit()
            conn.close()
            return '<script>alert("Товар видалено!"); window.location="/";</script>'
        else:
            conn.close()
            return '<script>alert("Товар не знайдено!"); window.location="/";</script>'
    except Exception as e:
        conn.close()
        return f'<script>alert("Помилка: {str(e)}"); window.location="/";</script>'

# Сторінка зняття коштів з пошти
@app.route('/withdraw', methods=['GET', 'POST'])
@login_required
def withdraw():
    conn = sqlite3.connect('business.db')
    c = conn.cursor()
    if request.method == 'POST':
        date = request.form['date']
        amount = float(request.form['amount'])
        c.execute("INSERT INTO withdrawals (date, amount) VALUES (?, ?)", (date, amount))
        conn.commit()
        conn.close()
        return '<script>alert("Зняття додано!"); window.location="/";</script>'
    c.execute("SELECT SUM(amount) FROM withdrawals")
    total_withdrawn = c.fetchone()[0] or 0
    conn.close()
    return render_template('withdraw.html', total_withdrawn=total_withdrawn)

# Сторінка історії запасів
@app.route('/stock_history', methods=['GET', 'POST'])
@login_required
def stock_history():
    conn = sqlite3.connect('business.db')
    c = conn.cursor()
    
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    
    if request.method == 'POST':
        start_date = request.form.get('start_date', start_date)
        end_date = request.form.get('end_date', end_date)
    
    c.execute("SELECT date, product_name, change_amount, action, sale_id FROM stock_history WHERE date BETWEEN ? AND ? ORDER BY date", 
              (start_date, end_date))
    history = c.fetchall()
    
    conn.close()
    return render_template('stock_history.html', history=history, start_date=start_date, end_date=end_date)

# Експорт звіту
@app.route('/export_report', methods=['GET', 'POST'])
@login_required
def export_report():
    conn = sqlite3.connect('business.db')
    c = conn.cursor()
    
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    
    if request.method == 'POST':
        start_date = request.form.get('start_date', start_date)
        end_date = request.form.get('end_date', end_date)
    
    c.execute("SELECT client_name, instagram, ttn, products, prepayment, cod, status, date FROM sales WHERE date BETWEEN ? AND ? ORDER BY date", 
              (start_date, end_date))
    sales = c.fetchall()
    
    c.execute("SELECT description, amount, date FROM expenses WHERE date BETWEEN ? AND ?", (start_date, end_date))
    expenses = c.fetchall()
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    writer.writerow(['Тип', 'Дата', 'Ім’я', 'Instagram', 'ТТН', 'Товар', 'Передоплата (грн)', 'На пошті (грн)', 'Статус'])
    for sale in sales:
        writer.writerow(['Продаж', sale[7], sale[0], sale[1], sale[2], sale[3], sale[4], sale[5], sale[6]])
    
    writer.writerow(['Тип', 'Дата', 'Опис', 'Сума (грн)'])
    for expense in expenses:
        writer.writerow(['Витрата', expense[2], expense[0], expense[1]])
    
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode()),
        mimetype='text/csv',
        as_attachment=True,
        attachment_filename=f'report_{start_date}_to_{end_date}.csv'
    )

# Зміна статусу замовлення
@app.route('/change_status/<int:sale_id>', methods=['GET', 'POST'])
@login_required
def change_status(sale_id):
    conn = sqlite3.connect('business.db')
    c = conn.cursor()
    try:
        if request.method == 'POST':
            new_status = request.form['status']
            c.execute("SELECT status, products, date FROM sales WHERE id = ?", (sale_id,))
            result = c.fetchone()
            if not result:
                conn.close()
                return '<script>alert("Замовлення не знайдено!"); window.location="/purchases";</script>'
            current_status, products, sale_date = result
            if new_status == 'Повернення' and current_status != 'Повернення':
                product_list = products.split(", ") if products else []
                for product in product_list:
                    name_qty = product.split(" (")
                    name = name_qty[0]
                    qty = int(name_qty[1].split(" ")[0]) if len(name_qty) > 1 else 0
                    c.execute("UPDATE products SET stock = stock + ? WHERE name = ?", (qty, name))
                    c.execute("INSERT INTO stock_history (date, product_name, change_amount, action, sale_id) VALUES (?, ?, ?, ?, ?)", 
                              (sale_date, name, qty, 'Повернення', sale_id))
            c.execute("UPDATE sales SET status = ? WHERE id = ?", (new_status, sale_id))
            conn.commit()
            conn.close()
            return '<script>alert("Статус змінено!"); window.location="/purchases";</script>'
        c.execute("SELECT client_name, products, status FROM sales WHERE id = ?", (sale_id,))
        sale = c.fetchone()
        if sale:
            return render_template('change_status.html', sale=sale, sale_id=sale_id)
        return '<script>alert("Замовлення не знайдено!"); window.location="/purchases";</script>'
    except Exception as e:
        conn.close()
        return f'<script>alert("Помилка: {str(e)}"); window.location="/purchases";</script>'

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=8080)
