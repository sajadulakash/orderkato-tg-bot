# OrderKato Telegram Bot

A simple Telegram bot for field order management. Designed for operational use with easy-to-edit CSV data files.

## 📁 Directory Structure

```
OrderKatoBot/
├── orderkato_bot.py        # Main bot script
├── .gitignore              # Git ignore file
├── config/
│   ├── token.txt           # Telegram bot token (edit this!)
│   └── order.txt           # Order counter (auto-managed)
├── data/
│   ├── shops.csv           # Shop and area data
│   ├── products.csv        # Product data
│   └── orders/             # Auto-generated daily order files
│       └── orders_YYYY-MM-DD.csv
└── README.md
```

## 🚀 Setup

### 1. Install Python Dependencies

```bash
pip install python-telegram-bot
```

### 2. Get Your Telegram Bot Token

1. Open Telegram and search for `@BotFather`
2. Send `/newbot` command
3. Follow the instructions to create your bot
4. Copy the API token provided

### 3. Configure the Token

Edit `config/token.txt` and replace the placeholder with your actual bot token:

```
YOUR_ACTUAL_BOT_TOKEN_HERE
```

### 4. Run the Bot

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
| `/cancel` | Cancel current order |
| `/help` | Show help message |

### Order Flow

1. Type `/order` to start
2. Select an **area** from the list
3. Select a **shop** from that area
4. Tap products to add them to your order
5. Enter quantities (tap quick buttons or type a number)
6. Review and confirm your order

### Check Order Status

Type `/status` to see all your orders with their current status:
- 🟡 PENDING - Order placed, awaiting delivery
- ✅ DELIVERED - Order has been delivered
- ❌ CANCELLED - Order was cancelled

## 📝 Data Files

### shops.csv

Contains shop information organized by area. Edit this file to add/remove shops.

```csv
area_name,shop_name,shop_address
Bonani,City Mart,123 Main Street
Bonani,Quick Stop,456 Central Ave
Mirpur,Fresh Market,101 North Blvd
Badda,Value Shop,404 Pine Road
```

**Columns:**
- `area_name` - Area/region name (used for grouping)
- `shop_name` - Shop name
- `shop_address` - Shop address (optional, for display)

### products.csv

Contains the list of available products. **Note:** Only `product_name` column is required.

```csv
product_name
Coca-Cola-500ml
teer-atta
jibon-water-1L
teer-oil-1L
```

**Columns:**
- `product_name` - Product display name

### orders/orders_YYYY-MM-DD.csv

Auto-generated daily order files. A new file is created automatically for each day.

```csv
order_id,order_date,order_time,username,area_name,shop_name,product_name,quantity,status
O1,2026-01-25,10:30:45,john_doe,Bonani,City Mart,Coca-Cola-500ml,10,pending
O2,2026-01-25,11:15:30,jane_doe,Mirpur,Fresh Market,teer-atta,5,delivered
```

**Columns:**
- `order_id` - Unique order ID (O1, O2, O3, etc.)
- `order_date` - Date of order (YYYY-MM-DD)
- `order_time` - Time of order (HH:MM:SS)
- `username` - Telegram username
- `area_name` - Selected area
- `shop_name` - Selected shop
- `product_name` - Product name
- `quantity` - Ordered quantity
- `status` - Order status (pending/delivered/cancelled)

Each product is stored as a separate row. Orders with multiple products share the same `order_id`.

### config/order.txt

Stores the current order counter. This file is auto-managed by the bot - do not edit manually unless you want to reset the order numbering.

## ⚙️ Customization

### Adding New Areas/Shops

Simply edit `data/shops.csv`:

```csv
area_name,shop_name,shop_address
New Area,New Shop,123 New Street
```

No code changes required!

### Adding New Products

Edit `data/products.csv`:

```csv
product_name
New Product Name
```

Changes are applied immediately - no restart needed.

### Updating Order Status

To mark an order as delivered, edit the `data/orders/orders_YYYY-MM-DD.csv` file and change the `status` column from `pending` to `delivered`.

## 🔧 Troubleshooting

### "Token file not found"
Make sure `config/token.txt` exists and contains your bot token.

### "No areas/products found"
Check that `data/shops.csv` and `data/products.csv` exist and have valid data.

### Bot not responding
- Check your internet connection
- Verify the bot token is correct
- Check the terminal for error messages

## 📄 License

This project is provided as-is for operational use.

