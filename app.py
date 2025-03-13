from flask import Flask, request, render_template
import sqlite3
from datetime import datetime, timedelta

app = Flask(__name__)

# Ініціалізація бази даних
def init_db():
    conn = sqlite3.connect('business.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS products 
                 (id INTEGER PRIMARY KEY, name TEXT UNIQUE, stock INTEGER)''')  # Додано UNIQUE для назви
    c.execute('''CREATE TABLE IF NOT EXISTS sales 
                 (id INTEGER PRIMARY KEY, date TEXT, client_name TEXT, instagram TEXT, 
                  post_office TEXT, prepayment REAL, cod REAL, products TEXT, ttn TEXT, 
                  status TEXT, comment TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS expenses 
                 (id INTEGER PRIMARY KEY, date TEXT, amount REAL, description TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS withdrawals 
                 (id INTEGER PRIMARY KEY, date TEXT, amount REAL)''')
    # Додаємо початкові товари, якщо таблиця порожня
    c.execute("SELECT COUNT(*) FROM products")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO products (name, stock) VALUES ('Щітка A', 50)")
        c.execute("INSERT INTO products (name, stock) VALUES ('Щітка B', 30)")
        c.execute("INSERT INTO products (name, stock) VALUES ('Щітка C', 20)")
    conn.commit()
    conn.close()

# Головна сторінка
@app.route('/', methods=['GET', 'POST'])
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
                          total_income=total_income, start_date=start_date, end_date=end_date, withdrawn=withdrawn)

# Сторінка "Покупки"
@app.route('/purchases', methods=['GET', 'POST'])
def purchases():
    conn = sqlite3.connect('business.db')
    c = conn.cursor()
    
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    
    if request.method == 'POST':
        if 'start_date' in request.form:
            start_date = request.form.get('start_date', start_date)
            end_date = request.form.get('end_date', end_date)
        else:
            # Додавання покупки
            date = request.form['date']
            client_name = request.form['client_name']
            instagram = request.form['instagram']
            post_office = request.form['post_office']
            prepayment = float(request.form['prepayment'] or 0)
            cod = float(request.form['cod'] or 0)
            ttn = request.form['ttn']
            status = request.form['status']
            comment = request.form['comment']
            
            # Перевірка запасів товару
            product_names = request.form.getlist('product')
            quantities = request.form.getlist('quantity')
            products = []
            for name, qty in zip(product_names, quantities):
                if name and int(qty) > 0:
                    c.execute("SELECT stock FROM products WHERE name = ?", (name,))
                    stock = c.fetchone()
                    if stock is None or stock[0] < int(qty) and status != 'Повернення':
                        conn.close()
                        return f'<script>alert("Недостатньо товару {name} на складі! Залишок: {stock[0] if stock else 0} шт."); window.location="/purchases";</script>'
                    products.append(f"{name} ({qty} шт.)")
                    if status != 'Повернення':
                        c.execute("UPDATE products SET stock = stock - ? WHERE name = ?", (int(qty), name))
            
            products_str = ", ".join(products)
            c.execute("INSERT INTO sales (date, client_name, instagram, post_office, prepayment, cod, products, ttn, status, comment) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", 
                      (date, client_name, instagram, post_office, prepayment, cod, products_str, ttn, status, comment))
            conn.commit()
            conn.close()
            return '<script>alert("Покупку додано!"); window.location="/purchases";</script>'
    
    c.execute("SELECT id, date, client_name, instagram, post_office, products, prepayment, cod, ttn, status, comment FROM sales WHERE date BETWEEN ? AND ? ORDER BY date", 
              (start_date, end_date))
    sales = c.fetchall()
    
    product_counts = {}
    for sale in sales:
        products = sale[5].split(", ") if sale[5] else []
        for product in products:
            name_qty = product.split(" (")
            name = name_qty[0]
            qty = int(name_qty[1].split(" ")[0]) if len(name_qty) > 1 else 0
            product_counts[name] = product_counts.get(name, 0) + qty
    
    totals = {'Забрали': 0, 'Очікує': 0, 'Повернення': 0}
    for sale in sales:
        status = sale[9]
        total = sale[6] + sale[7]
        totals[status] = totals.get(status, 0) + total
    
    c.execute("SELECT id, name, stock FROM products")  # Додано stock для валідації
    products = c.fetchall()
    conn.close()
    return render_template('purchases.html', sales=sales, products=products, product_counts=product_counts, 
                          totals=totals, start_date=start_date, end_date=end_date)

# Зміна статусу
@app.route('/change_status/<int:sale_id>', methods=['GET', 'POST'])
def change_status(sale_id):
    conn = sqlite3.connect('business.db')
    c = conn.cursor()
    
    try:
        if request.method == 'POST':
            new_status = request.form['status']
            c.execute("SELECT status, products FROM sales WHERE id = ?", (sale_id,))
            result = c.fetchone()
            if not result:
                conn.close()
                return '<script>alert("Продаж не знайдено!"); window.location="/purchases";</script>'
            
            current_status, products = result
            if new_status == 'Повернення' and current_status != 'Повернення':
                product_list = products.split(", ") if products else []
                for product in product_list:
                    name_qty = product.split(" (")
                    name = name_qty[0]
                    qty = int(name_qty[1].split(" ")[0]) if len(name_qty) > 1 else 0
                    c.execute("UPDATE products SET stock = stock + ? WHERE name = ?", (qty, name))
            elif current_status == 'Повернення' and new_status != 'Повернення':
                product_list = products.split(", ") if products else []
                for product in product_list:
                    name_qty = product.split(" (")
                    name = name_qty[0]
                    qty = int(name_qty[1].split(" ")[0]) if len(name_qty) > 1 else 0
                    c.execute("SELECT stock FROM products WHERE name = ?", (name,))
                    stock = c.fetchone()[0]
                    if stock < qty:
                        conn.close()
                        return f'<script>alert("Недостатньо товару {name} на складі! Залишок: {stock} шт."); window.location="/purchases";</script>'
                    c.execute("UPDATE products SET stock = stock - ? WHERE name = ?", (qty, name))
            
            c.execute("UPDATE sales SET status = ? WHERE id = ?", (new_status, sale_id))
            conn.commit()
            conn.close()
            return '<script>alert("Статус змінено!"); window.location="/purchases";</script>'
        
        c.execute("SELECT status FROM sales WHERE id = ?", (sale_id,))
        result = c.fetchone()
        if not result:
            conn.close()
            return '<script>alert("Продаж не знайдено!"); window.location="/purchases";</script>'
        current_status = result[0]
        conn.close()
        return render_template('change_status.html', sale_id=sale_id, current_status=current_status)
    except Exception as e:
        conn.close()
        return f'<script>alert("Помилка: {str(e)}"); window.location="/purchases";</script>'

# Сторінка "Переглянути звіти"
@app.route('/reports', methods=['GET', 'POST'])
def reports():
    conn = sqlite3.connect('business.db')
    c = conn.cursor()
    
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    
    if request.method == 'POST':
        start_date = request.form.get('start_date', start_date)
        end_date = request.form.get('end_date', end_date)
    
    c.execute("SELECT client_name, instagram, ttn, products, prepayment, cod, status FROM sales WHERE date BETWEEN ? AND ? ORDER BY date", 
              (start_date, end_date))
    sales = c.fetchall()
    
    product_counts = {}
    for sale in sales:
        products = sale[3].split(", ") if sale[3] else []
        for product in products:
            name_qty = product.split(" (")
            name = name_qty[0]
            qty = int(name_qty[1].split(" ")[0]) if len(name_qty) > 1 else 0
            product_counts[name] = product_counts.get(name, 0) + qty
    
    totals = {'Забрали': 0, 'Очікує': 0, 'Повернення': 0}
    for sale in sales:
        status = sale[6]
        total = sale[4] + sale[5]
        totals[status] = totals.get(status, 0) + total
    
    c.execute("SELECT description, amount FROM expenses WHERE date BETWEEN ? AND ?", (start_date, end_date))
    expenses = c.fetchall()
    total_expenses = sum(expense[1] for expense in expenses)
    
    profit = totals['Забрали'] - total_expenses
    
    conn.close()
    return render_template('reports.html', sales=sales, product_counts=product_counts, totals=totals, 
                          expenses=expenses, total_expenses=total_expenses, profit=profit, 
                          start_date=start_date, end_date=end_date)

# Додавання витрат
@app.route('/add_expense', methods=['GET', 'POST'])
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
        return '<script>alert("Витрату додано!"); window.location="/";</script>'
    return render_template('add_expense.html')

# Зняття коштів з пошти
@app.route('/withdraw', methods=['GET', 'POST'])
def withdraw():
    if request.method == 'POST':
        date = request.form['date']
        amount = float(request.form['amount'])
        
        conn = sqlite3.connect('business.db')
        c = conn.cursor()
        c.execute("INSERT INTO withdrawals (date, amount) VALUES (?, ?)", (date, amount))
        conn.commit()
        conn.close()
        return '<script>alert("Зняття додано!"); window.location="/";</script>'
    return render_template('withdraw.html')

# Додавання товару в обіг
@app.route('/add_product', methods=['GET', 'POST'])
def add_product():
    if request.method == 'POST':
        name = request.form['name']
        stock = int(request.form['stock'])
        
        conn = sqlite3.connect('business.db')
        c = conn.cursor()
        # Перевірка унікальності назви товару
        c.execute("SELECT COUNT(*) FROM products WHERE name = ?", (name,))
        if c.fetchone()[0] > 0:
            conn.close()
            return '<script>alert("Товар із такою назвою вже існує!"); window.location="/add_product";</script>'
        
        c.execute("INSERT INTO products (name, stock) VALUES (?, ?)", (name, stock))
        conn.commit()
        conn.close()
        return '<script>alert("Товар додано!"); window.location="/";</script>'
    return render_template('add_product.html')

# Редагування запасів товару
@app.route('/edit_product/<int:product_id>', methods=['GET', 'POST'])
def edit_product(product_id):
    conn = sqlite3.connect('business.db')
    c = conn.cursor()
    
    try:
        if request.method == 'POST':
            new_stock = int(request.form['stock'])
            c.execute("UPDATE products SET stock = ? WHERE id = ?", (new_stock, product_id))
            conn.commit()
            conn.close()
            return '<script>alert("Запаси оновлено!"); window.location="/";</script>'
        
        c.execute("SELECT name, stock FROM products WHERE id = ?", (product_id,))
        product = c.fetchone()
        if not product:
            conn.close()
            return '<script>alert("Товар не знайдено!"); window.location="/";</script>'
        conn.close()
        return render_template('edit_product.html', product=product, product_id=product_id)
    except Exception as e:
        conn.close()
        return f'<script>alert("Помилка: {str(e)}"); window.location="/";</script>'

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=8080)
