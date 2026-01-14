import keep_alive
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import requests
import time
import threading
import json
import os
import re
from datetime import datetime, timedelta
from urllib.parse import quote
import logging
keep_alive.keep_alive()
# ================= CONFIG =================
BOT_TOKEN = "8555066395:AAH9Fw1Fm3pOcfpzScgLqXb0SQ7IkWs3VWU"
bot = telebot.TeleBot(BOT_TOKEN)

# Files lưu trữ
ACCOUNTS_FILE = "monitored_accounts.json"
DONE_FILE = "done_keo.json"
CANCELED_FILE = "canceled_keo.json"

# API
API_INFO_URL = "https://adidaphat.site/facebook/getinfo"
UID_API_URL = "https://keyherlyswar.x10.mx/Apidocs/getuidfb.php?link="
API_KEY = "apikeysumi"

# ================= LOGGING =================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ================= HELPER FUNCTIONS =================
def format_number(num):
    """Định dạng số với dấu chấm"""
    return f"{int(num):,}".replace(",", ".")

def parse_amount(amount_str):
    """Chuyển đổi số tiền từ dạng '20K', '1.5M' sang số"""
    amount_str = str(amount_str).upper().replace(",", ".").strip()
    
    if 'K' in amount_str:
        num = amount_str.replace('K', '').strip()
        try:
            return float(num) * 1000
        except:
            return 0
    elif 'M' in amount_str:
        num = amount_str.replace('M', '').strip()
        try:
            return float(num) * 1000000
        except:
            return 0
    else:
        try:
            return float(amount_str)
        except:
            return 0

def parse_time_duration(time_str):
    """Chuyển đổi thời gian từ dạng '30d', '2h', '90m' sang giây"""
    time_str = str(time_str).lower().strip()
    
    if 'd' in time_str:
        days = float(time_str.replace('d', '').strip())
        return int(days * 24 * 60 * 60)
    elif 'h' in time_str:
        hours = float(time_str.replace('h', '').strip())
        return int(hours * 60 * 60)
    elif 'm' in time_str:
        minutes = float(time_str.replace('m', '').strip())
        return int(minutes * 60)
    elif 's' in time_str:
        seconds = float(time_str.replace('s', '').strip())
        return int(seconds)
    else:
        try:
            return int(time_str)
        except:
            return 3600  # Mặc định 1 giờ

def extract_uid_from_input(input_str):
    """Trích xuất UID từ input"""
    input_str = input_str.strip()
    
    if input_str.isdigit():
        return input_str
    
    try:
        url_encoded = quote(input_str)
        res = requests.get(UID_API_URL + url_encoded, timeout=10).json()
        if res.get("status") == "success" and "uid" in res:
            return res["uid"]
        else:
            return None
    except:
        return None

def get_fb_info(uid):
    """Lấy thông tin Facebook từ UID (bao gồm avatar)"""
    try:
        url = f"{API_INFO_URL}?uid={uid}&apikey={API_KEY}"
        r = requests.get(url, timeout=15)
        res = r.json()
        
        if 'error' in res:
            return {"error": res['error']}
        
        if 'success' in res and not res['success']:
            return {"error": res.get('message', 'Lỗi không xác định')}
            
        return {"success": True, "data": res}
    except Exception as e:
        return {"error": f"Lỗi kết nối: {str(e)}"}

def get_avatar_from_api(uid):
    """Lấy avatar từ API thông tin Facebook"""
    try:
        info = get_fb_info(uid)
        if 'error' in info:
            return None
        
        fb_data = info['data']
        avatar = fb_data.get('avatar')
        
        if avatar and isinstance(avatar, str) and avatar.startswith(('http://', 'https://')):
            return avatar
        
        # Fallback: thử dùng graph.facebook.com
        fallback_url = f"https://graph.facebook.com/{uid}/picture?type=large&width=400&height=400"
        return fallback_url
        
    except:
        # Fallback cuối cùng
        return f"https://graph.facebook.com/{uid}/picture?type=large"

def check_account_live(uid):
    """Kiểm tra tài khoản còn live không"""
    try:
        url = f"{API_INFO_URL}?uid={uid}&apikey={API_KEY}"
        r = requests.get(url, timeout=10)
        res = r.json()
        
        if 'error' in res or ('success' in res and not res['success']):
            return False
        return True
    except:
        return False

# ================= DATA MANAGEMENT =================
def load_data(filename, default=[]):
    """Tải dữ liệu từ file JSON"""
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return default
    return default

def save_data(filename, data):
    """Lưu dữ liệu vào file JSON"""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except:
        return False

# ================= MONITORING SYSTEM =================
monitored_accounts = load_data(ACCOUNTS_FILE, [])
done_keo = load_data(DONE_FILE, [])
canceled_keo = load_data(CANCELED_FILE, [])

# Lưu trữ nội dung tin nhắn cuối cùng để so sánh
last_message_content = {}

def monitor_accounts():
    """Hàm kiểm tra định kỳ các tài khoản đang theo dõi"""
    global monitored_accounts, done_keo, canceled_keo, last_message_content
    
    while True:
        try:
            current_time = datetime.now()
            
            for account in monitored_accounts[:]:
                uid = account.get('uid')
                chat_id = account.get('chat_id')
                message_id = account.get('message_id')
                end_time = datetime.fromisoformat(account.get('end_time'))
                user_name = account.get('user_name', 'Không rõ')
                
                # Kiểm tra nếu đã hết thời gian theo dõi
                if current_time >= end_time:
                    # Chuyển vào list done
                    account['status'] = 'done'
                    account['done_time'] = current_time.isoformat()
                    done_keo.append(account)
                    monitored_accounts.remove(account)
                    
                    # Cập nhật tin nhắn
                    try:
                        update_account_message(chat_id, message_id, account, is_done=True)
                    except Exception as e:
                        logger.error(f"Lỗi cập nhật khi hết thời gian: {e}")
                    
                    save_data(ACCOUNTS_FILE, monitored_accounts)
                    save_data(DONE_FILE, done_keo)
                    continue
                
                # Kiểm tra tình trạng live/die (check mỗi 60s)
                try:
                    is_live = check_account_live(uid)
                except:
                    is_live = False
                
                if not is_live and account.get('status') != 'die':
                    old_status = account.get('status')
                    account['status'] = 'die'
                    account['die_time'] = current_time.isoformat()
                    
                    # Chỉ save nếu có thay đổi
                    if old_status != 'die':
                        save_data(ACCOUNTS_FILE, monitored_accounts)
                    
                    # Gửi thông báo acc die
                    try:
                        die_message = (
                            f"❌ <b>THÔNG BÁO TRẠNG THÁI:</b> — "
                            f"👤 <b>Tên:</b> {account.get('name', 'Không rõ')}\n"
                            f"<code>{uid}</code>\n"
                            f"🔗 <b>Link profile:</b> <a href='https://facebook.com/{uid}'>LINK PROFILE</a>\n"
                            f"📌 <b>Trạng thái:</b> ❌ DIE — VÔ HIỆU HOÁ\n"
                            f"⏰ <b>Thời gian die:</b> {current_time.strftime('%d/%m/%Y %H:%M:%S')}\n"
                        )
                        
                        # Gửi thông báo die riêng
                        bot.send_message(
                            chat_id=chat_id,
                            text=die_message,
                            parse_mode='HTML'
                        )
                    except Exception as e:
                        logger.error(f"Lỗi gửi thông báo die: {e}")
                    
                    # Cập nhật tin nhắn kèo
                    try:
                        update_account_message(chat_id, message_id, account)
                    except Exception as e:
                        logger.error(f"Lỗi cập nhật khi die: {e}")
                
                elif is_live and account.get('status') != 'live':
                    old_status = account.get('status')
                    account['status'] = 'live'
                    
                    # Chỉ save nếu có thay đổi
                    if old_status != 'live':
                        save_data(ACCOUNTS_FILE, monitored_accounts)
                    
                    try:
                        update_account_message(chat_id, message_id, account)
                    except Exception as e:
                        logger.error(f"Lỗi cập nhật khi live: {e}")
            
            time.sleep(60)  # Kiểm tra mỗi 60 giây
            
        except Exception as e:
            logger.error(f"Lỗi trong monitor_accounts: {e}")
            time.sleep(30)  # Chờ lâu hơn nếu có lỗi

def update_account_message(chat_id, message_id, account, is_done=False):
    """Cập nhật tin nhắn kèo"""
    try:
        new_message = generate_account_message(account, is_done)
        message_key = f"{chat_id}_{message_id}"
        
        # Kiểm tra xem nội dung có thay đổi không
        if message_key in last_message_content:
            if last_message_content[message_key] == new_message:
                # Nội dung không đổi, không cần update
                return
        
        # Lưu nội dung mới
        last_message_content[message_key] = new_message
        
        # Xác định có nút hay không (khi done/hủy thì không có nút)
        reply_markup = None
        if not is_done and account.get('status') not in ['done', 'canceled']:
            reply_markup = generate_buttons(account['id'])
        
        # Thử cập nhật caption (nếu là photo)
        try:
            bot.edit_message_caption(
                chat_id=chat_id,
                message_id=message_id,
                caption=new_message,
                parse_mode='HTML',
                reply_markup=reply_markup
            )
            return
        except:
            pass
        
        # Thử cập nhật text (nếu là message)
        try:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=new_message,
                parse_mode='HTML',
                reply_markup=reply_markup
            )
        except Exception as e:
            if "message is not modified" not in str(e):
                logger.error(f"Lỗi cập nhật tin nhắn: {e}")
            
    except Exception as e:
        if "message is not modified" not in str(e):
            logger.error(f"Lỗi trong update_account_message: {e}")

def generate_account_message(account, is_done=False, is_canceled=False):
    """Tạo nội dung tin nhắn cho tài khoản"""
    uid = account.get('uid')
    name = account.get('name', 'Không rõ')
    amount = account.get('amount', 0)
    status = account.get('status', 'live')
    start_time = datetime.fromisoformat(account.get('start_time'))
    end_time = datetime.fromisoformat(account.get('end_time'))
    die_time = account.get('die_time')
    note = account.get('note', '')
    user_name = account.get('user_name', 'Không rõ')
    
    # Format thời gian
    start_time_str = start_time.strftime("%d/%m/%Y %H:%M:%S")
    end_time_str = end_time.strftime("%d/%m/%Y %H:%M:%S")
    
    # Khởi tạo message
    message = ""
    
    if is_done:
        message += "✅ <b>KÈO ĐÃ HOÀN THÀNH</b>\n"
        message += f"💸 <b>ĐÃ CỘNG {format_number(amount)} VND</b>\n"
        message += "   ───｡𖦹°‧──────˙⟡────\n\n"
    elif is_canceled:
        message += "❌ <b>ĐÃ HỦY KÈO!!</b>\n"
        message += "   ───｡𖦹°‧──────˙⟡────\n\n"
    
    # Trạng thái
    if is_done:
        status_emoji = "✅"
        status_text = "HOÀN THÀNH"
    elif is_canceled:
        status_emoji = "❌"
        status_text = "ĐÃ HỦY"
    else:
        status_emoji = "🟢" if status == 'live' else "🔴"
        status_text = "LIVE — ĐANG THEO DÕI" if status == 'live' else "DIE — VÔ HIỆU HOÁ!"
    
    message += f"👤 <b>Tên:</b> {name} — "
    message += f"<code>{uid}</code>\n"
    message += f"🔗 <b>Link profile:</b> <a href='https://facebook.com/{uid}'>Xem link tại đây!</a>\n"
    message += f"📌 <b>Trạng thái:</b> {status_emoji} {status_text}\n"
    message += f"💸 <b>Giá tiền:</b> {format_number(amount)} VND\n"
    message += f"⏰ <b>Ngày lên kèo:</b> {start_time_str}\n"
    
    if note:
        message += f"📝 <b>Note:</b> {note}\n"
    
    if status == 'die' and die_time and not is_done and not is_canceled:
        die_dt = datetime.fromisoformat(die_time)
        message += f"⏰ <b>Die lúc:</b> {die_dt.strftime('%d/%m/%Y %H:%M:%S')}\n"
    
    return message

def generate_buttons(account_id):
    """Tạo nút bấm cho tin nhắn"""
    keyboard = InlineKeyboardMarkup()
    
    keyboard.row(
        InlineKeyboardButton("✅ Done kèo", callback_data=f"done_{account_id}"),
        InlineKeyboardButton("❌ Hủy kèo", callback_data=f"cancel_{account_id}")
    )
    
    keyboard.row(
        InlineKeyboardButton("📋 Chỉnh sửa", callback_data=f"edit_{account_id}")
    )
    
    return keyboard

def generate_edit_buttons(account_id):
    """Tạo nút chỉnh sửa"""
    keyboard = InlineKeyboardMarkup()
    
    keyboard.row(
        InlineKeyboardButton("💸 Sửa giá tiền ", callback_data=f"edit_amount_{account_id}"),
        InlineKeyboardButton("⏰ Chỉnh thời gian", callback_data=f"edit_time_{account_id}")
    )
    
    keyboard.row(
        InlineKeyboardButton("📝 Sửa note", callback_data=f"edit_note_{account_id}")
    )
    
    keyboard.row(
        InlineKeyboardButton("🔙 Quay lại", callback_data=f"back_{account_id}")
    )
    
    return keyboard

# ================= BOT HANDLERS =================
@bot.message_handler(commands=['start', 'help'])
def handle_start_help(message):
    """Xử lý lệnh /start và /help"""
    help_text = (
        "🤖 <b>NUXW BOT - BOT THEO DÕI ACC FACEBOOK</b>\n\n"
        
        "📌 <b>CÁC LỆNH CHÍNH:</b>\n"
        "• <code>/theodoitt &lt;link/uid&gt; &lt;số tiền&gt; &lt;thời gian&gt; [note]</code> - Tạo kèo theo dõi\n"
        "• <code>/thongtinkeo</code> - Xem thông tin kèo của bạn\n"
        "• <code>/botinfo</code> - Thông tin về bot\n\n"
        
        "📝 <b>VÍ DỤ SỬ DỤNG:</b>\n"
        "• <code>/theodoitt https://facebook.com/tg.nux 100K 30d done keo som</code>\n"
        "• <code>/theodoitt 100000000000001 50K 2h done keo cang som cang tot</code>\n"
        "• <code>/theodoitt tg.nux 20K 90m chờ acc die</code>\n\n"
        
        "⚠️ <b>LƯU Ý:</b>\n"
        "• Bot sẽ tự động check acc mỗi 1 phút\n"
        "• Khi acc die, bot sẽ thông báo ngay lập tức\n"
        "• Bạn có thể chỉnh sửa thông tin kèo bất kỳ lúc nào\n\n"
        
        "👨‍💻 <b>Developer:</b> @tghieuX\n"
        "📞 <b>Liên hệ:</b> 0338316701"
    )
    
    bot.reply_to(message, help_text, parse_mode='HTML')

@bot.message_handler(commands=['botinfo'])
def handle_botinfo(message):
    """Xử lý lệnh /botinfo"""
    botinfo_text = (
        "🤖 <b>THÔNG TIN BOT</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        
        "🛠️ <b>Chức năng:</b> Theo dõi trạng thái Live/Die acc Facebook\n"
        "⏱️ <b>Tần suất check:</b> 1 phút/lần\n"
        "👨‍💻 <b>Developer:</b> Trung Hiếu (tghieuX)\n"
        "📱 <b>Telegram:</b> @tghieuX\n"
        "📞 <b>Zalo:</b> 0338316701\n"
        "🔗 <b>Facebook:</b> tg.nux\n\n"
        
        "💖 <b>Cảm ơn bạn đã sử dụng bot!</b>"
    )
    
    bot.reply_to(message, botinfo_text, parse_mode='HTML')

@bot.message_handler(commands=['theodoitt'])
def handle_theodoitt(message):
    """Xử lý lệnh /theodoitt"""
    try:
        # Parse toàn bộ message
        full_text = message.text
        parts = full_text.split()
        
        if len(parts) < 4:
            bot.reply_to(message,
                "❌ <b>Sai cú pháp!</b>\n"
                "✅ <b>Cách dùng:</b> <code>/theodoitt &lt;link/uid&gt; &lt;số tiền&gt; &lt;thời gian&gt; [note]</code>\n"
                "📌 <b>Ví dụ:</b>\n"
                "• <code>/theodoitt https://facebook.com/zuck 20K 30d</code>\n"
                "• <code>/theodoitt 100000000000001 50K 2h done keo cang som cang tot</code>\n"
                "• <code>/theodoitt tg.nux 15K 90m chờ acc die</code>",
                parse_mode='HTML'
            )
            return
        
        # Parse các tham số
        fb_input = parts[1]
        amount_str = parts[2]
        time_str = parts[3]
        
        # Note (phần còn lại của message)
        note = ' '.join(parts[4:]) if len(parts) > 4 else ''
        
        # Gửi thông báo đang xử lý
        processing_msg = bot.reply_to(message, "🔄 <b>Đang get UID từ link...</b>", parse_mode='HTML')
        
        # Trích UID
        uid = extract_uid_from_input(fb_input)
        if not uid:
            bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=processing_msg.message_id,
                text="❌ Không thể lấy UID từ link/uid bạn cung cấp!"
            )
            return
        
        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=processing_msg.message_id,
            text=f"✅ Đã lấy được UID: {uid}!"
        )
        
        # Lấy thông tin tài khoản
        info = get_fb_info(uid)
        if 'error' in info:
            bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=processing_msg.message_id,
                text=f"❌ Lỗi khi lấy thông tin: {info['error']}"
            )
            return
        
        fb_data = info['data']
        name = fb_data.get('name', 'Không rõ')
        
        # Parse số tiền và thời gian
        amount = parse_amount(amount_str)
        duration_seconds = parse_time_duration(time_str)
        
        if amount <= 0:
            bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=processing_msg.message_id,
                text="❌ Số tiền không hợp lệ!"
            )
            return
        
        if duration_seconds <= 0:
            bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=processing_msg.message_id,
                text="❌ Thời gian không hợp lệ!"
            )
            return
        
        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=processing_msg.message_id,
            text=f"✅ Thông tin: {name}\n🔄 Đang chuẩn bị..."
        )
        
        # Tạo account object
        account_id = str(int(time.time()))
        start_time = datetime.now()
        end_time = start_time + timedelta(seconds=duration_seconds)
        
        # Lấy username của người dùng
        user_name = message.from_user.username
        if user_name:
            user_name = f"@{user_name}"
        else:
            user_name = message.from_user.first_name or "Không rõ"
        
        account = {
            'id': account_id,
            'uid': uid,
            'name': name,
            'amount': amount,
            'amount_str': amount_str.upper(),
            'time_str': time_str,
            'duration': duration_seconds,
            'note': note,
            'status': 'live',
            'chat_id': message.chat.id,
            'user_id': message.from_user.id,
            'user_name': user_name,
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'message_id': None
        }
        
        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=processing_msg.message_id,
            text="🎯 <b>Sẵn sàng!</b>"
        )
        
        # Lấy avatar từ API (ưu tiên avatar từ API info)
        avatar_url = get_avatar_from_api(uid)
        
        if avatar_url:
            try:
                # Gửi tin nhắn với avatar và thông tin kèo
                sent_msg = bot.send_photo(
                    chat_id=message.chat.id,
                    photo=avatar_url,
                    caption=generate_account_message(account),
                    parse_mode='HTML',
                    reply_markup=generate_buttons(account_id)
                )
            except Exception as e:
                logger.error(f"Lỗi khi gửi ảnh: {e}")
                # Nếu gửi ảnh lỗi, gửi tin nhắn bình thường
                sent_msg = bot.send_message(
                    chat_id=message.chat.id,
                    text=generate_account_message(account),
                    parse_mode='HTML',
                    reply_markup=generate_buttons(account_id)
                )
        else:
            # Nếu không có avatar, gửi tin nhắn bình thường
            sent_msg = bot.send_message(
                chat_id=message.chat.id,
                text=generate_account_message(account),
                parse_mode='HTML',
                reply_markup=generate_buttons(account_id)
            )
        
        account['message_id'] = sent_msg.message_id
        monitored_accounts.append(account)
        save_data(ACCOUNTS_FILE, monitored_accounts)
        
        # Xóa tin nhắn xử lý
        try:
            bot.delete_message(message.chat.id, processing_msg.message_id)
        except:
            pass
        
    except Exception as e:
        logger.error(f"Lỗi trong handle_theodoitt: {e}")
        try:
            bot.reply_to(message, "❌ Đã xảy ra lỗi khi xử lý lệnh!")
        except:
            pass

@bot.message_handler(commands=['thongtinkeo'])
def handle_thongtinkeo(message):
    """Xử lý lệnh /thongtinkeo"""
    try:
        user_id = message.from_user.id
        
        # Lọc kèo theo user
        user_monitored = [acc for acc in monitored_accounts if acc.get('user_id') == user_id]
        user_done = [acc for acc in done_keo if acc.get('user_id') == user_id]
        user_canceled = [acc for acc in canceled_keo if acc.get('user_id') == user_id]
        
        # Tính tổng tiền
        total_amount = sum(acc.get('amount', 0) for acc in user_done)
        
        # Tạo message
        response = "📋 <b>THÔNG TIN KÈO CỦA BẠN</b>\n\n"
        
        response += "📊 <b>List acc đang theo dõi:</b>\n"
        if user_monitored:
            for i, acc in enumerate(user_monitored, 1):
                name = acc.get('name', 'Không rõ')
                amount = format_number(acc.get('amount', 0))
                status = "🟢 Live" if acc.get('status') == 'live' else "🔴 Die"
                response += f"{i}. {name} - {amount}VND - {status}\n"
        else:
            response += "📭 Không có kèo nào đang theo dõi\n"
        
        response += "\n✅ <b>List kèo done:</b>\n"
        if user_done:
            for i, acc in enumerate(user_done, 1):
                amount = format_number(acc.get('amount', 0))
                response += f"{i}. {amount} VND\n"
        else:
            response += "📭 Không có kèo done\n"
        
        response += "\n❌ <b>List kèo hủy:</b>\n"
        if user_canceled:
            for i, acc in enumerate(user_canceled, 1):
                name = acc.get('name', 'Không rõ')
                response += f"{i}. {name}\n"
        else:
            response += "📭 Không có kèo hủy\n"
        
        response += f"\n💸 <b>Tổng tiền:</b> {format_number(total_amount)} VND"
        
        bot.reply_to(message, response, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Lỗi trong handle_thongtinkeo: {e}")
        bot.reply_to(message, "❌ Đã xảy ra lỗi khi xử lý lệnh!")

# ================= CALLBACK HANDLERS =================
@bot.callback_query_handler(func=lambda call: call.data.startswith('done_'))
def handle_done_callback(call):
    """Xử lý nút Done kèo"""
    try:
        account_id = call.data.split('_')[1]
        
        # Tìm account
        account = None
        for acc in monitored_accounts:
            if acc['id'] == account_id:
                account = acc
                break
        
        if not account:
            bot.answer_callback_query(call.id, "❌ Không tìm thấy kèo này!")
            return
        
        # Xử lý nút Done kèo
        account['status'] = 'done'
        account['done_time'] = datetime.now().isoformat()
        
        done_keo.append(account)
        monitored_accounts.remove(account)
        
        save_data(ACCOUNTS_FILE, monitored_accounts)
        save_data(DONE_FILE, done_keo)
        
        # Cập nhật tin nhắn với is_done=True và XÓA NÚT
        try:
            new_message = generate_account_message(account, is_done=True)
            
            # Thử edit caption (nếu là photo) và XÓA NÚT
            try:
                bot.edit_message_caption(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    caption=new_message,
                    parse_mode='HTML',
                    reply_markup=None  # XÓA NÚT
                )
            except:
                # Thử edit text (nếu là text) và XÓA NÚT
                try:
                    bot.edit_message_text(
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id,
                        text=new_message,
                        parse_mode='HTML',
                        reply_markup=None  # XÓA NÚT
                    )
                except Exception as e:
                    if "message is not modified" not in str(e):
                        logger.error(f"Lỗi update khi done: {e}")
                    
                    # Fallback cuối cùng: chỉ xóa nút
                    try:
                        bot.edit_message_reply_markup(
                            chat_id=call.message.chat.id,
                            message_id=call.message.message_id,
                            reply_markup=None
                        )
                    except:
                        pass
            
        except Exception as e:
            logger.error(f"Lỗi update khi done: {e}")
        
        bot.answer_callback_query(call.id, "✅ Đã đánh dấu kèo hoàn thành!")
        
    except Exception as e:
        logger.error(f"Lỗi trong handle_done_callback: {e}")
        bot.answer_callback_query(call.id, "❌ Đã xảy ra lỗi!")

@bot.callback_query_handler(func=lambda call: call.data.startswith('cancel_'))
def handle_cancel_callback(call):
    """Xử lý nút Hủy kèo"""
    try:
        account_id = call.data.split('_')[1]
        
        # Tìm account
        account = None
        for acc in monitored_accounts:
            if acc['id'] == account_id:
                account = acc
                break
        
        if not account:
            bot.answer_callback_query(call.id, "❌ Không tìm thấy kèo này!")
            return
        
        # Xử lý nút Hủy kèo
        account['status'] = 'canceled'
        canceled_keo.append(account)
        monitored_accounts.remove(account)
        
        save_data(ACCOUNTS_FILE, monitored_accounts)
        save_data(CANCELED_FILE, canceled_keo)
        
        # Cập nhật tin nhắn với is_canceled=True và XÓA NÚT
        try:
            new_message = generate_account_message(account, is_canceled=True)
            
            # Thử edit caption (nếu là photo) và XÓA NÚT
            try:
                bot.edit_message_caption(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    caption=new_message,
                    parse_mode='HTML',
                    reply_markup=None  # XÓA NÚT
                )
            except:
                # Thử edit text (nếu là text) và XÓA NÚT
                try:
                    bot.edit_message_text(
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id,
                        text=new_message,
                        parse_mode='HTML',
                        reply_markup=None  # XÓA NÚT
                    )
                except Exception as e:
                    if "message is not modified" not in str(e):
                        logger.error(f"Lỗi update khi cancel: {e}")
                    
                    # Fallback cuối cùng: chỉ xóa nút
                    try:
                        bot.edit_message_reply_markup(
                            chat_id=call.message.chat.id,
                            message_id=call.message.message_id,
                            reply_markup=None
                        )
                    except:
                        pass
            
        except Exception as e:
            logger.error(f"Lỗi update khi cancel: {e}")
        
        bot.answer_callback_query(call.id, "❌ Đã hủy kèo!")
        
    except Exception as e:
        logger.error(f"Lỗi trong handle_cancel_callback: {e}")
        bot.answer_callback_query(call.id, "❌ Đã xảy ra lỗi!")

@bot.callback_query_handler(func=lambda call: call.data.startswith('edit_'))
def handle_edit_callback(call):
    """Xử lý nút chỉnh sửa"""
    try:
        data = call.data
        account_id = data.split('_')[-1]
        
        # Kiểm tra account còn tồn tại không
        account_exists = any(acc['id'] == account_id for acc in monitored_accounts)
        if not account_exists:
            bot.answer_callback_query(call.id, "❌ Kèo này không tồn tại hoặc đã bị xóa!")
            return
        
        if data == f"edit_{account_id}":
            # Hiển thị menu chỉnh sửa
            bot.edit_message_reply_markup(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=generate_edit_buttons(account_id)
            )
            
            bot.answer_callback_query(call.id, "📋 Chọn mục cần chỉnh sửa")
            
        elif data.startswith('edit_amount_'):
            # Yêu cầu nhập số tiền mới
            msg = bot.send_message(
                call.message.chat.id,
                f"💰 <b>Nhập số tiền mới cho kèo:</b>\n"
                f"<i>Ví dụ: 20K, 1.5M, 15000</i>",
                parse_mode='HTML'
            )
            
            # Lưu thông tin để xử lý sau
            bot.register_next_step_handler(msg, process_edit_amount, account_id, call.message.message_id)
            bot.answer_callback_query(call.id, "💰 Nhập số tiền mới")
            
        elif data.startswith('edit_time_'):
            # Yêu cầu nhập thời gian mới
            msg = bot.send_message(
                call.message.chat.id,
                f"⏰ <b>Nhập thời gian mới cho kèo:</b>\n"
                f"<i>Ví dụ: 30d, 2h, 90m, 3600s</i>",
                parse_mode='HTML'
            )
            
            bot.register_next_step_handler(msg, process_edit_time, account_id, call.message.message_id)
            bot.answer_callback_query(call.id, "⏰ Nhập thời gian mới")
            
        elif data.startswith('edit_note_'):
            # Yêu cầu nhập note mới
            msg = bot.send_message(
                call.message.chat.id,
                f"📝 <b>Nhập note mới cho kèo:</b>\n"
                f"<i>Ghi chú, lưu ý về kèo này</i>",
                parse_mode='HTML'
            )
            
            bot.register_next_step_handler(msg, process_edit_note, account_id, call.message.message_id)
            bot.answer_callback_query(call.id, "📝 Nhập note mới")
            
        elif data.startswith('back_'):
            # Quay lại nút chính
            bot.edit_message_reply_markup(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=generate_buttons(account_id)
            )
            
            bot.answer_callback_query(call.id)
            
    except Exception as e:
        logger.error(f"Lỗi trong handle_edit_callback: {e}")
        try:
            bot.answer_callback_query(call.id, "❌ Đã xảy ra lỗi!")
        except:
            pass

def process_edit_amount(message, account_id, original_message_id):
    """Xử lý chỉnh sửa số tiền"""
    try:
        amount_str = message.text.strip()
        new_amount = parse_amount(amount_str)
        
        if new_amount <= 0:
            bot.reply_to(message, "❌ Số tiền không hợp lệ!")
            return
        
        # Cập nhật account
        updated = False
        for acc in monitored_accounts:
            if acc['id'] == account_id:
                if acc.get('amount') != new_amount:
                    acc['amount'] = new_amount
                    acc['amount_str'] = amount_str.upper()
                    updated = True
                    
                    # Cập nhật tin nhắn kèo
                    update_account_message(message.chat.id, original_message_id, acc)
                    
                    save_data(ACCOUNTS_FILE, monitored_accounts)
                    
                    bot.reply_to(message, f"✅ Đã cập nhật số tiền thành: {format_number(new_amount)} VND")
                else:
                    bot.reply_to(message, "⚠️ Số tiền mới giống số tiền cũ!")
                break
        
        if not updated:
            bot.reply_to(message, "❌ Không tìm thấy kèo để cập nhật!")
    
    except Exception as e:
        logger.error(f"Lỗi trong process_edit_amount: {e}")
        bot.reply_to(message, "❌ Đã xảy ra lỗi khi cập nhật số tiền!")

def process_edit_time(message, account_id, original_message_id):
    """Xử lý chỉnh sửa thời gian"""
    try:
        time_str = message.text.strip()
        new_duration = parse_time_duration(time_str)
        
        if new_duration <= 0:
            bot.reply_to(message, "❌ Thời gian không hợp lệ!")
            return
        
        # Cập nhật account
        updated = False
        for acc in monitored_accounts:
            if acc['id'] == account_id:
                start_time = datetime.fromisoformat(acc['start_time'])
                new_end_time = start_time + timedelta(seconds=new_duration)
                
                if acc.get('duration') != new_duration:
                    acc['duration'] = new_duration
                    acc['time_str'] = time_str
                    acc['end_time'] = new_end_time.isoformat()
                    updated = True
                    
                    # Cập nhật tin nhắn kèo
                    update_account_message(message.chat.id, original_message_id, acc)
                    
                    save_data(ACCOUNTS_FILE, monitored_accounts)
                    
                    bot.reply_to(message, f"✅ Đã cập nhật thời gian thành: {time_str}")
                else:
                    bot.reply_to(message, "⚠️ Thời gian mới giống thời gian cũ!")
                break
        
        if not updated:
            bot.reply_to(message, "❌ Không tìm thấy kèo để cập nhật!")
    
    except Exception as e:
        logger.error(f"Lỗi trong process_edit_time: {e}")
        bot.reply_to(message, "❌ Đã xảy ra lỗi khi cập nhật thời gian!")

def process_edit_note(message, account_id, original_message_id):
    """Xử lý chỉnh sửa note"""
    try:
        new_note = message.text.strip()
        
        # Cập nhật account
        updated = False
        for acc in monitored_accounts:
            if acc['id'] == account_id:
                if acc.get('note') != new_note:
                    acc['note'] = new_note
                    updated = True
                    
                    # Cập nhật tin nhắn kèo
                    update_account_message(message.chat.id, original_message_id, acc)
                    
                    save_data(ACCOUNTS_FILE, monitored_accounts)
                    
                    bot.reply_to(message, f"✅ Đã cập nhật note")
                else:
                    bot.reply_to(message, "⚠️ Note mới giống note cũ!")
                break
        
        if not updated:
            bot.reply_to(message, "❌ Không tìm thấy kèo để cập nhật!")
    
    except Exception as e:
        logger.error(f"Lỗi trong process_edit_note: {e}")
        bot.reply_to(message, "❌ Đã xảy ra lỗi khi cập nhật note!")

# ================= MAIN =================
def start_monitoring():
    """Khởi động thread theo dõi"""
    monitor_thread = threading.Thread(target=monitor_accounts, daemon=True)
    monitor_thread.start()

if __name__ == "__main__":
    print("🤖 BOT THEO DÕI ACC FACEBOOK - BY TGHIEUX")
    print("🚀 Đang khởi động bot...")
    
    start_monitoring()
    
    while True:
        try:
            bot.polling(none_stop=True, timeout=30, long_polling_timeout=30)
        except Exception as e:
            if "Connection aborted" not in str(e) and "RemoteDisconnected" not in str(e):
                logger.error(f"Lỗi polling: {e}")
            time.sleep(10)  # Chờ 10s trước khi thử lại
