import discord
from file_manager import load_json, save_json
from datetime import datetime
from model.toxic_detector import ToxicMessageProcessor, ToxicDetectorResult

CONSTANTS_FILE = 'config/constants.json'
USER_DATA_FILE = 'data/user_data.json'

default_constants = {
    "target_keywords": ["user"],
    "insult_keywords": ["toxic"],
    "praise_keywords": ["awesome"],
    "last_reset_date": "1970-01-01"
}

default_user_data = {
    "example_user": {
        "name": "example_user",
        "display_name": "Example User",
        "insult_mentions": 0,
        "praise_mentions": 0,
        "history_insult_mentions": 0,
        "histiry_praise_mentions": 0,
        "last_reset_date": "1970-01-01"
    }
}


constants = load_json(CONSTANTS_FILE, default_constants)
TARGET_KEYWORDS = constants["target_keywords"]
INSULT_KEYWORDS = constants["insult_keywords"]
PRAISE_KEYWORDS = constants["praise_keywords"]

user_data = load_json(USER_DATA_FILE, default_user_data)


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


async def handle_rank_command(interaction: discord.Interaction):
    sorted_insults = sorted(
        (
            (user_name, {**user_info, "display_name": user_info.get("display_name", user_info["name"])})
            for user_name, user_info in user_data.items()
            if user_info.get('insult_mentions', 0) > 0
        ),
        key=lambda x: x[1]['insult_mentions'],
        reverse=True
    )

    sorted_praises = sorted(
        (
            (user_name, {**user_info, "display_name": user_info.get("display_name", user_info["name"])})
            for user_name, user_info in user_data.items()
            if user_info.get('praise_mentions', 0) > 0
        ),
        key=lambda x: x[1]['praise_mentions'],
        reverse=True
    )

    insult_rank_message = build_rank_message(sorted_insults, "insult")
    praise_rank_message = build_rank_message(sorted_praises, "praise")

    combined_message = f"{insult_rank_message}\n\n{praise_rank_message}"
    await interaction.response.send_message(combined_message)


def build_rank_message(sorted_users, rank_type):
    rank_data = {
        "insult": {
            "title": "# Insult Rank",
            "field": "insult_mentions",
            "message": "You're going straight to hell!"
        },
        "praise": {
            "title": "# Praise Rank",
            "field": "praise_mentions",
            "message": "You're going to heaven!"
        }
    }
    
    if rank_type not in rank_data:
        return "Invalid rank type."

    rank_info = rank_data[rank_type]

    if not sorted_users:
        return f"No {rank_type} records yet."

    top_user_name, top_user_info = sorted_users[0]
    rank_message = (
        f"{rank_info['title']}:\n"
        f"Congrats! [ **{top_user_info['display_name']}** (**{top_user_info['name']}**) ] "
        f"Total {rank_type.capitalize()}: {top_user_info[rank_info['field']]} times.\n"
        f"{rank_info['message']}"
    )

    for idx, (user_name, user_info) in enumerate(sorted_users[1:4], start=2):
        rank_message += f"{idx}. {user_info['display_name']} ({user_info['name']}) - {user_info[rank_info['field']]} times\n"

    return rank_message


async def auto_handle_insult(message: discord.Message):
    user_name = message.author.name
    current_date = datetime.now().strftime('%Y-%m-%d')

    if any(keyword.lower() in message.content.lower() for keyword in TARGET_KEYWORDS):
        if any(insult in message.content for insult in INSULT_KEYWORDS):
            if user_name not in user_data:
                user_data[user_name] = {
                    'name': message.author.display_name,
                    'display_name': message.author.display_name,
                    'insult_mentions': 1,
                    'praise_mentions': 0,
                    'history_insult_mentions': 1,
                    'history_praise_mentions': 0,
                    'last_reset_date': current_date
                }
            else:
                user_data[user_name]['insult_mentions'] = user_data[user_name].get('insult_mentions', 0) + 1
                user_data[user_name]['history_insult_mentions'] = user_data[user_name].get('history_insult_mentions', 0) + 1
                user_data[user_name]['last_reset_date'] = user_data[user_name].get('last_reset_date', current_date)

            save_json(USER_DATA_FILE, user_data)

            insult_count = user_data[user_name].get('insult_mentions', 0)
            response_message = f"{message.author.display_name} ({user_data[user_name]['name']})\nTOXIC: {insult_count}"
            await message.channel.send(response_message)


async def auto_handle_praise(message: discord.Message):
    user_name = message.author.name
    current_date = datetime.now().strftime('%Y-%m-%d')

    if any(keyword.lower() in message.content.lower() for keyword in TARGET_KEYWORDS) and \
       any(praise in message.content.lower() for praise in constants.get("praise_keywords", [])):

        if user_name not in user_data:
            user_data[user_name] = {
                'name': message.author.display_name,
                'display_name': message.author.display_name,
                'insult_mentions': 0,
                'praise_mentions': 1,
                'history_insult_mentions': 0,
                'history_praise_mentions': 1,
                'last_reset_date': current_date
            }
        else:
            user_data[user_name]['display_name'] = message.author.display_name
            user_data[user_name]['praise_mentions'] = user_data[user_name].get('praise_mentions', 0) + 1
            user_data[user_name]['last_reset_date'] = user_data[user_name].get('last_reset_date', current_date)

        save_json(USER_DATA_FILE, user_data)

        praise_count = user_data[user_name].get('praise_mentions', 0)
        response_message = f"{message.author.display_name} ({user_data[user_name]['name']})\nPRAISE: {praise_count}"
        await message.channel.send(response_message)

async def auto_nlp_process(message: discord.Message, nlp_processor: ToxicMessageProcessor):
    nlp_result: ToxicDetectorResult = await nlp_processor.nlp_process(message)
    if nlp_result.score >= 0.9:
        if nlp_result.label == "Positive":
            message_type = "正面言論"
            embed_color = 0xa7c957
        else:
            message_type = "負面言論"
            embed_color = 0xbc4749

        embed = discord.Embed(title="NLP Processor",
                      description=f"你的訊息 {message.content} 被檢測為{message_type}",
                      colour=embed_color)
        embed.set_author(name="NoMoreBully")
        embed.add_field(name="Raw Data",
                value=f"{nlp_result}",
                inline=False)
        await message.channel.send(embed=embed)
