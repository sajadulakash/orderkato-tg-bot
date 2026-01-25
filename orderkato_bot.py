#!/usr/bin/env python3
"""
OrderKato Telegram Bot
A simple order management bot for field operations.

Directory Structure:
- config/token.txt      : Telegram bot token
- data/shops.csv        : Shop and area data
- data/products.csv     : Product SKU data
- data/orders/          : Daily order files (auto-generated)
"""

import csv
import os
import logging
from datetime import datetime
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Base directory (where the script is located)
BASE_DIR = Path(__file__).parent.resolve()

# File paths
TOKEN_FILE = BASE_DIR / "config" / "token.txt"
ORDER_COUNTER_FILE = BASE_DIR / "config" / "order.txt"
SHOPS_FILE = BASE_DIR / "data" / "shops.csv"
PRODUCTS_FILE = BASE_DIR / "data" / "products.csv"
ORDERS_DIR = BASE_DIR / "data" / "orders"

# Conversation states
SELECT_AREA, SELECT_SHOP, SELECT_PRODUCTS, ENTER_QUANTITY, CONFIRM_ORDER = range(5)


def read_token() -> str:
    """Read the Telegram bot token from config file."""
    try:
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            token = f.read().strip()
            if not token or token == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
                raise ValueError("Please set your bot token in config/token.txt")
            return token
    except FileNotFoundError:
        raise FileNotFoundError(f"Token file not found: {TOKEN_FILE}")


def read_shops() -> list[dict]:
    """Read shops data from CSV file."""
    shops = []
    try:
        with open(SHOPS_FILE, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                shops.append({
                    "area_name": row.get("area_name", "").strip(),
                    "shop_name": row.get("shop_name", "").strip(),
                    "shop_address": row.get("shop_address", "").strip(),
                })
    except FileNotFoundError:
        logger.error(f"Shops file not found: {SHOPS_FILE}")
    return shops


def read_products() -> list[dict]:
    """Read products data from CSV file."""
    products = []
    try:
        with open(PRODUCTS_FILE, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                product_name = row.get("product_name", "").strip()
                if product_name:  # Only add if product_name is not empty
                    products.append({
                        "product_name": product_name,
                    })
    except FileNotFoundError:
        logger.error(f"Products file not found: {PRODUCTS_FILE}")
    return products


def get_unique_areas() -> list[str]:
    """Get unique area names from shops data."""
    shops = read_shops()
    areas = list(dict.fromkeys(shop["area_name"] for shop in shops if shop["area_name"]))
    return areas


def get_shops_by_area(area_name: str) -> list[dict]:
    """Get all shops in a specific area."""
    shops = read_shops()
    return [shop for shop in shops if shop["area_name"] == area_name]


def get_next_order_number() -> int:
    """
    Get the next order number from counter file, increment and save it.
    Returns the new order number.
    """
    # Ensure config directory exists
    ORDER_COUNTER_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    # Read current number
    current_num = 0
    if ORDER_COUNTER_FILE.exists():
        try:
            with open(ORDER_COUNTER_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content.isdigit():
                    current_num = int(content)
        except Exception:
            current_num = 0
    
    # Increment
    next_num = current_num + 1
    
    # Save new number
    with open(ORDER_COUNTER_FILE, "w", encoding="utf-8") as f:
        f.write(str(next_num))
    
    return next_num


def get_user_orders(username: str) -> list[dict]:
    """
    Get all orders for a specific user from all order files.
    Returns a list of unique orders with their status.
    """
    orders = {}
    
    # Check if orders directory exists
    if not ORDERS_DIR.exists():
        return []
    
    # Read all order files
    for order_file in ORDERS_DIR.glob("orders_*.csv"):
        try:
            with open(order_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Check if this order belongs to the user
                    if row.get("username", "").lower() == username.lower():
                        order_id = row.get("order_id", "")
                        if order_id:
                            # Group by order_id, keep the status
                            if order_id not in orders:
                                orders[order_id] = {
                                    "order_id": order_id,
                                    "order_date": row.get("order_date", ""),
                                    "order_time": row.get("order_time", ""),
                                    "area_name": row.get("area_name", ""),
                                    "shop_name": row.get("shop_name", ""),
                                    "status": row.get("status", "pending"),
                                    "items": []
                                }
                            # Add item to the order
                            orders[order_id]["items"].append({
                                "product_name": row.get("product_name", ""),
                                "quantity": row.get("quantity", "0")
                            })
        except Exception as e:
            logger.error(f"Error reading order file {order_file}: {e}")
    
    # Convert to list and sort by date/time (newest first)
    order_list = list(orders.values())
    order_list.sort(key=lambda x: (x["order_date"], x["order_time"]), reverse=True)
    
    return order_list


def save_order(order_data: dict) -> tuple[str, str]:
    """
    Save order to daily CSV file.
    Creates a new file if it doesn't exist for the current date.
    Returns tuple of (filename, order_id).
    """
    # Ensure orders directory exists
    ORDERS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Generate filename with current date
    today = datetime.now().strftime("%Y-%m-%d")
    filename = f"orders_{today}.csv"
    filepath = ORDERS_DIR / filename
    
    # Check if file exists to determine if we need to write header
    file_exists = filepath.exists()
    
    # Get next order number and generate short order ID
    order_num = get_next_order_number()
    order_id = f"ord{order_num}"
    now = datetime.now()
    
    # Write order data
    with open(filepath, "a", newline="", encoding="utf-8") as f:
        fieldnames = ["order_id", "order_date", "order_time", "username", "area_name", "shop_name", "product_name", "quantity", "status"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        
        if not file_exists:
            writer.writeheader()
        
        # Current timestamp
        order_date = now.strftime("%Y-%m-%d")
        order_time = now.strftime("%H:%M:%S")
        
        # Write each product as a separate row (same order_id for all items in this order)
        for product_name, qty in order_data["items"].items():
            if qty > 0:
                writer.writerow({
                    "order_id": order_id,
                    "order_date": order_date,
                    "order_time": order_time,
                    "username": order_data.get("username", ""),
                    "area_name": order_data["area_name"],
                    "shop_name": order_data["shop_name"],
                    "product_name": product_name,
                    "quantity": qty,
                    "status": "pending",
                })
    
    return filename, order_id


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send welcome message when /start command is issued."""
    welcome_text = (
        "👋 Welcome to OrderKato Bot!\n\n"
        "This bot helps you place orders for shops.\n\n"
        "📝 Commands:\n"
        "/order - Start a new order\n"
        "/status - Check your order status\n"
        "/cancel - Cancel current order\n"
        "/help - Show help message"
    )
    await update.message.reply_text(welcome_text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send help message when /help command is issued."""
    help_text = (
        "📖 How to use OrderKato Bot:\n\n"
        "1. Type /order to start a new order\n"
        "2. Select an area from the list\n"
        "3. Select a shop from that area\n"
        "4. Select products and enter quantities\n"
        "5. Confirm your order\n\n"
        "📝 Commands:\n"
        "/order - Start a new order\n"
        "/status - Check your order status\n"
        "/cancel - Cancel current order\n"
        "/help - Show this help message"
    )
    await update.message.reply_text(help_text)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show order status for the user."""
    user = update.effective_user
    username = user.username or user.first_name or str(user.id)
    
    # Get orders for this user
    orders = get_user_orders(username)
    
    if not orders:
        await update.message.reply_text(
            f"📋 No orders found for {username}.\n\n"
            "Type /order to place a new order."
        )
        return
    
    # Build status message
    message_text = f"📋 ORDER STATUS FOR {username.upper()}\n"
    message_text += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    for order in orders[:10]:  # Show last 10 orders
        status = order["status"].upper()
        if status == "PENDING":
            status_icon = "🟡"
        elif status == "DELIVERED":
            status_icon = "✅"
        elif status == "CANCELLED":
            status_icon = "❌"
        else:
            status_icon = "⚪"
        
        # Build items summary
        items_summary = ", ".join([f"{item['product_name']} x{item['quantity']}" for item in order["items"][:3]])
        if len(order["items"]) > 3:
            items_summary += f" (+{len(order['items']) - 3} more)"
        
        message_text += f"{status_icon} {order['order_id']}\n"
        message_text += f"   📍 {order['shop_name']} ({order['area_name']})\n"
        message_text += f"   📦 {items_summary}\n"
        message_text += f"   📌 Status: {status}\n"
        message_text += f"   🕐 {order['order_date']} {order['order_time']}\n\n"
    
    if len(orders) > 10:
        message_text += f"... and {len(orders) - 10} more orders\n\n"
    
    message_text += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    message_text += "Type /order to place a new order."
    
    await update.message.reply_text(message_text)


async def order_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the order process - show area selection."""
    # Clear any previous order data
    context.user_data.clear()
    
    areas = get_unique_areas()
    
    if not areas:
        await update.message.reply_text(
            "❌ No areas found. Please check the shops.csv file."
        )
        return ConversationHandler.END
    
    # Create inline keyboard with areas
    keyboard = []
    for area in areas:
        keyboard.append([InlineKeyboardButton(area, callback_data=f"area:{area}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "📍 **Select an Area:**",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    
    return SELECT_AREA


async def area_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle area selection - show shops in selected area."""
    query = update.callback_query
    await query.answer()
    
    # Extract area name from callback data
    area_name = query.data.replace("area:", "")
    context.user_data["area_name"] = area_name
    
    # Get shops in this area
    shops = get_shops_by_area(area_name)
    
    if not shops:
        await query.edit_message_text(
            f"❌ No shops found in {area_name}."
        )
        return ConversationHandler.END
    
    # Create inline keyboard with shops
    keyboard = []
    for shop in shops:
        display_text = shop["shop_name"]
        if shop["shop_address"]:
            display_text += f" ({shop['shop_address']})"
        keyboard.append([
            InlineKeyboardButton(display_text, callback_data=f"shop:{shop['shop_name']}")
        ])
    
    # Add back button
    keyboard.append([InlineKeyboardButton("◀️ Back to Areas", callback_data="back:areas")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"📍 Area: **{area_name}**\n\n🏪 **Select a Shop:**",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    
    return SELECT_SHOP


async def back_to_areas(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Go back to area selection."""
    query = update.callback_query
    await query.answer()
    
    areas = get_unique_areas()
    
    keyboard = []
    for area in areas:
        keyboard.append([InlineKeyboardButton(area, callback_data=f"area:{area}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "📍 **Select an Area:**",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    
    return SELECT_AREA


async def shop_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle shop selection - show product selection."""
    query = update.callback_query
    await query.answer()
    
    # Extract shop name from callback data
    shop_name = query.data.replace("shop:", "")
    context.user_data["shop_name"] = shop_name
    context.user_data["items"] = {}  # Initialize items dictionary
    context.user_data["current_product"] = None
    
    # Show product selection
    return await show_product_selection(query, context)


async def show_product_selection(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Display product selection interface."""
    products = read_products()
    
    if not products:
        await query.edit_message_text(
            "❌ No products found. Please check the products.csv file."
        )
        return ConversationHandler.END
    
    area_name = context.user_data.get("area_name", "")
    shop_name = context.user_data.get("shop_name", "")
    items = context.user_data.get("items", {})
    
    # Build order summary if there are items
    order_summary = ""
    if items:
        order_summary = "\n\n📦 **Current Order:**\n"
        for product_name, qty in items.items():
            if qty > 0:
                order_summary += f"• {product_name}: {qty}\n"
    
    # Create inline keyboard with products
    keyboard = []
    for product in products:
        name = product["product_name"]
        qty = items.get(name, 0)
        
        if qty > 0:
            display_text = f"✅ {name} ({qty})"
        else:
            display_text = f"➕ {name}"
        
        keyboard.append([
            InlineKeyboardButton(display_text, callback_data=f"product:{name}")
        ])
    
    # Add action buttons
    action_row = []
    if items and any(q > 0 for q in items.values()):
        action_row.append(InlineKeyboardButton("✔️ Confirm Order", callback_data="action:confirm"))
        action_row.append(InlineKeyboardButton("🗑️ Clear All", callback_data="action:clear"))
    
    if action_row:
        keyboard.append(action_row)
    
    keyboard.append([InlineKeyboardButton("◀️ Back to Shops", callback_data=f"back:shops")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_text = (
        f"📍 Area: **{area_name}**\n"
        f"🏪 Shop: **{shop_name}**\n\n"
        f"🛒 **Select Products:**\n"
        f"Tap a product to add/edit quantity"
        f"{order_summary}"
    )
    
    await query.edit_message_text(
        message_text,
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    
    return SELECT_PRODUCTS


async def product_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle product selection - ask for quantity."""
    query = update.callback_query
    await query.answer()
    
    # Extract product name from callback data
    product_name = query.data.replace("product:", "")
    context.user_data["current_product"] = product_name
    
    # Get product info
    products = read_products()
    product = next((p for p in products if p["product_name"] == product_name), None)
    
    if not product:
        return await show_product_selection(query, context)
    
    current_qty = context.user_data.get("items", {}).get(product_name, 0)
    
    # Create quick quantity buttons
    keyboard = [
        [
            InlineKeyboardButton("1", callback_data="qty:1"),
            InlineKeyboardButton("2", callback_data="qty:2"),
            InlineKeyboardButton("3", callback_data="qty:3"),
            InlineKeyboardButton("5", callback_data="qty:5"),
        ],
        [
            InlineKeyboardButton("10", callback_data="qty:10"),
            InlineKeyboardButton("20", callback_data="qty:20"),
            InlineKeyboardButton("50", callback_data="qty:50"),
            InlineKeyboardButton("100", callback_data="qty:100"),
        ],
    ]
    
    if current_qty > 0:
        keyboard.append([
            InlineKeyboardButton(f"🗑️ Remove (Current: {current_qty})", callback_data="qty:0")
        ])
    
    keyboard.append([
        InlineKeyboardButton("◀️ Back to Products", callback_data="back:products")
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_text = (
        f"📦 **{product['product_name']}**\n\n"
    )
    
    if current_qty > 0:
        message_text += f"Current quantity: {current_qty}\n\n"
    
    message_text += "Select quantity or type a number:"
    
    await query.edit_message_text(
        message_text,
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    
    return ENTER_QUANTITY


async def quantity_button_pressed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle quantity button press."""
    query = update.callback_query
    await query.answer()
    
    qty = int(query.data.replace("qty:", ""))
    product_name = context.user_data.get("current_product")
    
    if not product_name:
        return await show_product_selection(query, context)
    
    if "items" not in context.user_data:
        context.user_data["items"] = {}
    
    if qty > 0:
        context.user_data["items"][product_name] = qty
    elif product_name in context.user_data["items"]:
        del context.user_data["items"][product_name]
    
    # Return to product selection
    return await show_product_selection(query, context)


async def quantity_typed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle manually typed quantity."""
    text = update.message.text.strip()
    
    try:
        qty = int(text)
        if qty < 0:
            raise ValueError("Negative quantity")
        if qty > 9999:
            await update.message.reply_text("❌ Maximum quantity is 9999. Please enter a smaller number.")
            return ENTER_QUANTITY
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid number.")
        return ENTER_QUANTITY
    
    product_name = context.user_data.get("current_product")
    
    if not product_name:
        await update.message.reply_text("❌ No product selected. Please start over with /order")
        return ConversationHandler.END
    
    if "items" not in context.user_data:
        context.user_data["items"] = {}
    
    if qty > 0:
        context.user_data["items"][product_name] = qty
    elif product_name in context.user_data["items"]:
        del context.user_data["items"][product_name]
    
    if qty > 0:
        await update.message.reply_text(f"✅ Added: {product_name} × {qty}")
    else:
        await update.message.reply_text(f"🗑️ Removed: {product_name}")
    
    # Show product selection again
    # We need to send a new message with the keyboard
    return await show_product_selection_new_message(update, context)


async def show_product_selection_new_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Display product selection interface as a new message."""
    products = read_products()
    
    if not products:
        await update.message.reply_text(
            "❌ No products found. Please check the products.csv file."
        )
        return ConversationHandler.END
    
    area_name = context.user_data.get("area_name", "")
    shop_name = context.user_data.get("shop_name", "")
    items = context.user_data.get("items", {})
    
    # Build order summary if there are items
    order_summary = ""
    if items:
        order_summary = "\n\n📦 **Current Order:**\n"
        for product_name, qty in items.items():
            if qty > 0:
                order_summary += f"• {product_name}: {qty}\n"
    
    # Create inline keyboard with products
    keyboard = []
    for product in products:
        name = product["product_name"]
        qty = items.get(name, 0)
        
        if qty > 0:
            display_text = f"✅ {name} ({qty})"
        else:
            display_text = f"➕ {name}"
        
        keyboard.append([
            InlineKeyboardButton(display_text, callback_data=f"product:{name}")
        ])
    
    # Add action buttons
    action_row = []
    if items and any(q > 0 for q in items.values()):
        action_row.append(InlineKeyboardButton("✔️ Confirm Order", callback_data="action:confirm"))
        action_row.append(InlineKeyboardButton("🗑️ Clear All", callback_data="action:clear"))
    
    if action_row:
        keyboard.append(action_row)
    
    keyboard.append([InlineKeyboardButton("◀️ Back to Shops", callback_data=f"back:shops")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_text = (
        f"📍 Area: **{area_name}**\n"
        f"🏪 Shop: **{shop_name}**\n\n"
        f"🛒 **Select Products:**\n"
        f"Tap a product to add/edit quantity"
        f"{order_summary}"
    )
    
    await update.message.reply_text(
        message_text,
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    
    return SELECT_PRODUCTS


async def back_to_shops(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Go back to shop selection."""
    query = update.callback_query
    await query.answer()
    
    area_name = context.user_data.get("area_name", "")
    shops = get_shops_by_area(area_name)
    
    keyboard = []
    for shop in shops:
        display_text = shop["shop_name"]
        if shop["shop_address"]:
            display_text += f" ({shop['shop_address']})"
        keyboard.append([
            InlineKeyboardButton(display_text, callback_data=f"shop:{shop['shop_name']}")
        ])
    
    keyboard.append([InlineKeyboardButton("◀️ Back to Areas", callback_data="back:areas")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"📍 Area: **{area_name}**\n\n🏪 **Select a Shop:**",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    
    return SELECT_SHOP


async def back_to_products(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Go back to product selection."""
    query = update.callback_query
    await query.answer()
    
    return await show_product_selection(query, context)


async def clear_all_items(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Clear all items from the current order."""
    query = update.callback_query
    await query.answer("All items cleared!")
    
    context.user_data["items"] = {}
    
    return await show_product_selection(query, context)


async def confirm_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show order confirmation screen."""
    query = update.callback_query
    await query.answer()
    
    products = read_products()
    items = context.user_data.get("items", {})
    area_name = context.user_data.get("area_name", "")
    shop_name = context.user_data.get("shop_name", "")
    
    if not items or not any(q > 0 for q in items.values()):
        await query.edit_message_text("❌ No items in order.")
        return ConversationHandler.END
    
    # Build order summary
    order_summary = ""
    total_items = 0
    for product_name, qty in items.items():
        if qty > 0:
            order_summary += f"  • {product_name} x {qty}\n"
            total_items += qty
    
    message_text = (
        "📋 ORDER SUMMARY\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"📍 Area: {area_name}\n"
        f"🏪 Shop: {shop_name}\n\n"
        f"📦 Items:\n{order_summary}\n"
        f"📊 Total items: {total_items}\n\n"
        "Please confirm your order:"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("✅ SUBMIT ORDER", callback_data="action:submit"),
            InlineKeyboardButton("❌ Cancel", callback_data="action:cancel"),
        ],
        [InlineKeyboardButton("✏️ Edit Order", callback_data="back:products")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        message_text,
        reply_markup=reply_markup
    )
    
    return CONFIRM_ORDER


async def submit_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Submit the order and save to CSV."""
    query = update.callback_query
    await query.answer("Submitting order...")
    
    # Get user info
    user = query.from_user
    
    # Prepare order data
    order_data = {
        "user_id": user.id,
        "username": user.username or user.first_name or str(user.id),
        "area_name": context.user_data.get("area_name", ""),
        "shop_name": context.user_data.get("shop_name", ""),
        "items": context.user_data.get("items", {}),
    }
    
    # Save order
    try:
        filename, order_id = save_order(order_data)
        
        # Build order summary
        items = order_data["items"]
        order_summary = ""
        total_qty = 0
        for product_name, qty in items.items():
            if qty > 0:
                order_summary += f"  • {product_name} x {qty}\n"
                total_qty += qty
        
        message_text = (
            "✅ ORDER SUBMITTED SUCCESSFULLY!\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🆔 Order ID:\n   {order_id}\n\n"
            f"👤 User: {order_data['username']}\n\n"
            f"📍 Area: {order_data['area_name']}\n"
            f"🏪 Shop: {order_data['shop_name']}\n\n"
            f"📦 Ordered Items:\n{order_summary}\n"
            f"📊 Total Quantity: {total_qty}\n\n"
            f"📌 Status: PENDING\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Type /order to place another order."
        )
        
        await query.edit_message_text(message_text)
        
    except Exception as e:
        logger.error(f"Error saving order: {e}")
        await query.edit_message_text(
            "❌ Error saving order. Please try again or contact support."
        )
    
    # Clear user data
    context.user_data.clear()
    
    return ConversationHandler.END


async def cancel_order_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel order via button."""
    query = update.callback_query
    await query.answer("Order cancelled")
    
    await query.edit_message_text(
        "❌ Order cancelled.\n\nType /order to start a new order."
    )
    
    context.user_data.clear()
    return ConversationHandler.END


async def cancel_order_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel order via /cancel command."""
    await update.message.reply_text(
        "❌ Order cancelled.\n\nType /order to start a new order."
    )
    
    context.user_data.clear()
    return ConversationHandler.END


async def handle_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle action buttons (confirm, clear, submit, cancel)."""
    query = update.callback_query
    action = query.data.replace("action:", "")
    
    if action == "confirm":
        return await confirm_order(update, context)
    elif action == "clear":
        return await clear_all_items(update, context)
    elif action == "submit":
        return await submit_order(update, context)
    elif action == "cancel":
        return await cancel_order_button(update, context)
    
    return SELECT_PRODUCTS


async def handle_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle back navigation buttons."""
    query = update.callback_query
    destination = query.data.replace("back:", "")
    
    if destination == "areas":
        return await back_to_areas(update, context)
    elif destination == "shops":
        return await back_to_shops(update, context)
    elif destination == "products":
        return await back_to_products(update, context)
    
    return SELECT_PRODUCTS


def main() -> None:
    """Run the bot."""
    # Read token
    try:
        token = read_token()
    except (FileNotFoundError, ValueError) as e:
        logger.error(f"Token error: {e}")
        print(f"\n❌ Error: {e}")
        print("\nPlease create config/token.txt with your Telegram bot token.")
        print("Get your token from @BotFather on Telegram.")
        return
    
    # Ensure required directories exist
    ORDERS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Check if data files exist
    if not SHOPS_FILE.exists():
        logger.warning(f"Shops file not found: {SHOPS_FILE}")
        print(f"\n⚠️ Warning: {SHOPS_FILE} not found")
    
    if not PRODUCTS_FILE.exists():
        logger.warning(f"Products file not found: {PRODUCTS_FILE}")
        print(f"\n⚠️ Warning: {PRODUCTS_FILE} not found")
    
    # Create the Application
    application = Application.builder().token(token).build()
    
    # Create conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("order", order_start)],
        states={
            SELECT_AREA: [
                CallbackQueryHandler(area_selected, pattern=r"^area:"),
            ],
            SELECT_SHOP: [
                CallbackQueryHandler(shop_selected, pattern=r"^shop:"),
                CallbackQueryHandler(handle_back, pattern=r"^back:"),
            ],
            SELECT_PRODUCTS: [
                CallbackQueryHandler(product_selected, pattern=r"^product:"),
                CallbackQueryHandler(handle_action, pattern=r"^action:"),
                CallbackQueryHandler(handle_back, pattern=r"^back:"),
            ],
            ENTER_QUANTITY: [
                CallbackQueryHandler(quantity_button_pressed, pattern=r"^qty:"),
                CallbackQueryHandler(handle_back, pattern=r"^back:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, quantity_typed),
            ],
            CONFIRM_ORDER: [
                CallbackQueryHandler(handle_action, pattern=r"^action:"),
                CallbackQueryHandler(handle_back, pattern=r"^back:"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_order_command)],
    )
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(conv_handler)
    
    # Start the bot
    print("\n🤖 OrderKato Bot is starting...")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"📁 Shops file: {SHOPS_FILE}")
    print(f"📁 Products file: {PRODUCTS_FILE}")
    print(f"📁 Orders directory: {ORDERS_DIR}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("Press Ctrl+C to stop the bot.\n")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
