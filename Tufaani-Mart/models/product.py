from models.database import db

class Product(db.Model):
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    product_name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Float, nullable=False, default=0)
    category = db.Column(db.String(100), nullable=False)
    brand = db.Column(db.String(100))
    unit = db.Column(db.String(50), default="1 piece")
    stock = db.Column(db.Integer, default=0)
    discount = db.Column(db.Float, default=0)
    rating = db.Column(db.Float, default=0)
    image = db.Column(db.String(255))
    seller_id = db.Column(db.Integer, nullable=False)
    store_id = db.Column(db.Integer)
    is_available = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
