import os, sqlite3, csv, io, secrets
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, Response, abort
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.getenv('DATABASE_PATH', os.path.join(BASE, 'data', 'coffee.db'))
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', secrets.token_hex(32))
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax', SESSION_COOKIE_SECURE=os.getenv('COOKIE_SECURE','0')=='1', MAX_CONTENT_LENGTH=1024*1024)
if os.getenv('TRUST_PROXY') == '1': app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

def db():
    os.makedirs(os.path.dirname(os.path.abspath(DB)), exist_ok=True)
    c=sqlite3.connect(DB, timeout=15)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    c.execute('PRAGMA busy_timeout=15000')
    return c

def init_db():
    with db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL DEFAULT 'Coffee', price_paise INTEGER NOT NULL CHECK(price_paise>=0), active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS bills(id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, customer TEXT NOT NULL DEFAULT '', subtotal_paise INTEGER NOT NULL, discount_paise INTEGER NOT NULL, tax_paise INTEGER NOT NULL, total_paise INTEGER NOT NULL, payment_method TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS bill_items(id INTEGER PRIMARY KEY, bill_id INTEGER NOT NULL REFERENCES bills(id), product_id INTEGER REFERENCES products(id) ON DELETE SET NULL, name TEXT NOT NULL, qty INTEGER NOT NULL, unit_price_paise INTEGER NOT NULL, line_total_paise INTEGER NOT NULL);
        ''')
        if not c.execute('SELECT 1 FROM users LIMIT 1').fetchone():
            username=os.getenv('ADMIN_USERNAME','admin'); password=os.getenv('ADMIN_PASSWORD')
            if not password:
                password=secrets.token_urlsafe(14)
                print('INITIAL ADMIN PASSWORD (save it now):',password,flush=True)
            c.execute('INSERT INTO users(username,password_hash) VALUES(?,?)',(username,generate_password_hash(password)))
        if not c.execute('SELECT 1 FROM products LIMIT 1').fetchone():
            c.executemany('INSERT INTO products(name,category,price_paise) VALUES(?,?,?)',[(n,cat,p) for n,cat,p in [('Espresso','Coffee',9000),('Cappuccino','Coffee',14000),('Latte','Coffee',15000),('Americano','Coffee',11000),('Cold Coffee','Coffee',16000),('Masala Tea','Tea',5000),('Hot Chocolate','Other',13000),('Cookie','Snacks',4000)]])
        c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('shop_name','Chit Chai')")
        c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('gst_rate','5')")
        c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('shop_address','')")
        c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('shop_phone','')")
        c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('gstin','')")

def setting(c,key):
    row=c.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone()
    return row['value'] if row else ''

def money(p): return f'{p/100:,.2f}'
app.jinja_env.filters['money']=money

def login_required(fn):
    @wraps(fn)
    def wrapper(*args,**kwargs):
        if 'uid' not in session: return redirect(url_for('login'))
        return fn(*args,**kwargs)
    return wrapper

@app.before_request
def csrf_protect():
    if request.method in ('POST','PUT','PATCH','DELETE'):
        if not session.get('csrf') or request.headers.get('X-CSRF-Token',request.form.get('csrf_token')) != session['csrf']:
            abort(400,description='Invalid CSRF token')

@app.context_processor
def inject_globals():
    with db() as c: name=setting(c,'shop_name')
    return {'csrf_token':session.setdefault('csrf',secrets.token_urlsafe(24)),'shop_name':name}

@app.route('/login',methods=['GET','POST'])
def login():
    if request.method=='POST':
        with db() as c: user=c.execute('SELECT * FROM users WHERE username=?',(request.form.get('username',''),)).fetchone()
        if user and check_password_hash(user['password_hash'],request.form.get('password','')):
            session.clear(); session['uid']=user['id']; session['csrf']=secrets.token_urlsafe(24)
            return redirect(url_for('index'))
        flash('Invalid username or password','error')
    return render_template('login.html')

@app.post('/logout')
def logout():
    session.clear(); return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    with db() as c:
        products=c.execute('SELECT * FROM products WHERE active=1 ORDER BY category,name').fetchall()
        today=datetime.now().strftime('%Y-%m-%d')
        stats=c.execute('SELECT COUNT(*) count, COALESCE(SUM(total_paise),0) total FROM bills WHERE substr(created_at,1,10)=?',(today,)).fetchone()
        recent=c.execute('SELECT * FROM bills ORDER BY id DESC LIMIT 8').fetchall()
        gst=setting(c,'gst_rate')
    return render_template('index.html',products=products,stats=stats,recent=recent,gst=gst)

def parse_paise(value):
    x=Decimal(str(value))
    if not x.is_finite() or x<0: raise ValueError('Invalid amount')
    return int((x*100).quantize(Decimal('1'),rounding=ROUND_HALF_UP))

@app.post('/api/bills')
@login_required
def create_bill():
    data=request.get_json(silent=True) or {}
    items=data.get('items',[])
    if not isinstance(items,list) or not items or len(items)>100: return jsonify(error='Add at least one item'),400
    try:
        discount=parse_paise(data.get('discount',0))
        customer=str(data.get('customer','')).strip()[:100]
        payment=str(data.get('payment','Cash'))
        if payment not in ('Cash','UPI','Card'): raise ValueError('Invalid payment method')
        with db() as c:
            prepared=[]; subtotal=0
            for item in items:
                pid=int(item['id']); qty=int(item['qty'])
                if qty<1 or qty>999: raise ValueError('Quantity must be 1–999')
                p=c.execute('SELECT * FROM products WHERE id=? AND active=1',(pid,)).fetchone()
                if not p: raise ValueError('Product unavailable')
                line=p['price_paise']*qty
                subtotal+=line
                prepared.append((pid,p['name'],qty,p['price_paise'],line))
            if discount>subtotal: raise ValueError('Discount exceeds subtotal')
            rate=Decimal(setting(c,'gst_rate'))
            tax=int(((Decimal(subtotal-discount)*rate)/100).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
            total=subtotal-discount+tax
            cur=c.execute('INSERT INTO bills(created_at,customer,subtotal_paise,discount_paise,tax_paise,total_paise,payment_method) VALUES(?,?,?,?,?,?,?)',(datetime.now().strftime('%Y-%m-%d %H:%M:%S'),customer,subtotal,discount,tax,total,payment))
            bid=cur.lastrowid
            c.executemany('INSERT INTO bill_items(bill_id,product_id,name,qty,unit_price_paise,line_total_paise) VALUES(?,?,?,?,?,?)',[(bid,*i) for i in prepared])
        return jsonify(id=bid,invoice_url=url_for('invoice',bill_id=bid)),201
    except (ValueError,TypeError,KeyError,ArithmeticError,OverflowError) as e: return jsonify(error=str(e)),400

@app.route('/bills')
@login_required
def bills():
    q=request.args.get('q','').strip()[:100]
    with db() as c:
        if q:
            rows=c.execute('SELECT * FROM bills WHERE customer LIKE ? OR CAST(id AS TEXT)=? ORDER BY id DESC LIMIT 300',('%'+q+'%',q)).fetchall()
        else: rows=c.execute('SELECT * FROM bills ORDER BY id DESC LIMIT 300').fetchall()
    return render_template('bills.html',bills=rows,q=q)

@app.route('/bills/<int:bill_id>')
@login_required
def invoice(bill_id):
    with db() as c:
        bill=c.execute('SELECT * FROM bills WHERE id=?',(bill_id,)).fetchone()
        if not bill: abort(404)
        items=c.execute('SELECT * FROM bill_items WHERE bill_id=?',(bill_id,)).fetchall()
        settings={k:setting(c,k) for k in ('shop_name','shop_address','shop_phone','gstin','gst_rate')}
    return render_template('invoice.html',bill=bill,items=items,settings=settings)

@app.route('/products',methods=['GET','POST'])
@login_required
def products():
    if request.method=='POST':
        try:
            name=request.form.get('name','').strip()[:100]
            if not name: raise ValueError('Product name required')
            category=request.form.get('category','Coffee').strip()[:40] or 'Other'
            price=parse_paise(request.form.get('price','0'))
            with db() as c:
                pid=request.form.get('id','').strip()
                if pid:
                    c.execute('UPDATE products SET name=?,category=?,price_paise=? WHERE id=?',(name,category,price,int(pid)))
                else: c.execute('INSERT INTO products(name,category,price_paise) VALUES(?,?,?)',(name,category,price))
            flash('Product saved','success')
        except (ValueError,ArithmeticError) as e: flash(str(e),'error')
        return redirect(url_for('products'))
    with db() as c: rows=c.execute('SELECT * FROM products ORDER BY active DESC,category,name').fetchall()
    return render_template('products.html',products=rows)

@app.post('/products/<int:pid>/toggle')
@login_required
def toggle_product(pid):
    with db() as c: c.execute('UPDATE products SET active=1-active WHERE id=?',(pid,))
    return redirect(url_for('products'))

@app.route('/settings',methods=['GET','POST'])
@login_required
def settings_page():
    if request.method=='POST':
        try:
            rate=Decimal(request.form.get('gst_rate','0'))
            if not rate.is_finite() or not 0<=rate<=100: raise ValueError('GST must be between 0 and 100')
            values={k:request.form.get(k,'').strip()[:200] for k in ('shop_name','shop_address','shop_phone','gstin')}
            if not values['shop_name']: raise ValueError('Shop name required')
            values['gst_rate']=str(rate)
            with db() as c:
                for k,v in values.items(): c.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)',(k,v))
            flash('Settings updated','success')
        except (ValueError,ArithmeticError) as e: flash(str(e),'error')
        return redirect(url_for('settings_page'))
    with db() as c: values={k:setting(c,k) for k in ('shop_name','shop_address','shop_phone','gstin','gst_rate')}
    return render_template('settings.html',settings=values)

@app.route('/reports')
@login_required
def reports():
    with db() as c:
        daily=c.execute('SELECT substr(created_at,1,10) day,COUNT(*) bills,SUM(total_paise) total FROM bills GROUP BY substr(created_at,1,10) ORDER BY day DESC LIMIT 30').fetchall()
        top=c.execute('SELECT name,SUM(qty) qty,SUM(line_total_paise) revenue FROM bill_items GROUP BY name ORDER BY qty DESC LIMIT 10').fetchall()
    return render_template('reports.html',daily=daily,top=top)

@app.route('/export.csv')
@login_required
def export_csv():
    output=io.StringIO(); writer=csv.writer(output)
    writer.writerow(['Bill ID','Date','Customer','Subtotal INR','Discount INR','GST INR','Total INR','Payment'])
    with db() as c:
        for r in c.execute('SELECT * FROM bills ORDER BY id DESC'):
            writer.writerow([r['id'],r['created_at'],r['customer'],money(r['subtotal_paise']),money(r['discount_paise']),money(r['tax_paise']),money(r['total_paise']),r['payment_method']])
    return Response('\ufeff'+output.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename=coffee-sales.csv'})

@app.route('/account',methods=['GET','POST'])
@login_required
def account():
    if request.method=='POST':
        with db() as c:
            user=c.execute('SELECT * FROM users WHERE id=?',(session['uid'],)).fetchone()
            if not check_password_hash(user['password_hash'],request.form.get('current','')):
                flash('Current password incorrect','error')
            elif len(request.form.get('new',''))<10: flash('New password must have at least 10 characters','error')
            else:
                c.execute('UPDATE users SET password_hash=? WHERE id=?',(generate_password_hash(request.form['new']),session['uid']))
                flash('Password changed','success')
        return redirect(url_for('account'))
    return render_template('account.html')

@app.route('/health')
def health(): return jsonify(status='ok')

init_db()
if __name__=='__main__': app.run(host='127.0.0.1',port=int(os.getenv('PORT','5000')),debug=False)
