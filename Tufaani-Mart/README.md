# Tufaani Mart - Corrected 3-Account Build

This build fixes the recent errors without deleting or recreating your existing `database.db`.

## Fixed
- `login_required` works as a decorator.
- `role_required` / `seller_required` / `admin_required` / `customer_required` work correctly.
- Seller Add Product no longer calls a decorator like a normal function.
- Product image uploads are saved to `uploads/products/`.
- Uploaded product images are served through Flask and displayed on Products/Home pages.
- Existing SQLite database is preserved; missing columns are added automatically.
- `orders.payment_method`, `orders.delivery_address`, `orders.phone`, and `order_items.price/subtotal` are migrated when missing.
- Seller can open Manage Orders and change Pending / Accepted / Preparing / Out for Delivery / Delivered / Cancelled.
- Seller dashboard uses compact spacing.

## Install / run
1. Keep your existing `database.db` in the project folder.
2. Replace the project files with this build, or extract this ZIP over your existing project folder.
3. Do NOT delete `database.db`.
4. Install dependencies:
   `pip install -r requirements.txt`
5. Run:
   `python app.py`

Permanent admin accounts:
- khushi.singh@tufaanimart.com
- rahul.gope@tufaanimart.com
- anuj.kharel@tufaanimart.com

Permanent admin password: `Tufaani@Admin2026`
