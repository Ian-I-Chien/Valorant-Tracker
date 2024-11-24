from file_manager import load_json, save_json
from datetime import datetime

CONSTANTS_FILE = 'config/constants.json'
USER_DATA_FILE = 'data/user_data.json'

constants = load_json(CONSTANTS_FILE)
TARGET_KEYWORDS = constants["target_keywords"]
INSULT_KEYWORDS = constants["insult_keywords"]

user_data = load_json(USER_DATA_FILE)

def check_and_reset_mentions():
    current_date = datetime.now().strftime('%Y-%m-%d')
    
    if "last_reset_date" not in constants:
        constants["last_reset_date"] = current_date
        save_json(CONSTANTS_FILE, constants)

    last_reset_date = constants["last_reset_date"]

    if current_date != last_reset_date:
        reset_daily_mentions()
        constants["last_reset_date"] = current_date
        save_json(CONSTANTS_FILE, constants)


def reset_daily_mentions():
    current_date = datetime.now().strftime('%Y-%m-%d')
    for user_name, user_info in user_data.items():
        user_info['mentions'] = 0 
        user_info['last_reset_date'] = current_date
    save_json(USER_DATA_FILE, user_data)


def build_rank_message(sorted_users):
    if not sorted_users:
        return "沒人臭他QQ你們都會上天堂<3"

    top_user_name, top_user_info = sorted_users[0]
    rank_message = (
        f"歷史排名：\n"
        f"恭喜臭臭人 [ {top_user_info['display_name']} ({top_user_info['name']}) ] 總共臭了 {top_user_info['history_mentions']} 次！\n"
        "你是真會下地獄 ==\n"
        "請聯繫管理員繳交贖罪券 (支援轉帳, 街口, LinePay) 1000$\n\n"
    )

    for idx, (user_name, user_info) in enumerate(sorted_users[1:5], start=2):
        rank_message += f"{idx}. {user_info['display_name']} ({user_info['name']}) - {user_info['history_mentions']} 次\n"

    return rank_message

async def handle_rank_command(client, message):
    sorted_users = sorted(
        (
            (user_name, {**user_info, "display_name": user_info.get("display_name", user_info["name"])})
            for user_name, user_info in user_data.items()
            if user_info['history_mentions'] > 0
        ),
        key=lambda x: x[1]['history_mentions'],
        reverse=True
    )

    ranking_message = build_rank_message(sorted_users)
    await message.channel.send(ranking_message)

async def handle_insult(client, message):
    user_name = message.author.name
    current_date = datetime.now().strftime('%Y-%m-%d')

    if any(keyword.lower() in message.content.lower() for keyword in TARGET_KEYWORDS) and \
       any(insult in message.content for insult in INSULT_KEYWORDS):

        if user_name not in user_data:
            user_data[user_name] = {
                'name': message.author.display_name,
                'display_name': message.author.display_name,
                'mentions': 1,
                'history_mentions': 1,
                'last_reset_date': current_date
            }
        else:
            user_data[user_name]['display_name'] = message.author.display_name
            user_data[user_name]['mentions'] += 1

            if 'history_mentions' not in user_data[user_name]:
                user_data[user_name]['history_mentions'] = 0
            user_data[user_name]['history_mentions'] += 1

            user_data[user_name]['last_reset_date'] = user_data[user_name].get('last_reset_date', current_date)

        save_json(USER_DATA_FILE, user_data)

        mentions_count = user_data[user_name]['mentions']
        user_nick_name = user_data[user_name]['name']
        response_message = f"{message.author.display_name} ({user_nick_name})\n今天臭修哥的次數: {mentions_count}"
        await message.channel.send(response_message)
