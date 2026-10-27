import os
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import text

from config import Config

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
from models.database import db
from models.user import User
from models.product import Product
from models.cart import Cart
from models.order import Order, OrderItem
from models.review import Review
from models.wishlist import Wishlist
from ai.chatbot import get_response

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static")
)
app.config.from_object(Config)
db.init_app(app)

PERMANENT_ADMINS = [
    {"full_name": "Khushi Singh", "email": "khushi.singh@tufaanimart.com"},
    {"full_name": "Rahul Kumar Gope", "email": "rahul.gope@tufaanimart.com"}
]
ADMIN_PASSWORD = "Tufaani@Admin2026"
ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

def allowed_image(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS

def migrate():
    migrations = {
        "user": {
            "is_permanent_admin": "BOOLEAN DEFAULT 0",
            "is_approved": "BOOLEAN DEFAULT 1",
            "approval_status": "VARCHAR(20) DEFAULT 'Approved'",
            "store_name": "VARCHAR(150)",
            "phone": "VARCHAR(20)",
        },
        "products": {
            "brand": "VARCHAR(100)",
            "unit": "VARCHAR(50) DEFAULT '1 piece'",
            "stock": "INTEGER DEFAULT 0",
            "discount": "FLOAT DEFAULT 0",
            "rating": "FLOAT DEFAULT 0",
            "store_id": "INTEGER",
            "is_available": "BOOLEAN DEFAULT 1",
            "image": "VARCHAR(255)",
        },
        "wishlist": {"created_at": "DATETIME"},
        "orders": {
            "payment_method": "VARCHAR(50) DEFAULT 'Cash on Delivery'",
            "delivery_address": "TEXT",
            "phone": "VARCHAR(20)",
        },
        "order_items": {
            "price": "FLOAT DEFAULT 0",
            "subtotal": "FLOAT DEFAULT 0",
        },
    }
    with db.engine.connect() as conn:
        for table, cols in migrations.items():
            exists = conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=:n"
            ), {"n": table}).fetchone()
            if not exists:
                continue
            existing = {r[1] for r in conn.execute(text(f"PRAGMA table_info({table})"))}
            for col, typ in cols.items():
                if col not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {typ}"))
        # Keep the new approval_status column synchronized with the
        # legacy is_approved flag for existing databases.
        user_exists = conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='user'"
        )).fetchone()
        if user_exists:
            cols = {r[1] for r in conn.execute(text("PRAGMA table_info(user)"))}
            if "approval_status" in cols and "is_approved" in cols:
                conn.execute(text("""
                    UPDATE user
                    SET approval_status = CASE
                        WHEN role = 'seller' AND is_approved = 1 THEN 'Approved'
                        WHEN role = 'seller' AND is_approved = 0 THEN 'Pending'
                        ELSE 'Approved'
                    END
                    WHERE approval_status IS NULL OR approval_status = ''
                """))
        conn.commit()

def seed_admins():
    for a in PERMANENT_ADMINS:
        u = User.query.filter_by(email=a["email"]).first()
        if not u:
            u = User(full_name=a["full_name"], email=a["email"],
                     password=generate_password_hash(ADMIN_PASSWORD),
                     role="admin", is_permanent_admin=True, is_approved=True)
            db.session.add(u)
        else:
            u.full_name = a["full_name"]
            u.role = "admin"
            u.is_permanent_admin = True
            u.is_approved = True
    db.session.commit()

def login_required(fn=None):
    """Login decorator. Supports both @login_required and @login_required()."""
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                flash("Please login first.", "warning")
                return redirect(url_for("login"))
            return view(*args, **kwargs)
        return wrapper

    if fn is None:
        return decorator
    return decorator(fn)


def role_required(role):
    """Role decorator. Supports both @seller_required and @seller_required()."""
    def decorator(fn=None):
        def wrap(view):
            @wraps(view)
            def wrapper(*args, **kwargs):
                if "user_id" not in session:
                    flash("Please login first.", "warning")
                    return redirect(url_for("login"))

                if session.get("role") != role:
                    flash("You do not have permission to access this page.", "error")
                    return redirect(url_for("dashboard"))

                return view(*args, **kwargs)
            return wrapper

        if fn is None:
            return wrap
        return wrap(fn)

    return decorator


admin_required = role_required("admin")
seller_required = role_required("seller")
customer_required = role_required("customer")

def price_after_discount(product):
    price = product.price or 0
    discount = product.discount or 0
    return round(price - price * discount / 100, 2)

def cart_data(user_id):
    items = Cart.query.filter_by(user_id=user_id).all()
    data, total = [], 0
    for item in items:
        product = Product.query.get(item.product_id)
        if not product:
            continue
        item_total = price_after_discount(product) * item.quantity
        total += item_total
        data.append({"item": item, "product": product, "item_total": round(item_total, 2)})
    return items, data, round(total, 2)

@app.context_processor
def inject_globals():
    return {"current_user": User.query.get(session["user_id"]) if session.get("user_id") else None}

@app.route("/")
def home():
    featured = Product.query.filter_by(is_available=True).order_by(Product.created_at.desc()).limit(8).all()
    categories = [x[0] for x in db.session.query(Product.category).filter(Product.category.isnot(None)).distinct().all() if x[0]]
    return render_template("index.html", products=featured, categories=categories)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        role = request.form.get("role", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if role not in ("admin", "seller", "customer"):
            flash("Please select a valid account type.", "warning")
            return redirect(url_for("login"))
        user = User.query.filter_by(email=email).first()
        if not user or not check_password_hash(user.password, password):
            flash("Invalid email or password.", "error")
            return redirect(url_for("login"))
        if user.role != role:
            flash(f"This account is not registered as {role}.", "error")
            return redirect(url_for("login"))
        if role == "admin" and not user.is_permanent_admin:
            flash("Admin accounts are restricted to permanent administrators.", "error")
            return redirect(url_for("login"))
        if role == "seller":
            seller_status = getattr(user, "approval_status", None) or ("Approved" if user.is_approved else "Pending")
            if seller_status == "Rejected":
                flash("Your seller application was rejected by an administrator.", "error")
                return redirect(url_for("login"))
            if seller_status != "Approved":
                flash("Your seller account is waiting for admin approval.", "warning")
                return redirect(url_for("login"))
        session.clear()
        session.update(user_id=user.id, role=user.role, name=user.full_name)
        flash(f"Welcome, {user.full_name}!", "success")
        return redirect(url_for("dashboard"))
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        role = request.form.get("role", "customer").strip()
        if role not in ("customer", "seller"):
            flash("Only Customer or Seller registration is available.", "error")
            return redirect(url_for("register"))
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        store_name = request.form.get("store_name", "").strip()
        if not all([full_name, email, password]):
            flash("Name, email and password are required.", "warning")
            return redirect(url_for("register"))
        if password != confirm:
            flash("Passwords do not match.", "warning")
            return redirect(url_for("register"))
        if role == "seller" and not store_name:
            flash("Store name is required for sellers.", "warning")
            return redirect(url_for("register"))
        if User.query.filter_by(email=email).first():
            flash("Email already registered.", "error")
            return redirect(url_for("register"))
        user = User(full_name=full_name, email=email, phone=phone,
                    password=generate_password_hash(password), role=role,
                    store_name=store_name if role == "seller" else None,
                    is_approved=False if role == "seller" else True,
                    approval_status="Pending" if role == "seller" else "Approved")
        try:
            db.session.add(user)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print("Registration error:", e)
            flash("Registration failed. Please try again.", "error")
            return redirect(url_for("register"))

        if role == "seller":
            flash("Registration successful. Your seller account is waiting for admin approval.", "success")
        else:
            flash("Customer registration successful.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/dashboard")
@login_required
def dashboard():
    role = session["role"]
    if role == "admin":
        return redirect(url_for("admin_dashboard"))
    if role == "seller":
        return redirect(url_for("seller_dashboard"))
    return redirect(url_for("customer_dashboard"))

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for("login"))


# ---------------- CUSTOMER ----------------
@app.route("/customer")
@customer_required
def customer_dashboard():
    orders = Order.query.filter_by(user_id=session["user_id"]).order_by(Order.ordered_at.desc()).all()
    return render_template("customer_dashboard.html", orders=orders)

@app.route("/stores")
def stores():
    sellers = User.query.filter_by(role="seller", approval_status="Approved").all()
    return render_template("stores.html", sellers=sellers, selected_store=None, store_products=[])

@app.route("/stores/<int:store_id>")
def store_details(store_id):
    store = User.query.filter_by(id=store_id, role="seller", approval_status="Approved").first_or_404()
    products = Product.query.filter_by(seller_id=store_id, is_available=True).all()
    return render_template("stores.html", sellers=[], selected_store=store, store_products=products)

@app.route("/uploads/products/<path:filename>")
def uploaded_product_image(filename):
    """Serve product images uploaded by sellers."""
    return send_from_directory(
        os.path.join(app.config["UPLOAD_FOLDER"], "products"),
        filename
    )


@app.route("/products")
def products():
    search = request.args.get("search", "").strip()
    category = request.args.get("category", "").strip()
    q = Product.query.filter_by(is_available=True)
    if search:
        q = q.filter((Product.product_name.ilike(f"%{search}%")) |
                     (Product.brand.ilike(f"%{search}%")) |
                     (Product.category.ilike(f"%{search}%")))
    if category:
        q = q.filter_by(category=category)
    product_list = q.order_by(Product.created_at.desc()).all()
    categories = [x[0] for x in db.session.query(Product.category).filter(Product.category.isnot(None)).distinct().all() if x[0]]

    # IDs already saved by the logged-in customer. This lets the
    # product cards show a useful filled/unfilled wishlist heart.
    wishlist_ids = set()
    if session.get("role") == "customer":
        wishlist_ids = {
            item.product_id
            for item in Wishlist.query.filter_by(user_id=session["user_id"]).all()
        }

    return render_template("products.html", products=product_list, categories=categories,
                           search=search, selected_category=category, selected_product=None,
                           wishlist_ids=wishlist_ids)

@app.route("/products/<int:product_id>")
def product_details(product_id):
    product = Product.query.filter_by(id=product_id, is_available=True).first_or_404()
    wishlist_ids = set()
    if session.get("role") == "customer":
        wishlist_ids = {
            item.product_id
            for item in Wishlist.query.filter_by(user_id=session["user_id"]).all()
        }
    return render_template("products.html", products=[], categories=[], search="",
                           selected_category="", selected_product=product,
                           wishlist_ids=wishlist_ids)

@app.route("/cart")
@customer_required
def cart():
    _, items, total = cart_data(session["user_id"])
    return render_template("cart.html", items=items, total=total)

@app.route("/add-to-cart/<int:product_id>", methods=["POST"])
@customer_required
def add_to_cart(product_id):
    p = Product.query.get_or_404(product_id)
    if not p.is_available or (p.stock is not None and p.stock <= 0):
        flash("Product is out of stock.", "warning")
        return redirect(request.referrer or url_for("products"))
    item = Cart.query.filter_by(user_id=session["user_id"], product_id=product_id).first()
    if item:
        if p.stock and item.quantity >= p.stock:
            flash("Maximum available stock already added.", "warning")
            return redirect(request.referrer or url_for("products"))
        item.quantity += 1
    else:
        db.session.add(Cart(user_id=session["user_id"], product_id=product_id, quantity=1))
    db.session.commit()
    flash(f"{p.product_name} added to cart.", "success")
    return redirect(request.referrer or url_for("products"))

@app.route("/cart/update/<int:cart_id>", methods=["POST"])
@customer_required
def update_cart(cart_id):
    item = Cart.query.filter_by(id=cart_id, user_id=session["user_id"]).first_or_404()
    qty = request.form.get("quantity", type=int)
    product = Product.query.get(item.product_id)
    if not qty or qty < 1 or (product.stock is not None and qty > product.stock):
        flash("Invalid quantity or insufficient stock.", "warning")
        return redirect(url_for("cart"))
    item.quantity = qty
    db.session.commit()
    return redirect(url_for("cart"))

@app.route("/cart/remove/<int:cart_id>", methods=["POST"])
@customer_required
def remove_from_cart(cart_id):
    item = Cart.query.filter_by(id=cart_id, user_id=session["user_id"]).first_or_404()
    db.session.delete(item)
    db.session.commit()
    return redirect(url_for("cart"))

@app.route("/checkout", methods=["GET", "POST"])
@customer_required
def checkout():
    cart_items, cart_products, total = cart_data(session["user_id"])
    if not cart_items:
        flash("Your cart is empty.", "warning")
        return redirect(url_for("cart"))
    if request.method == "POST":
        address = request.form.get("delivery_address", "").strip()
        phone = request.form.get("phone", "").strip()
        payment = request.form.get("payment_method", "cod")
        if not address:
            flash("Please enter your delivery address.", "warning")
            return redirect(url_for("checkout"))
        if not phone:
            flash("Please enter your phone number.", "warning")
            return redirect(url_for("checkout"))
        payment = "Cash on Delivery" if payment == "cod" else "Online Payment"
        try:
            for x in cart_products:
                p, qty = x["product"], x["item"].quantity
                if p.stock is not None and qty > p.stock:
                    raise ValueError(f"Not enough stock for {p.product_name}.")
            order = Order(user_id=session["user_id"], total_amount=total, status="Pending",
                          payment_method=payment, delivery_address=address, phone=phone)
            db.session.add(order)
            db.session.flush()
            for x in cart_products:
                p, qty = x["product"], x["item"].quantity
                price = price_after_discount(p)
                db.session.add(OrderItem(order_id=order.id, product_id=p.id, quantity=qty,
                                         price=price, subtotal=price * qty))
                if p.stock is not None:
                    p.stock = max(0, p.stock - qty)
                    if p.stock == 0:
                        p.is_available = False
            for item in cart_items:
                db.session.delete(item)
            db.session.commit()
            flash(f"Order #{order.id} placed successfully. Status: Pending.", "success")
            return redirect(url_for("orders"))
        except Exception as e:
            db.session.rollback()
            flash(str(e), "error")
            return redirect(url_for("checkout"))
    return render_template("checkout.html", cart_products=cart_products, total_amount=total)

@app.route("/orders")
@customer_required
def orders():
    orders = Order.query.filter_by(user_id=session["user_id"]).order_by(Order.ordered_at.desc()).all()
    return render_template("orders.html", orders=orders)

@app.route("/orders/<int:order_id>")
@customer_required
def order_details(order_id):
    order = Order.query.filter_by(id=order_id, user_id=session["user_id"]).first_or_404()
    return render_template("order_details.html", order=order)

@app.route("/wishlist")
@customer_required
def wishlist():
    items = Wishlist.query.filter_by(user_id=session["user_id"]).all()
    products = [Product.query.get(i.product_id) for i in items]
    return render_template("wishlist.html", products=[p for p in products if p])

@app.route("/wishlist/add/<int:product_id>", methods=["POST"])
@customer_required
def add_to_wishlist(product_id):
    if not Wishlist.query.filter_by(user_id=session["user_id"], product_id=product_id).first():
        db.session.add(Wishlist(user_id=session["user_id"], product_id=product_id))
        db.session.commit()
        flash("Added to wishlist.", "success")
    return redirect(request.referrer or url_for("products"))

@app.route("/wishlist/remove/<int:product_id>", methods=["POST"])
@customer_required
def remove_from_wishlist(product_id):
    item = Wishlist.query.filter_by(user_id=session["user_id"], product_id=product_id).first()
    if item:
        db.session.delete(item)
        db.session.commit()
    return redirect(url_for("wishlist"))


# ---------------- SELLER ----------------
@app.route("/seller")
@seller_required
def seller_dashboard():
    products = Product.query.filter_by(seller_id=session["user_id"]).all()
    product_ids = [p.id for p in products]
    order_ids = []
    if product_ids:
        order_ids = list({x.order_id for x in OrderItem.query.filter(OrderItem.product_id.in_(product_ids)).all()})
    orders = Order.query.filter(Order.id.in_(order_ids)).order_by(Order.ordered_at.desc()).all() if order_ids else []
    return render_template("seller_dashboard.html", products=products, orders=orders)

@app.route("/seller/add-product", methods=["GET", "POST"])
@seller_required
def add_product():
    if request.method == "POST":
        name = request.form.get("product_name", "").strip()
        category = request.form.get("category", "").strip()
        price = request.form.get("price", type=float)
        stock = request.form.get("stock", type=int)
        if not name or not category or price is None or stock is None:
            flash("Product name, category, price and stock are required.", "warning")
            return redirect(url_for("add_product"))
        image_file = request.files.get("image")
        filename = None
        if image_file and image_file.filename:
            if not allowed_image(image_file.filename):
                flash("Allowed images: PNG, JPG, JPEG, WEBP.", "error")
                return redirect(url_for("add_product"))
            original = secure_filename(image_file.filename)
            extension = original.rsplit(".", 1)[1].lower()
            import uuid
            filename = f"{session['user_id']}_{uuid.uuid4().hex}.{extension}"
            image_file.save(os.path.join(app.config["UPLOAD_FOLDER"], "products", filename))
        p = Product(product_name=name,
                    description=request.form.get("description", "").strip(),
                    price=price, category=category,
                    brand=request.form.get("brand", "").strip(),
                    unit=request.form.get("unit", "1 piece").strip(),
                    stock=stock, discount=request.form.get("discount", 0, type=float),
                    rating=0, image=filename, seller_id=session["user_id"],
                    store_id=session["user_id"], is_available=stock > 0)
        db.session.add(p)
        db.session.commit()
        flash("Product added successfully.", "success")
        return redirect(url_for("seller_products"))
    return render_template("add_product.html")

@app.route("/seller/products")
@seller_required
def seller_products():
    products = Product.query.filter_by(seller_id=session["user_id"]).order_by(Product.created_at.desc()).all()
    return render_template("seller_products.html", products=products)

@app.route("/seller/product/delete/<int:product_id>", methods=["POST"])
@seller_required
def delete_product(product_id):
    p = Product.query.filter_by(id=product_id, seller_id=session["user_id"]).first_or_404()
    db.session.delete(p)
    db.session.commit()
    flash("Product deleted.", "success")
    return redirect(url_for("seller_products"))

@app.route("/seller/orders")
@seller_required
def seller_orders():
    products = Product.query.filter_by(seller_id=session["user_id"]).all()
    ids = [p.id for p in products]
    order_ids = list({x.order_id for x in OrderItem.query.filter(OrderItem.product_id.in_(ids)).all()}) if ids else []
    orders = Order.query.filter(Order.id.in_(order_ids)).order_by(Order.ordered_at.desc()).all() if order_ids else []
    return render_template("seller_orders.html", orders=orders)

@app.route("/seller/orders/<int:order_id>/status", methods=["POST"])
@seller_required
def update_order_status(order_id):
    new_status = request.form.get("status", "")
    allowed = ["Pending", "Accepted", "Preparing", "Out for Delivery", "Delivered", "Cancelled"]
    if new_status not in allowed:
        flash("Invalid status.", "error")
        return redirect(url_for("seller_orders"))
    product_ids = [p.id for p in Product.query.filter_by(seller_id=session["user_id"]).all()]
    item = OrderItem.query.filter(OrderItem.order_id == order_id,
                                  OrderItem.product_id.in_(product_ids)).first()
    if not item:
        flash("This order does not contain your products.", "error")
        return redirect(url_for("seller_orders"))
    order = Order.query.get_or_404(order_id)
    order.status = new_status
    db.session.commit()
    flash(f"Order #{order.id} updated to {new_status}.", "success")
    return redirect(url_for("seller_orders"))


# ---------------- ADMIN ----------------
@app.route("/admin")
@admin_required
def admin_dashboard():
    stats = {
        "customers": User.query.filter_by(role="customer").count(),
        "sellers": User.query.filter_by(role="seller").count(),
        "products": Product.query.count(),
        "orders": Order.query.count(),
    }
    pending_sellers = User.query.filter_by(role="seller", approval_status="Pending").all()
    return render_template("admin_dashboard.html", stats=stats, pending_sellers=pending_sellers)

@app.route("/admin/sellers")
@admin_required
def admin_sellers():
    sellers = User.query.filter_by(role="seller").order_by(User.created_at.desc()).all()
    return render_template("admin_sellers.html", sellers=sellers)

@app.route("/admin/sellers/<int:user_id>/approve", methods=["POST"])
@admin_required
def approve_seller(user_id):
    seller = User.query.filter_by(id=user_id, role="seller").first_or_404()
    seller.is_approved = True
    seller.approval_status = "Approved"
    db.session.commit()
    flash(f"{seller.store_name or seller.full_name} approved successfully.", "success")
    return redirect(url_for("admin_sellers"))

@app.route("/admin/sellers/<int:user_id>/reject", methods=["POST"])
@admin_required
def reject_seller(user_id):
    seller = User.query.filter_by(id=user_id, role="seller").first_or_404()
    seller.is_approved = False
    seller.approval_status = "Rejected"
    db.session.commit()
    flash(f"{seller.store_name or seller.full_name} has been rejected.", "warning")
    return redirect(url_for("admin_sellers"))

@app.route("/admin/customers")
@admin_required
def admin_customers():
    customers = User.query.filter_by(role="customer").order_by(User.created_at.desc()).all()
    return render_template("admin_customers.html", customers=customers)

@app.route("/admin/products")
@admin_required
def admin_products():
    products = Product.query.order_by(Product.created_at.desc()).all()
    return render_template("admin_products.html", products=products)

@app.route("/admin/orders")
@admin_required
def admin_orders():
    orders = Order.query.order_by(Order.ordered_at.desc()).all()
    return render_template("admin_orders.html", orders=orders)

@app.route("/admin/orders/<int:order_id>/status", methods=["POST"])
@admin_required
def admin_order_status(order_id):
    status = request.form.get("status", "")
    if status not in ["Pending", "Accepted", "Preparing", "Out for Delivery", "Delivered", "Cancelled"]:
        flash("Invalid status.", "error")
        return redirect(url_for("admin_orders"))
    order = Order.query.get_or_404(order_id)
    order.status = status
    db.session.commit()
    flash(f"Order #{order.id} status changed to {status}.", "success")
    return redirect(url_for("admin_orders"))

@app.route("/admin/analytics")
@admin_required
def admin_analytics():
    orders = Order.query.all()
    revenue = round(sum(o.total_amount or 0 for o in orders), 2)
    return render_template("admin_analytics.html", revenue=revenue, orders=orders)

@app.route("/profile")
@login_required
def profile():
    user = User.query.get_or_404(session["user_id"])
    return render_template("profile.html", user=user)

@app.route("/ai")
def ai():
    return render_template("ai_assistant.html")

@app.route("/ai/chat", methods=["POST"])
@customer_required
def ai_chat():
    message = request.form.get("message", "").strip()
    if not message:
        return jsonify({"reply": "Please type a question first."}), 400

    products = Product.query.filter_by(is_available=True).order_by(Product.created_at.desc()).all()
    stores = User.query.filter_by(role="seller", approval_status="Approved").all()
    user_orders = Order.query.filter_by(user_id=session["user_id"]).order_by(Order.ordered_at.desc()).limit(5).all()

    reply = get_response(
        message,
        products=products,
        stores=stores,
        orders=user_orders
    )
    return jsonify({"reply": reply})

@app.route("/ai-picks")
@customer_required
def ai_picks():
    # Lightweight local recommendation engine: same-category first, then newest items.
    all_products = Product.query.filter_by(is_available=True).order_by(Product.created_at.desc()).all()
    cart_items = Cart.query.filter_by(user_id=session["user_id"]).all()
    cart_product_ids = {x.product_id for x in cart_items}
    recent_orders = Order.query.filter_by(user_id=session["user_id"]).order_by(Order.ordered_at.desc()).limit(5).all()
    purchased_ids = {item.product_id for order in recent_orders for item in order.items}
    history_ids = cart_product_ids | purchased_ids
    history = [p for p in all_products if p.id in history_ids]
    preferred_category = history[0].category if history else None
    recommended = []
    if preferred_category:
        recommended.extend([p for p in all_products if p.category == preferred_category and p.id not in history_ids])
    recommended.extend([p for p in all_products if p.id not in history_ids and p not in recommended])
    return render_template("ai_picks.html", recommendations=recommended[:8], preferred_category=preferred_category)

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/contact")
def contact():
    return render_template("contact.html")

@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404

with app.app_context():
    db.create_all()
    migrate()
    seed_admins()
    for folder in ["profile", "products", "stores"]:
        os.makedirs(os.path.join(app.config["UPLOAD_FOLDER"], folder), exist_ok=True)

if __name__ == "__main__":
    app.run(debug=True)
