from flask import Flask, render_template, request, jsonify, session
import requests
import time
import json
import os
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = "your_secret_key_here_12345"

# ====== YOUR CONFIG - PRIVATE CHANNEL ======
BOT_TOKEN = "8695639336:AAETQoASFRYYsTUAmIGhuZtyj29jJsjIvRA"
CHANNEL_LINK = "https://t.me/+MiEwFuylozg0OTJl"  # Sirf link, username nahi
CHANNEL_ID = "-1004399953802"  # Private channel ka ID (bot admin hona chahiye)
FAM_API_KEY = "fam_c2cfc0ecde4d7b33825d8e11a9153765746da845"

FAM_API_URL = "https://famgateway.in/api/qr.php"
FAM_STATUS_URL = "https://famgateway.in/api/status.php"
FAM_QR_URL = "https://famgateway.in/api/qr-image.php"

# ====== PREMIUM PACKS ======
PREMIUM_PACKS = {
    "silver": {
        "name": "Silver",
        "price": 80,
        "days": 10,
        "type": "temporary",
        "emoji": "🥈"
    },
    "gold": {
        "name": "Gold",
        "price": 100,
        "days": 15,
        "type": "temporary",
        "emoji": "🥇"
    },
    "platinum": {
        "name": "Platinum",
        "price": 200,
        "days": 30,
        "type": "temporary",
        "emoji": "💎"
    },
    "diamond": {
        "name": "Diamond",
        "price": 500,
        "days": 9999,
        "type": "permanent",
        "emoji": "👑"
    }
}

# ====== STORAGE ======
pending_orders = {}
premium_users = {}

# ====== HELPERS ======
def create_order(amount):
    try:
        url = f"{FAM_API_URL}?api_key={FAM_API_KEY}&amount={amount}"
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if data.get("status") == "success":
            order_data = data["data"]
            return {
                "success": True,
                "order_id": order_data["order_id"],
                "checkout_url": order_data["checkout_url"],
                "qr_url": order_data["qr_url"],
                "upi_intent": order_data["upi_intent"],
                "expires_at": datetime.strptime(order_data["expires_at_ist"], "%d-%m-%Y %H:%M:%S"),
                "amount": order_data["amount"]
            }
        else:
            return {"success": False, "error": "API Error"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def check_order_status(order_id):
    try:
        url = f"{FAM_STATUS_URL}?api_key={FAM_API_KEY}&order_id={order_id}"
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if data.get("status") == "success":
            payment_status = data.get("data", {}).get("payment_status", "pending")
            return {"success": True, "paid": payment_status == "paid"}
        else:
            return {"success": False, "paid": False}
    except:
        return {"success": False, "paid": False}

def accept_channel_join(chat_id):
    """Approve join request for private channel"""
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/approveChatJoinRequest"
        params = {
            "chat_id": CHANNEL_ID,  # Channel ID use kar rahe hain
            "user_id": chat_id
        }
        response = requests.post(url, data=params, timeout=10)
        return response.json().get("ok", False)
    except Exception as e:
        print(f"Approve error: {e}")
        return False

def check_channel_join(chat_id):
    """Check if user is already in channel"""
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getChatMember"
        params = {
            "chat_id": CHANNEL_ID,
            "user_id": chat_id
        }
        response = requests.post(url, data=params, timeout=10)
        data = response.json()
        if data.get("ok"):
            status = data.get("result", {}).get("status", "")
            return status in ["member", "administrator", "creator"]
        return False
    except Exception as e:
        print(f"Check error: {e}")
        return False

def get_pack_details(pack_key):
    return PREMIUM_PACKS.get(pack_key)

def get_user_premium(chat_id):
    user = premium_users.get(chat_id)
    if not user:
        return None
    
    if user["expires_at"]:
        if time.time() > user["expires_at"]:
            kick_user_from_channel(chat_id)
            return None
    
    return user

def kick_user_from_channel(chat_id):
    """Kick user from private channel after expiry"""
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/banChatMember"
        params = {
            "chat_id": CHANNEL_ID,
            "user_id": chat_id
        }
        response = requests.post(url, data=params, timeout=10)
        if response.json().get("ok"):
            # Unban after 30 seconds so they can rejoin
            time.sleep(30)
            unban_url = f"https://api.telegram.org/bot{BOT_TOKEN}/unbanChatMember"
            unban_params = {
                "chat_id": CHANNEL_ID,
                "user_id": chat_id
            }
            requests.post(unban_url, data=unban_params, timeout=10)
            return True
        return False
    except Exception as e:
        print(f"Kick error: {e}")
        return False

# ====== ROUTES ======
@app.route('/')
def index():
    return render_template('index.html', packs=PREMIUM_PACKS, channel_link=CHANNEL_LINK)

@app.route('/create_order', methods=['POST'])
def create_order_route():
    try:
        pack_key = request.form.get('pack')
        amount = float(request.form.get('amount', 0))
        
        if amount <= 0:
            return jsonify({"success": False, "error": "Invalid amount"})
        
        pack = PREMIUM_PACKS.get(pack_key)
        if not pack:
            return jsonify({"success": False, "error": "Invalid pack selected"})
        
        order = create_order(amount)
        if order["success"]:
            order_id = order["order_id"]
            pending_orders[order_id] = {
                "pack": pack_key,
                "amount": amount,
                "expires_at": order["expires_at"].timestamp(),
                "chat_id": None,
                "paid": False
            }
            return jsonify({
                "success": True,
                "order_id": order_id,
                "checkout_url": order["checkout_url"],
                "qr_url": order["qr_url"],
                "expires_at": order["expires_at"].strftime("%d-%m-%Y %H:%M:%S"),
                "pack": pack_key
            })
        else:
            return jsonify({"success": False, "error": order.get("error", "Unknown error")})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/check_order/<order_id>')
def check_order_route(order_id):
    status = check_order_status(order_id)
    if status.get("paid"):
        if order_id in pending_orders:
            pending_orders[order_id]["paid"] = True
        return jsonify({"success": True, "paid": True})
    else:
        if order_id in pending_orders:
            expires_at = pending_orders[order_id]["expires_at"]
            if time.time() > expires_at:
                return jsonify({"success": True, "paid": False, "expired": True})
        return jsonify({"success": True, "paid": False, "expired": False})

@app.route('/submit_chat_id', methods=['POST'])
def submit_chat_id():
    try:
        order_id = request.form.get('order_id')
        chat_id = request.form.get('chat_id')
        
        if not order_id or not chat_id:
            return jsonify({"success": False, "error": "Missing order_id or chat_id"})
        
        order = pending_orders.get(order_id)
        if not order:
            return jsonify({"success": False, "error": "Order not found"})
        
        status = check_order_status(order_id)
        if not status.get("paid"):
            return jsonify({"success": False, "error": "Payment not completed yet"})
        
        # Check if user joined the channel
        if not check_channel_join(chat_id):
            return jsonify({
                "success": False, 
                "error": f"❌ You haven't joined the channel yet!\n\n👉 Join first: {CHANNEL_LINK}\n\nThen click Activate again."
            })
        
        pack_key = order.get("pack")
        pack = PREMIUM_PACKS.get(pack_key)
        
        if not pack:
            return jsonify({"success": False, "error": "Invalid pack"})
        
        current_time = time.time()
        if pack["type"] == "permanent":
            expires_at = None
            days_text = "Permanent"
        else:
            expires_at = current_time + (pack["days"] * 24 * 60 * 60)
            days_text = f"{pack['days']} Days"
        
        premium_users[chat_id] = {
            "pack": pack_key,
            "expires_at": expires_at,
            "joined_at": current_time,
            "order_id": order_id
        }
        
        # Approve join request (private channel)
        if accept_channel_join(chat_id):
            return jsonify({
                "success": True,
                "message": f"✅ Premium {pack['name']} Activated!",
                "pack": pack["name"],
                "emoji": pack["emoji"],
                "duration": days_text,
                "channel": CHANNEL_LINK
            })
        else:
            return jsonify({
                "success": False, 
                "error": "⚠️ Could not approve request. Make sure bot is admin in channel."
            })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/check_premium/<chat_id>')
def check_premium(chat_id):
    user = get_user_premium(chat_id)
    if user:
        pack = PREMIUM_PACKS.get(user["pack"])
        return jsonify({
            "success": True,
            "premium": True,
            "pack": pack["name"],
            "emoji": pack["emoji"],
            "expires_at": datetime.fromtimestamp(user["expires_at"]).strftime("%d-%m-%Y %H:%M:%S") if user["expires_at"] else "Permanent"
        })
    else:
        return jsonify({"success": True, "premium": False})

@app.route('/order_status/<order_id>')
def order_status(order_id):
    order = pending_orders.get(order_id, {})
    return render_template('order_status.html', order_id=order_id, order=order)

@app.route('/bot_webhook', methods=['POST'])
def bot_webhook():
    try:
        data = request.get_json()
        return jsonify({"status": "ok"})
    except:
        return jsonify({"status": "error"})

# ====== AUTO KICK ======
def auto_kick_expired():
    current_time = time.time()
    users_to_kick = []
    
    for chat_id, user in premium_users.items():
        if user["expires_at"]:
            if current_time > user["expires_at"]:
                users_to_kick.append(chat_id)
    
    for chat_id in users_to_kick:
        kick_user_from_channel(chat_id)
        del premium_users[chat_id]
        print(f"✅ Kicked expired user: {chat_id}")

if __name__ == '__main__':
    import threading
    def schedule_auto_kick():
        while True:
            time.sleep(3600)  # Check every hour
            auto_kick_expired()
    
    kick_thread = threading.Thread(target=schedule_auto_kick, daemon=True)
    kick_thread.start()
    
    print("🚀 Bot Started!")
    print(f"📢 Channel: {CHANNEL_LINK}")
    print(f"🤖 Bot Token: {BOT_TOKEN[:20]}...")
    app.run(debug=True, host='0.0.0.0', port=5000)