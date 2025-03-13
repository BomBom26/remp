from flask import Flask, request, render_template, redirect, url_for, session, flash
import sqlite3
from datetime import datetime, timedelta

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

# Видалення товару
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

# Додавання товару
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

# Редагування товару
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

# Решта маршрутів (purchases, reports тощо) оновлюються аналогічно
# ... (додайте @login_required до всіх маршрутів, які потрібно захистити)

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=8080)
