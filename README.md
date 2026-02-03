# OrderKato Telegram Bot

A Telegram bot for field order management with MySQL database backend and photo verification.

## 📁 Directory Structure

```
OrderKatoBot/
├── orderkato_bot.py        # Main bot script
├── .gitignore              # Git ignore file
├── config/
│   └── token.txt           # Telegram bot token (edit this!)
├── ShopImage/              # Verified shop photos (auto-created)
├── temp/                   # Temporary files (auto-created)
└── README.md
```

## 🗄️ Database

This bot uses **MySQL** database (`Orderkatodb`) with the following tables:

| Table | Description |
|-------|-------------|
| `area` | Areas/regions for shop grouping |
| `shops` | Shop information linked to areas |
| `product` | Product catalog |
| `brand` | Product brands |
| `users` | Registered bot users (with telegram username) |
| `orders` | Order records with image_url |
| `order_product` | Order items (product quantities) |

## 🚀 Setup

### 1. Install Python Dependencies

```bash
pip install python-telegram-bot mysql-connector-python Pillow
```

### 2. Configure MySQL Database

Ensure your MySQL database `Orderkatodb` is running with the required tables. Update the connection settings in `orderkato_bot.py` if needed:

```python
DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "database": "Orderkatodb",
    "user": "your_username",
    "password": "your_password",
}
```

### 3. Get Your Telegram Bot Token

1. Open Telegram and search for `@BotFather`
2. Send `/newbot` command
3. Follow the instructions to create your bot
4. Copy the API token provided

### 4. Configure the Token

Edit `config/token.txt` and replace the placeholder with your actual bot token:

```
YOUR_ACTUAL_BOT_TOKEN_HERE
```

### 5. Run the Bot

```bash
python orderkato_bot.py
```

## 📋 How to Use

### Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message |
| `/order` | Start a new order |
| `/status` | Check your order status |
| `/update` | Update order status (mark delivered/cancel) |
| `/cancel` | Cancel current order |
| `/help` | Show help message |

### Order Flow

1. Type `/order` to start
2. Select an **area** from the list
3. Select a **shop** from that area
4. 📸 **Photo Verification** - Send a recent photo of the shop as a document
5. Tap products to add them to your order
6. Enter quantities (tap quick buttons or type a number)
7. Review and confirm your order

### 📸 Photo Verification

After selecting a shop, you must send a verification photo:

- **Format**: Send as **document/file** (not compressed photo)
- **Freshness**: Photo must be taken **within the last 1 minute**
- **EXIF Required**: Photo must contain timestamp metadata

**How to send as file:**
1. Tap the 📎 attach icon
2. Select **File** (not Photo)
3. Choose your photo from gallery

This ensures the user is physically at the shop location when placing the order.

### Check Order Status

Type `/status` to see all your orders with their current status:
- 🟡 PENDING - Order placed, awaiting delivery
- ✅ DELIVERED - Order has been delivered
- ⚠️ UNDER-DELIVERED / OVER-DELIVERED - Partial delivery issues

### Update Order Status

Type `/update` to see pending orders and quickly:
- Mark as **Delivered** ✅
- **Cancel** the order ❌

## 🗃️ Database Schema

### Users Table
Users must be registered in the database with their Telegram username to use the bot.

```sql
CREATE TABLE users (
    user_id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(100),
    tel_username VARCHAR(100) UNIQUE,
    -- other fields...
);
```

### Orders Table
```sql
CREATE TABLE orders (
    order_id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT,
    shop_id INT,
    order_timestamp DATETIME,
    image_url VARCHAR(500),  -- Verified photo path
    order_status ENUM('Pending', 'Delivered', 'Under-delivered', 'Over-delivered'),
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (shop_id) REFERENCES shops(shop_id)
);
```

## 📷 Shop Images

Verified photos are stored in the `ShopImage/` folder with the naming format:
```
shop_{shop_id}_user_{user_id}_{timestamp}_{uuid}.jpg
```

The image path is saved in the `image_url` column of the orders table.

## 🔧 Configuration

### Photo Verification Timeout

Edit `PHOTO_MAX_AGE_SECONDS` in `orderkato_bot.py` to change the maximum allowed photo age:

```python
PHOTO_MAX_AGE_SECONDS = 60  # 1 minute (default)
```

## 🔧 Troubleshooting

### "Token file not found"
Make sure `config/token.txt` exists and contains your bot token.

### "Cannot connect to database"
- Check MySQL is running
- Verify database credentials in `DB_CONFIG`
- Ensure `Orderkatodb` database exists

### "User not registered"
The Telegram username must be added to the `users` table in the database.

### "No EXIF data found"
- Take a new photo with your camera app (not screenshot)
- Make sure camera settings save EXIF metadata
- Send as document, not compressed photo

### "Photo is too old"
Take a fresh photo right now and send it immediately.

### Bot not responding
- Check your internet connection
- Verify the bot token is correct
- Check the terminal for error messages

## 📄 License

This project is provided as-is for operational use.

---

![OrderKato Bot](screenshot.png)