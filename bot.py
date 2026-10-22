import os
import sqlite3
from datetime import datetime, timezone, timedelta
from flask import Flask, request, jsonify
from flask_cors import CORS
import telebot
from telebot import types

# Ձեր բոտի Տոկենը
TOKEN = '8488488247:AAH7lJhja4U0IKwD_Mt2MCd7GoYZgE3XpYY'
bot = telebot.TeleBot(TOKEN)

# Խմբի և թեմաների (Topics) ID-ները
GROUP_CHAT_ID = -1004454975285          
ACTIVE_THREAD_ID = 6                   # «Նոր / Ակտիվ Հայտեր» (Կայքի հայտերի և /lead-ի համար)
TASKS_THREAD_ID = 24                   # «Առաջադրանքներ» (Ներքին /task-երի համար)
COMPLETED_THREAD_ID = 8                # «Ավարտված Աշխատանքներ» Topic-ի ID-ն

# Հիմնական ադմինի username-ը (առանց @ նշանի)
ADMIN_USERNAME = "HAYQ_1975"

# Երևանի ժամանակ (UTC+4)
YEREVAN_TZ = timezone(timedelta(hours=4))

app = Flask(__name__)
CORS(app)  # Թույլատրում է հարցումներ կայքից

def init_db():
    conn = sqlite3.connect('tasks.db')
    cursor = conn.cursor()
    # Հայտերի աղյուսակ (կայքից և /lead-ից եկող)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            message_id INTEGER PRIMARY KEY,
            chat_id INTEGER,
            client_name TEXT,
            client_phone TEXT,
            task_text TEXT,
            status TEXT,
            assignee TEXT
        )
    ''')
    # Ներքին Task-երի աղյուսակ (/task հրամանի համար)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS team_tasks (
            message_id INTEGER PRIMARY KEY,
            chat_id INTEGER,
            topic_id INTEGER,
            task_text TEXT,
            status TEXT,
            assignee TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# --- ՍՏՈՒԳՈՒՄ՝ ԱՐԴՅՈՔ ՕԳՏԱՏԵՐԸ ԱԴՄԻՆ Է ԹԵ ՉԱՏԻ ՏԵՐԸ ---
def check_is_admin_or_owner(user_id, username):
    if username and username.lower() == ADMIN_USERNAME.lower():
        return True
    
    try:
        chat_member = bot.get_chat_member(GROUP_CHAT_ID, user_id)
        if chat_member.status in ['creator', 'administrator']:
            return True
    except Exception as e:
        print(f"Սխալ կարգավիճակը ստուգելիս: {e}")
        
    return False

# --- ՖՈՒՆԿՑԻԱ ԿԱՅՔԻ ՀԱՅՏԵՐԻ ՀԱՄԱՐ (Գնում է «Նոր / Ակտիվ Հայտեր» - 6) ---
def create_lead_in_telegram(name, phone, issue):
    msg_body = (
        f"📌 **ՆՈՐ ՀԱՅՏ (ԿԱՅՔԻՑ)**\n\n"
        f"👤 Անուն՝ {name}\n"
        f"📞 Հեռախոս՝ {phone}\n"
        f"💬 Խնդիր՝ {issue}\n\n"
        f"• Վիճակ՝ 🟢 Ազատ է\n"
        f"• Կատարող՝ ➖ (Վերցված չէ)"
    )

    markup = types.InlineKeyboardMarkup()
    btn_take = types.InlineKeyboardButton("⏳ Կվերցնեմ", callback_data="take_task")
    markup.add(btn_take)

    sent_msg = bot.send_message(
        chat_id=GROUP_CHAT_ID,
        text=msg_body,
        parse_mode="Markdown",
        reply_markup=markup,
        message_thread_id=ACTIVE_THREAD_ID  # 6
    )

    conn = sqlite3.connect('tasks.db')
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO tasks (message_id, chat_id, client_name, client_phone, task_text, status, assignee) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (sent_msg.message_id, sent_msg.chat.id, name, phone, issue, "🟢 Ազատ է", None)
    )
    conn.commit()
    conn.close()
    return sent_msg


# --- 1. ԿԱՅՔԻՑ ՀԱՅՏԵՐԻ ՍՏԱՑՄԱՆ ENDPOINT ---
@app.route('/submit-lead', methods=['POST'])
def submit_lead():
    data = request.json
    name = data.get('name', 'Անհայտ')
    phone = data.get('phone', 'Անհայտ')
    issue = data.get('issue', 'Նշված չէ')

    try:
        create_lead_in_telegram(name, phone, issue)
        return jsonify({"status": "success", "message": "Հայտը հաջողությամբ ուղարկվեց!"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# --- 2. ԱԴՄԻՆԻ / ՉԱՏԻ ՏԵՐԻ ՁԵՌՔՈՎ ՀԱՅՏ ԱՎԵԼԱՑՆԵԼՈՒ ՀՐԱՄԱՆ (/lead) ---
@bot.message_handler(commands=['lead', 'հայտ'])
def manual_lead(message):
    user_id = message.from_user.id
    username = message.from_user.username

    if not check_is_admin_or_owner(user_id, username):
        bot.reply_to(message, "⚠️ Միայն ադմինը և չատի տերը կարող են ձեռքով հայտ ավելացնել։")
        return

    text_parts = message.text.split(maxsplit=1)
    if len(text_parts) < 2:
        bot.reply_to(
            message, 
            "❌ Սխալ ձևաչափ։ Օգտագործեք հետևյալ կերպ:\n"
            "`/lead Անուն | Հեռախոս | Խնդրի նկարագրություն`", 
            parse_mode="Markdown"
        )
        return

    params = text_parts[1].split('|')
    if len(params) < 3:
        bot.reply_to(
            message, 
            "❌ Խնդրում ենք պահպանել բաժանման նշանները (|):\n"
            "`/lead Անուն | Հեռախոս | Խնդիր`", 
            parse_mode="Markdown"
        )
        return

    name = params[0].strip()
    phone = params[1].strip()
    issue = params[2].strip()

    try:
        create_lead_in_telegram(name, phone, issue)
        bot.reply_to(message, "✅ Հայտը հաջողությամբ ավելացվեց Ակտիվ հայտերի բաժին։")
    except Exception as e:
        bot.reply_to(message, f"❌ Սխալ տեղի ունեցավ: {e}")


# --- 3. ՆԵՐՔԻՆ TASK-ԵՐԻ ՍՏԵՂԾՄԱՆ ՀՐԱՄԱՆ (/task -> Գնում է 24 թեմա) ---
@bot.message_handler(commands=['task', 'առաջադրանք'])
def manual_task(message):
    user_id = message.from_user.id
    username = message.from_user.username

    if not check_is_admin_or_owner(user_id, username):
        bot.reply_to(message, "⚠️ Միայն ադմինը և չատի տերը կարող են նոր task տալ։")
        return

    text_parts = message.text.split(maxsplit=1)
    if len(text_parts) < 2:
        bot.reply_to(
            message, 
            "❌ Սխալ ձևաչափ։ Օգտագործեք հետևյալ կերպ:\n"
            "`/task Առաջադրանքի նկարագրություն`\n\n"
            "Օրինակ՝ `/task Ստուգել սերվերի լոգերը`", 
            parse_mode="Markdown"
        )
        return

    task_desc = text_parts[1].strip()
    topic_id = TASKS_THREAD_ID  # 24

    msg_body = (
        f"📋 **ՆՈՐ ԱՌԱՋԱԴՐԱՆՔ (TASK)**\n\n"
        f"💬 Նկարագրություն՝ {task_desc}\n\n"
        f"• Վիճակ՝ 🟢 Ազատ է\n"
        f"• Կատարող՝ ➖ (Վերցված չէ)"
    )

    markup = types.InlineKeyboardMarkup()
    btn_take = types.InlineKeyboardButton("⏳ Վերցնել Task-ը", callback_data="take_team_task")
    markup.add(btn_take)

    try:
        sent_msg = bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text=msg_body,
            parse_mode="Markdown",
            reply_markup=markup,
            message_thread_id=topic_id
        )

        conn = sqlite3.connect('tasks.db')
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO team_tasks (message_id, chat_id, topic_id, task_text, status, assignee) VALUES (?, ?, ?, ?, ?, ?)",
            (sent_msg.message_id, sent_msg.chat.id, topic_id, task_desc, "🟢 Ազատ է", None)
        )
        conn.commit()
        conn.close()

        bot.reply_to(message, "✅ Առաջադրանքը հաջողությամբ ուղարկվեց Առաջադրանքների թեմա (24)։")
    except Exception as e:
        bot.reply_to(message, f"❌ Սխալ տեղի ունեցավ ուղարկելիս: {e}")


# --- 4. TELEGRAM ԿՈՃԱԿՆԵՐԻ ԵՎ ԳՈՐԾԱՐՔՆԵՐԻ ՄՇԱԿՈՒՄ ---
@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    message = call.message
    
    if call.from_user.username:
        user_name = f"@{call.from_user.username}"
    else:
        user_name = call.from_user.first_name

    conn = sqlite3.connect('tasks.db')
    cursor = conn.cursor()

    cursor.execute("SELECT client_name, client_phone, task_text, status, assignee FROM tasks WHERE message_id = ?", (message.message_id,))
    row = cursor.fetchone()

    if row:
        client_name, client_phone, task_text, status, assignee = row

        if call.data == "take_task":
            new_status = "⏳ Կատարման ընթացքում է"
            new_text = (
                f"📌 **ԱԿՏԻՎ ՀԱՅՏ**\n\n"
                f"👤 Անուն՝ {client_name}\n"
                f"📞 Հեռախոս՝ {client_phone}\n"
                f"💬 Խնդիր՝ {task_text}\n\n"
                f"• Վիճակ՝ {new_status}\n"
                f"• Կատարող՝ {user_name}"
            )
            
            markup = types.InlineKeyboardMarkup()
            btn_done = types.InlineKeyboardButton("✅ Ավարտել", callback_data="done_task")
            markup.add(btn_done)

            cursor.execute("UPDATE tasks SET status = ?, assignee = ? WHERE message_id = ?", (new_status, user_name, message.message_id))
            conn.commit()
            
            bot.edit_message_text(chat_id=message.chat.id, message_id=message.message_id, text=new_text, parse_mode="Markdown", reply_markup=markup)
            bot.answer_callback_query(call.id, f"Դուք վերցրիք այս հայտը ({user_name})։")

        elif call.data == "done_task":
            current_assignee = assignee if assignee else user_name
            now = datetime.now(YEREVAN_TZ).strftime("%d.%m.%Y %H:%M")

            try:
                bot.delete_message(message.chat.id, message.message_id)
            except Exception:
                pass

            completed_text = (
                f"✅ **ԱՎԱՐՏՎԱԾ ԱՇԽԱՏԱՆՔ**\n\n"
                f"👤 Հաճախորդ՝ {client_name}\n"
                f"📞 Հեռախոս՝ {client_phone}\n"
                f"💬 Խնդիր՝ {task_text}\n\n"
                f"🛠 Կատարող՝ {current_assignee}\n"
                f"🕐 Ավարտման ժամ՝ {now}"
            )
            
            bot.send_message(
                chat_id=GROUP_CHAT_ID,
                text=completed_text,
                parse_mode="Markdown",
                message_thread_id=COMPLETED_THREAD_ID
            )

            cursor.execute("UPDATE tasks SET status = ? WHERE message_id = ?", ("✅ Ավարտված է", message.message_id))
            conn.commit()
            bot.answer_callback_query(call.id, "Աշխատանքը հաջողությամբ տեղափոխվեց ավարտվածների բաժին։")

    else:
        cursor.execute("SELECT task_text, status, assignee FROM team_tasks WHERE message_id = ?", (message.message_id,))
        team_row = cursor.fetchone()

        if team_row:
            task_text, status, assignee = team_row

            if call.data == "take_team_task":
                new_status = "⏳ Կատարման ընթացքում է"
                new_text = (
                    f"📋 **ԱՌԱՋԱԴՐԱՆՔ (TASK)**\n\n"
                    f"💬 Նկարագրություն՝ {task_text}\n\n"
                    f"• Վիճակ՝ {new_status}\n"
                    f"• Կատարող՝ {user_name}"
                )
                
                markup = types.InlineKeyboardMarkup()
                btn_done = types.InlineKeyboardButton("✅ Ավարտել Task-ը", callback_data="done_team_task")
                markup.add(btn_done)

                cursor.execute("UPDATE team_tasks SET status = ?, assignee = ? WHERE message_id = ?", (new_status, user_name, message.message_id))
                conn.commit()
                
                bot.edit_message_text(chat_id=message.chat.id, message_id=message.message_id, text=new_text, parse_mode="Markdown", reply_markup=markup)
                bot.answer_callback_query(call.id, f"Դուք վերցրիք այս առաջադրանքը ({user_name})։")

            elif call.data == "done_team_task":
                current_assignee = assignee if assignee else user_name
                now = datetime.now(YEREVAN_TZ).strftime("%d.%m.%Y %H:%M")

                completed_text = (
                    f"✅ **ԱՎԱՐՏՎԱԾ ԱՌԱՋԱԴՐԱՆՔ**\n\n"
                    f"💬 Նկարագրություն՝ {task_text}\n\n"
                    f"🛠 Կատարող՝ {current_assignee}\n"
                    f"🕐 Ավարտման ժամ՝ {now}"
                )
                
                markup_none = types.InlineKeyboardMarkup()
                cursor.execute("UPDATE team_tasks SET status = ? WHERE message_id = ?", ("✅ Ավարտված է", message.message_id))
                conn.commit()

                bot.edit_message_text(chat_id=message.chat.id, message_id=message.message_id, text=completed_text, parse_mode="Markdown", reply_markup=markup_none)
                bot.answer_callback_query(call.id, "Առաջադրանքը նշվեց որպես ավարտված։")

    conn.close()

if __name__ == '__main__':
    import threading
    bot_thread = threading.Thread(target=bot.infinity_polling)
    bot_thread.daemon = True
    bot_thread.start()

    print("Բոտը և սերվերը աշխատում են ամպում...")
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
