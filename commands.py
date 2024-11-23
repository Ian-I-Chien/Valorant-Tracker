from file_manager import load_json, save_json

CONSTANTS_FILE = 'config/constants.json'
USER_DATA_FILE = 'data/user_data.json'

constants = load_json(CONSTANTS_FILE)
TARGET_KEYWORDS = constants["target_keywords"]
INSULT_KEYWORDS = constants["insult_keywords"]

user_data = load_json(USER_DATA_FILE)

async def handle_rank_command(client, message):
    if not any(user_info['mentions'] > 0 for user_info in user_data.values()):
        await message.channel.send("沒人臭他QQ你們都會上天堂<3")
        return

    sorted_users = sorted(
        ((user_name, user_info) for user_name, user_info in user_data.items() if user_info['mentions'] > 0),
        key=lambda x: x[1]['mentions'],
        reverse=True
    )

    ranking_message = "今天臭修哥的排名：\n"

    if sorted_users:
        first_user_name, first_user_info = sorted_users[0]
        ranking_message += (
            f"恭喜臭臭人[ {first_user_info['name']} ] 總共臭了 {first_user_info['mentions']} 次！你是真會下地獄 ==\n"
            "請聯繫YUI繳交贖罪券(支援轉帳,街口,LinePay) 1000$ 乙次\n"
        )

    for idx, (user_name, user_info) in enumerate(sorted_users[1:5], start=2):
        ranking_message += f"{idx}. {user_info['name']} (ID: {user_name}) - {user_info['mentions']} 次\n"

    await message.channel.send(ranking_message)

async def handle_insult(client, message):
    user_name = message.author.name
    if any(mention.lower() in message.content.lower() for mention in TARGET_KEYWORDS) and \
       any(insult in message.content for insult in INSULT_KEYWORDS):
        if user_name in user_data:
            user_data[user_name]['mentions'] += 1
        else:
            user_data[user_name] = {'name': user_name, 'mentions': 1}

        save_json(USER_DATA_FILE, user_data)

        mentions_count = user_data[user_name]['mentions']
        user_display_name = user_data[user_name]['name']
        await message.channel.send(f'{user_display_name} 今天臭修哥的次數: {mentions_count}')
