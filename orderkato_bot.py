#!/usr/bin/env python3
"""
OrderKato Telegram Bot
A simple order management bot for field operations.

Database: MySQL (Orderkatodb)
- Host: 127.0.0.1
- Port: 3306
"""

import logging
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path
import mysql.connector
from mysql.connector import Error
from PIL import Image
from PIL.ExifTags import TAGS
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

# MySQL Database Configuration
DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "database": "Orderkatodb",
    "user": "sajadulakash",
    "password": "fringe_core",
}

# Conversation states
SELECT_AREA, SELECT_SHOP, VERIFY_PHOTO, SELECT_PRODUCTS, ENTER_QUANTITY, CONFIRM_ORDER = range(6)

# Photo verification settings
SHOP_IMAGE_DIR = BASE_DIR / "ShopImage"
PHOTO_MAX_AGE_SECONDS = 60  # 1 minute

# Ensure ShopImage directory exists
SHOP_IMAGE_DIR.mkdir(parents=True, exist_ok=True)


def get_photo_datetime(image_path: str) -> datetime | None:
    """
    Extract the datetime when the photo was taken from EXIF data.
    Returns None if no EXIF datetime found.
    """
    try:
        image = Image.open(image_path)
        exif_data = image._getexif()
        
        if not exif_data:
            return None
        
        # Look for DateTimeOriginal (36867) or DateTime (306) tags
        datetime_tags = {
            36867: "DateTimeOriginal",  # When photo was taken
            36868: "DateTimeDigitized",  # When photo was digitized
            306: "DateTime",  # File modification time
        }
        
        for tag_id in [36867, 36868, 306]:  # Priority order
            if tag_id in exif_data:
                datetime_str = exif_data[tag_id]
                # EXIF datetime format: "YYYY:MM:DD HH:MM:SS"
                try:
                    photo_datetime = datetime.strptime(datetime_str, "%Y:%m:%d %H:%M:%S")
                    return photo_datetime
                except ValueError:
                    continue
        
        return None
    except Exception as e:
        logger.error(f"Error reading EXIF data: {e}")
        return None


def save_shop_photo(file_path: str, shop_id: int, user_id: int) -> str:
    """
    Save the verified photo to ShopImage folder.
    Returns the relative path to the saved image.
    """
    # Generate unique filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = uuid.uuid4().hex[:8]
    extension = Path(file_path).suffix or ".jpg"
    filename = f"shop_{shop_id}_user_{user_id}_{timestamp}_{unique_id}{extension}"
    
    destination = SHOP_IMAGE_DIR / filename
    
    # Copy the file to ShopImage folder
    import shutil
    shutil.copy2(file_path, destination)
    
    return f"ShopImage/{filename}"


def get_db_connection():
    """Create and return a database connection."""
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        return connection
    except Error as e:
        logger.error(f"Database connection error: {e}")
        return None


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
    """Read shops data from database."""
    shops = []
    connection = get_db_connection()
    if not connection:
        return shops
    
    try:
        cursor = connection.cursor(dictionary=True)
        query = """
            SELECT s.shop_id, s.shop_name, s.address as shop_address, 
                   s.owner_name, s.phone_number,
                   a.area_name, a.area_id
            FROM shops s
            JOIN area a ON s.area_id = a.area_id
            WHERE a.area_type = 'Area'
            ORDER BY a.area_name, s.shop_name
        """
        cursor.execute(query)
        shops = cursor.fetchall()
        cursor.close()
    except Error as e:
        logger.error(f"Error reading shops: {e}")
    finally:
        connection.close()
    
    return shops


def read_products() -> list[dict]:
    """Read products data from database."""
    products = []
    connection = get_db_connection()
    if not connection:
        return products
    
    try:
        cursor = connection.cursor(dictionary=True)
        query = """
            SELECT p.product_id, p.product_name, p.price, p.discount,
                   b.brand_name
            FROM product p
            JOIN brand b ON p.brand_id = b.brand_id
            ORDER BY b.brand_name, p.product_name
        """
        cursor.execute(query)
        products = cursor.fetchall()
        cursor.close()
    except Error as e:
        logger.error(f"Error reading products: {e}")
    finally:
        connection.close()
    
    return products


def get_unique_areas() -> list[dict]:
    """Get unique areas from database."""
    areas = []
    connection = get_db_connection()
    if not connection:
        return areas
    
    try:
        cursor = connection.cursor(dictionary=True)
        query = """
            SELECT area_id, area_name 
            FROM area 
            WHERE area_type = 'Area'
            ORDER BY area_name
        """
        cursor.execute(query)
        areas = cursor.fetchall()
        cursor.close()
    except Error as e:
        logger.error(f"Error reading areas: {e}")
    finally:
        connection.close()
    
    return areas


def get_shops_by_area(area_id: int) -> list[dict]:
    """Get all shops in a specific area."""
    shops = []
    connection = get_db_connection()
    if not connection:
        return shops
    
    try:
        cursor = connection.cursor(dictionary=True)
        query = """
            SELECT shop_id, shop_name, address as shop_address, 
                   owner_name, phone_number
            FROM shops
            WHERE area_id = %s
            ORDER BY shop_name
        """
        cursor.execute(query, (area_id,))
        shops = cursor.fetchall()
        cursor.close()
    except Error as e:
        logger.error(f"Error reading shops by area: {e}")
    finally:
        connection.close()
    
    return shops


def get_user_by_telegram(tel_username: str) -> dict | None:
    """Get user from database by telegram username."""
    connection = get_db_connection()
    if not connection:
        return None
    
    user = None
    try:
        cursor = connection.cursor(dictionary=True)
        query = "SELECT * FROM users WHERE tel_username = %s"
        cursor.execute(query, (tel_username,))
        user = cursor.fetchone()
        cursor.close()
    except Error as e:
        logger.error(f"Error reading user: {e}")
    finally:
        connection.close()
    
    return user


def get_user_orders(user_id: int) -> list[dict]:
    """Get all orders for a specific user from database."""
    orders = []
    connection = get_db_connection()
    if not connection:
        return orders
    
    try:
        cursor = connection.cursor(dictionary=True)
        query = """
            SELECT o.order_id, o.order_timestamp, o.order_status,
                   s.shop_name, a.area_name
            FROM orders o
            LEFT JOIN shops s ON o.shop_id = s.shop_id
            LEFT JOIN area a ON s.area_id = a.area_id
            WHERE o.user_id = %s
            ORDER BY o.order_timestamp DESC
            LIMIT 20
        """
        cursor.execute(query, (user_id,))
        order_rows = cursor.fetchall()
        
        for order_row in order_rows:
            # Get items for this order
            items_query = """
                SELECT p.product_name, op.quantity
                FROM order_product op
                JOIN product p ON op.product_id = p.product_id
                WHERE op.order_id = %s
            """
            cursor.execute(items_query, (order_row['order_id'],))
            items = cursor.fetchall()
            
            orders.append({
                "order_id": f"ord{order_row['order_id']}",
                "order_date": order_row['order_timestamp'].strftime("%Y-%m-%d"),
                "order_time": order_row['order_timestamp'].strftime("%H:%M:%S"),
                "area_name": order_row['area_name'] or "N/A",
                "shop_name": order_row['shop_name'] or "N/A",
                "status": order_row['order_status'],
                "items": items
            })
        
        cursor.close()
    except Error as e:
        logger.error(f"Error reading user orders: {e}")
    finally:
        connection.close()
    
    return orders


def update_order_status(order_id: str, new_status: str) -> bool:
    """Update the status of an order in database."""
    connection = get_db_connection()
    if not connection:
        return False
    
    try:
        # Extract numeric ID from "ord123" format
        numeric_id = int(order_id.replace("ord", ""))
        
        cursor = connection.cursor()
        query = "UPDATE orders SET order_status = %s WHERE order_id = %s"
        cursor.execute(query, (new_status, numeric_id))
        connection.commit()
        updated = cursor.rowcount > 0
        cursor.close()
        return updated
    except Error as e:
        logger.error(f"Error updating order status: {e}")
        return False
    finally:
        connection.close()


def delete_order(order_id: str) -> bool:
    """Delete an order from database."""
    connection = get_db_connection()
    if not connection:
        return False
    
    try:
        # Extract numeric ID from "ord123" format
        numeric_id = int(order_id.replace("ord", ""))
        
        cursor = connection.cursor()
        # Delete order items first
        cursor.execute("DELETE FROM order_product WHERE order_id = %s", (numeric_id,))
        # Delete order
        cursor.execute("DELETE FROM orders WHERE order_id = %s", (numeric_id,))
        connection.commit()
        deleted = cursor.rowcount > 0
        cursor.close()
        return deleted
    except Error as e:
        logger.error(f"Error deleting order: {e}")
        return False
    finally:
        connection.close()


def save_order(order_data: dict) -> tuple[str, str]:
    """
    Save order to database.
    Returns tuple of (status_message, order_id).
    """
    connection = get_db_connection()
    if not connection:
        raise Exception("Database connection failed")
    
    try:
        cursor = connection.cursor()
        
        # Insert order with image_url
        image_url = order_data.get("image_url")
        order_query = """
            INSERT INTO orders (user_id, shop_id, order_timestamp, image_url, order_status)
            VALUES (%s, %s, %s, %s, 'Pending')
        """
        cursor.execute(order_query, (
            order_data["user_id"],
            order_data["shop_id"],
            datetime.now(),
            image_url
        ))
        
        order_id = cursor.lastrowid
        
        # Insert order items
        items_query = """
            INSERT INTO order_product (order_id, product_id, quantity)
            VALUES (%s, %s, %s)
        """
        for product_id, qty in order_data["items"].items():
            if qty > 0:
                cursor.execute(items_query, (order_id, product_id, qty))
        
        connection.commit()
        cursor.close()
        
        return "success", f"ord{order_id}"
    except Error as e:
        logger.error(f"Error saving order: {e}")
        raise Exception(f"Error saving order: {e}")
    finally:
        connection.close()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send welcome message when /start command is issued."""
    welcome_text = (
        "👋 Welcome to OrderKato Bot!\n\n"
        "This bot helps you place orders for shops.\n\n"
        "📝 Commands:\n"
        "/order - Start a new order\n"
        "/status - Check your order status\n"
        "/update - Update order status\n"
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
        "/update - Update order status\n"
        "/cancel - Cancel current order\n"
        "/help - Show this help message"
    )
    await update.message.reply_text(help_text)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show order status for the user."""
    user = update.effective_user
    tel_username = user.username or ""
    
    # Get user from database
    db_user = get_user_by_telegram(tel_username)
    
    if not db_user:
        await update.message.reply_text(
            f"❌ User @{tel_username} not registered.\n\n"
            "Please contact admin to register."
        )
        return
    
    # Get orders for this user
    orders = get_user_orders(db_user['user_id'])
    
    if not orders:
        await update.message.reply_text(
            f"📋 No orders found for {db_user['name']}.\n\n"
            "Type /order to place a new order."
        )
        return
    
    # Build status message
    message_text = f"📋 ORDER STATUS FOR {db_user['name'].upper()}\n"
    message_text += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    for order in orders[:10]:  # Show last 10 orders
        status = order["status"].upper()
        if status == "PENDING":
            status_icon = "🟡"
        elif status == "DELIVERED":
            status_icon = "✅"
        elif status in ["UNDER-DELIVERED", "OVER-DELIVERED"]:
            status_icon = "⚠️"
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


async def update_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show user's orders with options to update status."""
    user = update.effective_user
    tel_username = user.username or ""
    
    # Get user from database
    db_user = get_user_by_telegram(tel_username)
    
    if not db_user:
        await update.message.reply_text(
            f"❌ User @{tel_username} not registered.\n\n"
            "Please contact admin to register."
        )
        return
    
    # Get orders for this user (only pending ones can be updated)
    all_orders = get_user_orders(db_user['user_id'])
    orders = [o for o in all_orders if o["status"].upper() == "PENDING"]
    
    if not orders:
        await update.message.reply_text(
            f"📋 No pending orders found for {db_user['name']}.\n\n"
            "Only pending orders can be updated.\n"
            "Type /status to see all your orders."
        )
        return
    
    # Build message with buttons for each order
    message_text = f"📝 UPDATE ORDER STATUS\n"
    message_text += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    message_text += "Select an order to update:\n\n"
    
    keyboard = []
    for order in orders[:10]:  # Limit to 10 orders
        # Build items summary
        items_summary = ", ".join([f"{item['product_name']} x{item['quantity']}" for item in order["items"][:2]])
        if len(order["items"]) > 2:
            items_summary += "..."
        
        message_text += f"🟡 {order['order_id']} - {order['shop_name']}\n"
        message_text += f"   {items_summary}\n\n"
        
        # Add buttons for this order
        keyboard.append([
            InlineKeyboardButton(f"{order['order_id']}", callback_data=f"upd_info:{order['order_id']}"),
            InlineKeyboardButton("✅ Delivered", callback_data=f"upd_delivered:{order['order_id']}"),
            InlineKeyboardButton("❌ Cancel", callback_data=f"upd_cancel:{order['order_id']}")
        ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        message_text,
        reply_markup=reply_markup
    )


async def handle_order_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle order status update callbacks."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data.startswith("upd_info:"):
        order_id = data.replace("upd_info:", "")
        await query.answer(f"Order: {order_id}", show_alert=False)
        return
    
    if data.startswith("upd_delivered:"):
        order_id = data.replace("upd_delivered:", "")
        success = update_order_status(order_id, "Delivered")
        
        if success:
            await query.edit_message_text(
                f"✅ Order {order_id} marked as DELIVERED!\n\n"
                "Type /status to see your orders.\n"
                "Type /update to update more orders."
            )
        else:
            await query.edit_message_text(
                f"❌ Failed to update order {order_id}.\n"
                "Please try again or contact support."
            )
    
    elif data.startswith("upd_cancel:"):
        order_id = data.replace("upd_cancel:", "")
        success = delete_order(order_id)
        
        if success:
            await query.edit_message_text(
                f"🗑️ Order {order_id} has been CANCELLED and deleted!\n\n"
                "Type /status to see your orders.\n"
                "Type /order to place a new order."
            )
        else:
            await query.edit_message_text(
                f"❌ Failed to cancel order {order_id}.\n"
                "Please try again or contact support."
            )


async def order_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the order process - show area selection."""
    user = update.effective_user
    tel_username = user.username or ""
    
    # Check if user is registered
    db_user = get_user_by_telegram(tel_username)
    if not db_user:
        await update.message.reply_text(
            f"❌ User @{tel_username} not registered.\n\n"
            "Please contact admin to register."
        )
        return ConversationHandler.END
    
    # Clear any previous order data and store user info
    context.user_data.clear()
    context.user_data["db_user"] = db_user
    
    areas = get_unique_areas()
    
    if not areas:
        await update.message.reply_text(
            "❌ No areas found. Please contact admin."
        )
        return ConversationHandler.END
    
    # Create inline keyboard with areas
    keyboard = []
    for area in areas:
        keyboard.append([InlineKeyboardButton(
            area['area_name'], 
            callback_data=f"area:{area['area_id']}:{area['area_name']}"
        )])
    
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
    
    # Extract area info from callback data
    parts = query.data.replace("area:", "").split(":", 1)
    area_id = int(parts[0])
    area_name = parts[1]
    
    context.user_data["area_id"] = area_id
    context.user_data["area_name"] = area_name
    
    # Get shops in this area
    shops = get_shops_by_area(area_id)
    
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
            display_text += f" ({shop['shop_address'][:30]}...)" if len(shop['shop_address']) > 30 else f" ({shop['shop_address']})"
        keyboard.append([
            InlineKeyboardButton(display_text, callback_data=f"shop:{shop['shop_id']}:{shop['shop_name']}")
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
        keyboard.append([InlineKeyboardButton(
            area['area_name'], 
            callback_data=f"area:{area['area_id']}:{area['area_name']}"
        )])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "📍 **Select an Area:**",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    
    return SELECT_AREA


async def shop_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle shop selection - request photo verification."""
    query = update.callback_query
    await query.answer()
    
    # Extract shop info from callback data
    parts = query.data.replace("shop:", "").split(":", 1)
    shop_id = int(parts[0])
    shop_name = parts[1]
    
    context.user_data["shop_id"] = shop_id
    context.user_data["shop_name"] = shop_name
    context.user_data["items"] = {}  # product_id -> quantity
    context.user_data["current_product"] = None
    context.user_data["verified_photo_path"] = None
    
    # Request photo verification
    area_name = context.user_data.get("area_name", "")
    
    keyboard = [[InlineKeyboardButton("◀️ Back to Shops", callback_data="back:shops")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"📍 Area: **{area_name}**\n"
        f"🏪 Shop: **{shop_name}**\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📸 **PHOTO VERIFICATION REQUIRED**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Please send a photo of the shop **as a document/file**.\n\n"
        "⚠️ **Requirements:**\n"
        "• Send photo as **File/Document** (not as compressed photo)\n"
        "• Photo must be taken **within the last 1 minute**\n"
        "• Photo must contain EXIF metadata\n\n"
        "📎 To send as file: Attach → File → Select photo",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    
    return VERIFY_PHOTO


async def handle_photo_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle photo document for verification."""
    document = update.message.document
    
    # Check if it's an image file
    mime_type = document.mime_type or ""
    if not mime_type.startswith("image/"):
        await update.message.reply_text(
            "❌ **Invalid format!**\n\n"
            "Please send an **image file** (JPEG, PNG, etc.) as a document.\n\n"
            "📎 Tap Attach → File → Select your photo",
            parse_mode="Markdown"
        )
        return VERIFY_PHOTO
    
    # Download the file
    file = await document.get_file()
    
    # Create temp file path
    temp_dir = BASE_DIR / "temp"
    temp_dir.mkdir(exist_ok=True)
    
    extension = Path(document.file_name).suffix if document.file_name else ".jpg"
    temp_path = temp_dir / f"temp_{update.effective_user.id}_{datetime.now().strftime('%Y%m%d%H%M%S')}{extension}"
    
    await file.download_to_drive(temp_path)
    
    # Extract photo datetime from EXIF
    photo_datetime = get_photo_datetime(str(temp_path))
    
    if not photo_datetime:
        # Clean up temp file
        temp_path.unlink(missing_ok=True)
        
        await update.message.reply_text(
            "❌ **No EXIF data found!**\n\n"
            "This photo doesn't contain timestamp information.\n\n"
            "Please take a **new photo** with your camera app and send it as a document.\n\n"
            "💡 Make sure your camera saves EXIF data (location/time info).",
            parse_mode="Markdown"
        )
        return VERIFY_PHOTO
    
    # Check if photo was taken within the allowed time
    current_time = datetime.now()
    time_diff = (current_time - photo_datetime).total_seconds()
    
    if time_diff > PHOTO_MAX_AGE_SECONDS:
        # Clean up temp file
        temp_path.unlink(missing_ok=True)
        
        # Calculate how old the photo is
        minutes_old = int(time_diff / 60)
        seconds_old = int(time_diff % 60)
        
        await update.message.reply_text(
            "❌ **Photo is too old!**\n\n"
            f"📅 Photo taken: {photo_datetime.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"⏱️ Age: {minutes_old}m {seconds_old}s ago\n"
            f"⏳ Maximum allowed: {PHOTO_MAX_AGE_SECONDS} seconds\n\n"
            "Please take a **fresh photo** right now and send it as a document.",
            parse_mode="Markdown"
        )
        return VERIFY_PHOTO
    
    # Photo verified! Save it
    shop_id = context.user_data.get("shop_id")
    db_user = context.user_data.get("db_user")
    
    image_url = save_shop_photo(str(temp_path), shop_id, db_user['user_id'])
    context.user_data["verified_photo_path"] = image_url
    
    # Clean up temp file
    temp_path.unlink(missing_ok=True)
    
    await update.message.reply_text(
        "✅ **Photo Verified Successfully!**\n\n"
        f"📅 Photo taken: {photo_datetime.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"⏱️ Time difference: {int(time_diff)} seconds\n\n"
        "Proceeding to product selection...",
        parse_mode="Markdown"
    )
    
    # Show product selection as a new message
    return await show_product_selection_new_message(update, context)


async def handle_compressed_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle when user sends a compressed photo instead of document."""
    await update.message.reply_text(
        "❌ **Invalid format!**\n\n"
        "You sent a **compressed photo**. Please send it as a **document/file** instead.\n\n"
        "📎 How to send as file:\n"
        "1. Tap the 📎 attach icon\n"
        "2. Select **File** (not Photo)\n"
        "3. Choose your photo from gallery\n\n"
        "This preserves the EXIF data needed for verification.",
        parse_mode="Markdown"
    )
    return VERIFY_PHOTO


async def show_product_selection(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Display product selection interface."""
    products = read_products()
    
    if not products:
        await query.edit_message_text(
            "❌ No products found. Please contact admin."
        )
        return ConversationHandler.END
    
    area_name = context.user_data.get("area_name", "")
    shop_name = context.user_data.get("shop_name", "")
    items = context.user_data.get("items", {})
    
    # Build order summary if there are items
    order_summary = ""
    if items:
        order_summary = "\n\n📦 **Current Order:**\n"
        for product in products:
            pid = product['product_id']
            if pid in items and items[pid] > 0:
                order_summary += f"• {product['product_name']}: {items[pid]}\n"
    
    # Create inline keyboard with products
    keyboard = []
    for product in products:
        pid = product['product_id']
        qty = items.get(pid, 0)
        price = float(product['price'])
        
        if qty > 0:
            display_text = f"✅ {product['product_name']} (৳{price:.0f}) [{qty}]"
        else:
            display_text = f"➕ {product['product_name']} (৳{price:.0f})"
        
        keyboard.append([
            InlineKeyboardButton(display_text, callback_data=f"product:{pid}:{product['product_name']}")
        ])
    
    # Add action buttons
    action_row = []
    if items and any(q > 0 for q in items.values()):
        action_row.append(InlineKeyboardButton("✔️ Confirm Order", callback_data="action:confirm"))
        action_row.append(InlineKeyboardButton("🗑️ Clear All", callback_data="action:clear"))
    
    if action_row:
        keyboard.append(action_row)
    
    keyboard.append([InlineKeyboardButton("◀️ Back to Shops", callback_data="back:shops")])
    
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
    
    # Extract product info from callback data
    parts = query.data.replace("product:", "").split(":", 1)
    product_id = int(parts[0])
    product_name = parts[1]
    
    context.user_data["current_product"] = product_id
    context.user_data["current_product_name"] = product_name
    
    current_qty = context.user_data.get("items", {}).get(product_id, 0)
    
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
    
    message_text = f"📦 **{product_name}**\n\n"
    
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
    product_id = context.user_data.get("current_product")
    
    if not product_id:
        return await show_product_selection(query, context)
    
    if "items" not in context.user_data:
        context.user_data["items"] = {}
    
    if qty > 0:
        context.user_data["items"][product_id] = qty
    elif product_id in context.user_data["items"]:
        del context.user_data["items"][product_id]
    
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
    
    product_id = context.user_data.get("current_product")
    product_name = context.user_data.get("current_product_name", "Product")
    
    if not product_id:
        await update.message.reply_text("❌ No product selected. Please start over with /order")
        return ConversationHandler.END
    
    if "items" not in context.user_data:
        context.user_data["items"] = {}
    
    if qty > 0:
        context.user_data["items"][product_id] = qty
    elif product_id in context.user_data["items"]:
        del context.user_data["items"][product_id]
    
    if qty > 0:
        await update.message.reply_text(f"✅ Added: {product_name} × {qty}")
    else:
        await update.message.reply_text(f"🗑️ Removed: {product_name}")
    
    # Show product selection again as new message
    return await show_product_selection_new_message(update, context)


async def show_product_selection_new_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Display product selection interface as a new message."""
    products = read_products()
    
    if not products:
        await update.message.reply_text(
            "❌ No products found. Please contact admin."
        )
        return ConversationHandler.END
    
    area_name = context.user_data.get("area_name", "")
    shop_name = context.user_data.get("shop_name", "")
    items = context.user_data.get("items", {})
    
    # Build order summary if there are items
    order_summary = ""
    if items:
        order_summary = "\n\n📦 **Current Order:**\n"
        for product in products:
            pid = product['product_id']
            if pid in items and items[pid] > 0:
                order_summary += f"• {product['product_name']}: {items[pid]}\n"
    
    # Create inline keyboard with products
    keyboard = []
    for product in products:
        pid = product['product_id']
        qty = items.get(pid, 0)
        price = float(product['price'])
        
        if qty > 0:
            display_text = f"✅ {product['product_name']} (৳{price:.0f}) [{qty}]"
        else:
            display_text = f"➕ {product['product_name']} (৳{price:.0f})"
        
        keyboard.append([
            InlineKeyboardButton(display_text, callback_data=f"product:{pid}:{product['product_name']}")
        ])
    
    # Add action buttons
    action_row = []
    if items and any(q > 0 for q in items.values()):
        action_row.append(InlineKeyboardButton("✔️ Confirm Order", callback_data="action:confirm"))
        action_row.append(InlineKeyboardButton("🗑️ Clear All", callback_data="action:clear"))
    
    if action_row:
        keyboard.append(action_row)
    
    keyboard.append([InlineKeyboardButton("◀️ Back to Shops", callback_data="back:shops")])
    
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
    
    area_id = context.user_data.get("area_id")
    area_name = context.user_data.get("area_name", "")
    shops = get_shops_by_area(area_id)
    
    keyboard = []
    for shop in shops:
        display_text = shop["shop_name"]
        if shop["shop_address"]:
            display_text += f" ({shop['shop_address'][:30]}...)" if len(shop['shop_address']) > 30 else f" ({shop['shop_address']})"
        keyboard.append([
            InlineKeyboardButton(display_text, callback_data=f"shop:{shop['shop_id']}:{shop['shop_name']}")
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
    total_price = 0
    
    for product in products:
        pid = product['product_id']
        if pid in items and items[pid] > 0:
            qty = items[pid]
            price = float(product['price'])
            discount = float(product['discount'])
            final_price = price * (1 - discount/100)
            line_total = final_price * qty
            
            order_summary += f"  • {product['product_name']} x {qty} = ৳{line_total:.0f}\n"
            total_items += qty
            total_price += line_total
    
    message_text = (
        "📋 ORDER SUMMARY\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"📍 Area: {area_name}\n"
        f"🏪 Shop: {shop_name}\n\n"
        f"📦 Items:\n{order_summary}\n"
        f"📊 Total items: {total_items}\n"
        f"💰 Total: ৳{total_price:.0f}\n\n"
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
    """Submit the order and save to database."""
    query = update.callback_query
    await query.answer("Submitting order...")
    
    db_user = context.user_data.get("db_user")
    
    # Prepare order data with verified photo
    order_data = {
        "user_id": db_user['user_id'],
        "shop_id": context.user_data.get("shop_id"),
        "items": context.user_data.get("items", {}),
        "image_url": context.user_data.get("verified_photo_path"),  # Include verified photo
    }
    
    # Save order
    try:
        _, order_id = save_order(order_data)
        
        # Build order summary
        products = read_products()
        items = order_data["items"]
        order_summary = ""
        total_qty = 0
        
        for product in products:
            pid = product['product_id']
            if pid in items and items[pid] > 0:
                qty = items[pid]
                order_summary += f"  • {product['product_name']} x {qty}\n"
                total_qty += qty
        
        # Include photo verification status in message
        photo_status = "✅ Verified" if order_data["image_url"] else "❌ Not provided"
        
        message_text = (
            "✅ ORDER SUBMITTED SUCCESSFULLY!\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🆔 Order ID: {order_id}\n\n"
            f"👤 User: {db_user['name']}\n\n"
            f"📍 Area: {context.user_data.get('area_name', '')}\n"
            f"🏪 Shop: {context.user_data.get('shop_name', '')}\n"
            f"📸 Photo: {photo_status}\n\n"
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
    
    # Test database connection
    connection = get_db_connection()
    if not connection:
        print("\n❌ Error: Cannot connect to database")
        print("Please check your MySQL connection settings.")
        return
    connection.close()
    
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
            VERIFY_PHOTO: [
                MessageHandler(filters.Document.IMAGE, handle_photo_document),
                MessageHandler(filters.PHOTO, handle_compressed_photo),
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
    application.add_handler(CommandHandler("update", update_command))
    application.add_handler(CallbackQueryHandler(handle_order_update, pattern=r"^upd_"))
    application.add_handler(conv_handler)
    
    # Start the bot
    print("\n🤖 OrderKato Bot is starting...")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"📁 Token file: {TOKEN_FILE}")
    print(f"🗄️  Database: {DB_CONFIG['database']}@{DB_CONFIG['host']}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("Press Ctrl+C to stop the bot.\n")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
