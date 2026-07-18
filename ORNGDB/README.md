# ORNGDB – Order Management Web Application Overview

## 1️⃣ What the application does

ORNGDB is a small **order‑management** system built with **Django**. It supports three user roles:

| Role | Capabilities |
|------|--------------|
| **Customer** | Browse products, add items to a cart, place a quick bill (order), view and pay own orders. |
| **Delivery / Staff** | Create quick bills for customers, edit existing bills, settle old balances, view all orders for a store, toggle payment status, generate printable bills (text or image). |
| **Admin** | All delivery capabilities plus full admin access via Django admin. |

All data is persisted in a SQLite database (`db.sqlite3`). The UI uses **Bootstrap** and a custom color scheme (vibrant orange `#ff6600`) with modern typography (Outfit font).

---

## 2️⃣ Main data models (backend)

| Model | Purpose | Important fields |
|-------|---------|-----------------|
| **Order** | A transaction made by a customer (or delivery staff on behalf of a customer). | `customer`, `store_name`, `status` (`pending/received/cancelled`), `total_amount`, `old_balance`, `remaining_balance`, `payment_status` (`paid/unpaid`), timestamps. |
| **OrderItem** | One line‑item inside an `Order`. | `order`, `product`, `quantity`, `price_at_time`. |
| **CartItem** | Temporary items a customer adds before checking out. | `customer`, `product`, `quantity`. |
| **DraftBill** | A *quick‑bill* that a delivery user is editing; saved automatically so they can resume later. | `delivery_user`, `items_json` (product → qty map), `store_name`, `old_balance`. |
| **Product** (in the `products` app) | Catalog of sellable items. | `name`, `price`, `available` flag. |
| **User** (from the `users` app) | Extends Django’s auth user; adds `role` (`customer`, `delivery`, `admin`) and optional `store_name`. |

Helper properties on `Order` (`grand_total`, `remaining_due`, `cash_paid`, etc.) compute values on the fly.

---

## 3️⃣ Key URL endpoints & view functions

### Orders app (`orders/views.py`)

| URL (named) | View | What it does |
|-------------|------|--------------|
| `cancel_order` (POST) | `cancel_order(request, order_id)` | Delivery staff can cancel a *pending* order; otherwise returns an error. |
| `quick_bill_create` (POST) | `quick_bill_create(request)` | Delivery staff creates a **quick bill** (order). Handles custom prices, quantity ordering, old‑balance settlement, and updates any previously unpaid orders for the same store. |
| `toggle_order_payment_status` (POST) | `toggle_order_payment_status(request, order_id)` | Switches an order’s `payment_status` between *paid* / *unpaid* (or updates balances when a partial payment amount is supplied). |
| `pay_store_balance` (POST) | `pay_store_balance(request)` | Takes a bulk payment amount for a store and distributes it across the store’s unpaid orders (old‑balance first). |
| `share_order_bill` (GET) | `share_order_bill(request, order_id)` | Generates a **textual bill** (or PNG image) that can be shown to the customer. Supports two layout types (`type1` – compact, `type2` – detailed). |
| Draft‑Bill APIs (`draft_bill_get`, `draft_bill_save`, `draft_bill_clear`) | JSON endpoints used by the front‑end to persist the “quick‑bill” being edited. |
| `store_orders_api` (GET) | Returns all orders for a given store (JSON), used by the staff UI. |
| `order_edit_details_api` (GET) | Returns the editable details of a single order (JSON). |
| `customer_quick_bill_create` (POST) | Allows a **customer** to place a new order directly from a popup UI; similar logic to `quick_bill_create` but limited to the logged‑in customer. |

All POST views are protected by `@login_required` and (where needed) a role check (`request.user.role`).

### Products app (`products/views.py`)

Only a placeholder (`# Create your views here.`) – product data is mainly accessed via the Django admin or through the cart template.

### Users app

Contains admin registration, authentication, and role management (not shown in the snippet but typical Django setup).

---

## 4️⃣ Templates & UI components (what the user actually sees)

### Base layout – `templates/base.html`
*Defines the common header/footer, loads Bootstrap, static CSS, and a Google Font (Outfit) for a modern look.* All other pages extend this template.

### Cart page – `templates/orders/cart.html`
| UI Element | Button / Control | What it triggers |
|------------|------------------|------------------|
| **“Continue Shopping”** (link) | → `customer_menu` url | Takes the user back to the product list. |
| **Cart item list** | – | Shows each product name, quantity stepper, and subtotal (`₹{{ item.subtotal }}`). |
| **Quantity Stepper** (‑ / + buttons & numeric input) | Javascript intercept (`dec-btn`, `inc‑btn`, `.qty-input`) | Submits the surrounding `<form>` (`cart_update` view) as soon as the user clicks or changes the number. |
| **Total amount** | – | Sum of all line items (`₹{{ total_amount }}`). |
| **“Place Order”** (big orange button) | → `checkout` POST | Submits the bill to `quick_bill_create` (delivery staff) or `customer_quick_bill_create` (customer). |
| **Empty‑cart alert** | – | Shown when no items are in the cart; includes a link back to product browsing. |

The UI uses a **vibrant orange** (`#ff6600`) for primary actions, rounded‑pill buttons, and a subtle shadow for cards – matching the “rich aesthetics” guideline.

### My Orders page (`my_orders.html`)
(Not fully listed, but typical): shows a table of a user’s orders with status badges, “Pay” / “Toggle paid” buttons that call `toggle_order_payment_status`, and a “Share Bill” link that opens the printable bill view.

### Order Detail page (`order_detail.html`)
Displays a single order’s line items, old balance, total, cash paid, remaining balance, and payment status. Contains a **“Download Image”** button (adds `format=image` to the bill URL) that triggers the PNG rendering in `share_order_bill`.

---

## 5️⃣ Key buttons & their backend functions (chronological flow)

| Button (UI label) | Where it appears | Backend view / logic |
|-------------------|------------------|----------------------|
| **Continue Shopping** | Cart page | Simple GET redirect to product list (`customer_menu`). |
| **‑ / +** (quantity stepper) | Cart page | JavaScript captures click, updates the hidden `<input>` and submits the `cart_update` form (a POST to a view that updates `CartItem.quantity`). |
| **Place Order** | Cart page (footer) | Submits the whole cart to `quick_bill_create` (delivery) **or** `customer_quick_bill_create` (customer). The view validates items, calculates `total_amount`, settles any old balances, creates an `Order` and related `OrderItem`s, and clears the draft bill. |
| **Cancel Order** | Order list / detail (delivery) | Calls `cancel_order`; only works if `order.status == 'pending'`. |
| **Toggle Payment Status** | Order list (delivery) | Calls `toggle_order_payment_status`. If a numeric amount is provided, it reduces the remaining balance; otherwise it flips `payment_status` and updates `remaining_balance` accordingly. |
| **Pay Store Balance** | Store‑level UI (delivery) | Calls `pay_store_balance`. Takes a single amount and pays it off across all unpaid orders for that store, respecting old balances first. |
| **Share Bill** (text) | Order detail | Calls `share_order_bill` → returns JSON with `bill_text`. The front‑end can render this in a modal or copy it. |
| **Share Bill** (image) | Order detail (via a “download” button) | Same view, but `format=image` triggers Pillow code that draws the same bill text onto a PNG and streams it back (`image/png`). |
| **Save Draft** (auto) | Quick‑bill UI (delivery) | AJAX `draft_bill_save` stores the current items, store name, and old balance in `DraftBill`. On page reload, `draft_bill_get` restores the data. |
| **Clear Draft** | Quick‑bill UI (delivery) | AJAX `draft_bill_clear` deletes the user’s draft bill. |
| **Edit Order** (quick‑bill modal) | Staff UI | When an existing order is edited, `quick_bill_create` receives an `order_id` and updates the order (re‑creates line items, recomputes balances, settles prior unpaid orders). |
| **Pay Store Balance** (bulk) | Store‑level UI (delivery) | Same as above, but the view loops through unpaid orders, applying the payment sequentially. |
| **Logout / Login** | Throughout | Standard Django auth views (not shown in code). |

All POST endpoints expect a CSRF token (`{% csrf_token %}`) – the templates include it automatically.

---

## 6️⃣ How the business logic works (summary of the heavy lifting)

1. **Creating / Editing an Order**
   * Collect items (product → qty → price).
   * Compute `total_amount = Σ price × qty`.
   * Determine `old_balance` – the sum of any prior unpaid balances for that customer/store (or 0).
   * `grand_total = total_amount + old_balance`.
   * Save the `Order` with `remaining_balance = grand_total` (or a custom value when editing).
   * For **editing**, the old order’s items are deleted then rebuilt; any previous unpaid orders for the same store are marked **paid** if the old balance is cleared.

2. **Settlement of Old Balance**
   * When a payment is recorded (`toggle_order_payment_status` or `pay_store_balance`), the code first reduces the **old balance** portion of the order, then distributes any remaining amount to prior unpaid orders for the same store (chronological order).

3. **Bill Rendering**
   * `share_order_bill` builds a plain‑text receipt with a fixed width (`w`, default 32 chars). The receipt contains header, order metadata, line‑item list, totals, old‑balance, cash‑paid, new‑balance, and a payment‑status line.
   * When `format=image` is requested, Pillow draws each line onto a white canvas, using a monospaced font (`RobotoMono`).

4. **Draft‑Bill Persistence**
   * The UI serialises the current cart (`items_json`) and posts it to `draft_bill_save`.
   * When the staff returns later, `draft_bill_get` pre‑populates the UI, allowing them to resume where they left off.

---

## 7️⃣ User‑role checks (security)

* Every view is wrapped with `@login_required`.
* Most staff‑only views check `request.user.role != 'delivery'` (or `admin`).
* Customers can only access their own orders; delivery/admin can see all.

If a role check fails, the view returns **403 Unauthorized** JSON.

---

## 8️⃣ Static assets & styling

* **Bootstrap** provides the grid, buttons, alerts, and responsive layout.
* Custom CSS (in `static/`) adds the orange accent, rounded‑pill buttons, and subtle box‑shadows → a modern, premium look.
* Icons are loaded from **Bootstrap‑Icons** (used for the stepper’s “‑” and “+”).

---

## 9️⃣ How the pieces fit together (high‑level flow)

1. **Customer** → visits product list → adds items → cart page.
2. **Cart → “Place Order”** → POST → `customer_quick_bill_create` → creates an `Order`.
3. **Delivery staff** → open “Quick Bill” UI → assemble a draft → “Place Order” → `quick_bill_create`.
4. **After placement**, staff can **share** the bill (text or image), **pay store balance**, or **toggle payment status** as needed.
5. All **order changes** automatically recalculate balances, old‑balance settlements, and update the `payment_status` flag.

---

**TL;DR**
- **Models**: Order ↔ OrderItem, CartItem, DraftBill, Product, User.
- **Views**: create/cancel/edit orders, toggle/pay status, generate printable bills, manage draft quick‑bills, expose JSON APIs for the front‑end.
- **Templates**: base layout, cart page (with quantity stepper), order list/detail, printable bill.
- **Buttons**: “Continue Shopping”, quantity stepper (‑/ +), “Place Order”, “Cancel Order”, “Toggle Payment”, “Pay Store Balance”, “Share Bill (text)”, “Share Bill (image)”.
- **Logic**: automatically settles old balances, distributes payments across unpaid orders, creates a nicely‑formatted receipt, and persists drafts so staff never lose work.

---

*If you need a deeper dive into any specific view, template, or model, just let me know!*
