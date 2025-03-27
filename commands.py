import discord
from tortoise.exceptions import IntegrityError, DoesNotExist
from database.model_orm import UserOrm, MatchOrm, ValorantAccountOrm
from file_manager import load_json, save_json
from datetime import datetime
from model.toxic_detector import ToxicMessageProcessor, ToxicDetectorResult
from valorant.match import Match
from valorant.player import ValorantPlayer
from utils import parse_player_name
import traceback
from collections import deque

CONSTANTS_FILE = "config/constants.json"
USER_DATA_FILE = "data/user_data.json"

default_constants = {
    "target_keywords": ["user"],
    "insult_keywords": ["toxic"],
    "praise_keywords": ["awesome"],
    "last_reset_date": "1970-01-01",
}

default_user_data = {
    "example_user": {
        "name": "example_user",
        "display_name": "Example User",
        "insult_mentions": 0,
        "praise_mentions": 0,
        "history_insult_mentions": 0,
        "histiry_praise_mentions": 0,
        "last_reset_date": "1970-01-01",
    }
}

constants = load_json(CONSTANTS_FILE, default_constants)
TARGET_KEYWORDS = constants["target_keywords"]
INSULT_KEYWORDS = constants["insult_keywords"]
PRAISE_KEYWORDS = constants["praise_keywords"]

user_data = load_json(USER_DATA_FILE, default_user_data)


def check_and_reset_mentions():
    current_date = datetime.now().strftime("%Y-%m-%d")

    if "last_reset_date" not in constants:
        constants["last_reset_date"] = current_date
        save_json(CONSTANTS_FILE, constants)

    last_reset_date = constants["last_reset_date"]

    if current_date != last_reset_date:
        reset_daily_mentions()
        constants["last_reset_date"] = current_date
        save_json(CONSTANTS_FILE, constants)


def reset_daily_mentions():
    current_date = datetime.now().strftime("%Y-%m-%d")
    for user_name, user_info in user_data.items():
        user_info["mentions"] = 0
        user_info["last_reset_date"] = current_date
    save_json(USER_DATA_FILE, user_data)


async def handle_polling_matches(interaction: discord.Interaction = None):
    try:
        async with UserOrm() as user_model:
            users_data = await user_model.get_all()

            for user_data in users_data:
                for account_data in user_data["valorant_accounts"]:
                    try:
                        player_name, player_tag = account_data[
                            "valorant_account"
                        ].split("#")
                        valorant_puuid = account_data["valorant_puuid"]

                        match = Match(player_name, player_tag)
                        last_match_id = await match.get_last_match_id()

                        if last_match_id:
                            async with MatchOrm() as match_model:
                                match_data = await match_model.get_match_data(
                                    last_match_id, valorant_puuid
                                )

                                if match_data:
                                    print(
                                        f"Match {last_match_id} already exists for {player_name}, no need to fetch."
                                    )
                                else:
                                    print(
                                        f"Fetching new match data {last_match_id} for {player_name}..."
                                    )
                                    match_data = (
                                        await match.get_stored_match_by_id_by_api()
                                    )
                                    match.last_match_data = match_data
                                    await match_model.save_match(
                                        match_id=last_match_id,
                                        valorant_puuid=valorant_puuid,
                                        match_data=match_data,
                                    )
                                    print(
                                        f"Saved new match {last_match_id} for {account_data['valorant_account']}"
                                    )
                                    return await match.sorted_formatted_player()

                    except Exception as e:
                        print(
                            f"Error processing account {account_data['valorant_account']}: {e}"
                        )
                        traceback.print_exc()

    except Exception as e:
        print(f"Critical error in handle_polling_matches: {e}")
        traceback.print_exc()


async def whoami(interaction: discord.Interaction):
    # To handle whoami command
    return


async def handle_rank_command(interaction: discord.Interaction):
    sorted_insults = sorted(
        (
            (
                user_name,
                {
                    **user_info,
                    "display_name": user_info.get("display_name", user_info["name"]),
                },
            )
            for user_name, user_info in user_data.items()
            if user_info.get("insult_mentions", 0) > 0
        ),
        key=lambda x: x[1]["insult_mentions"],
        reverse=True,
    )

    sorted_praises = sorted(
        (
            (
                user_name,
                {
                    **user_info,
                    "display_name": user_info.get("display_name", user_info["name"]),
                },
            )
            for user_name, user_info in user_data.items()
            if user_info.get("praise_mentions", 0) > 0
        ),
        key=lambda x: x[1]["praise_mentions"],
        reverse=True,
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
            "message": "You're going straight to hell!",
        },
        "praise": {
            "title": "# Praise Rank",
            "field": "praise_mentions",
            "message": "You're going to heaven!",
        },
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
    current_date = datetime.now().strftime("%Y-%m-%d")

    if any(keyword.lower() in message.content.lower() for keyword in TARGET_KEYWORDS):
        if any(insult in message.content for insult in INSULT_KEYWORDS):
            if user_name not in user_data:
                user_data[user_name] = {
                    "name": message.author.display_name,
                    "display_name": message.author.display_name,
                    "insult_mentions": 1,
                    "praise_mentions": 0,
                    "history_insult_mentions": 1,
                    "history_praise_mentions": 0,
                    "last_reset_date": current_date,
                }
            else:
                user_data[user_name]["insult_mentions"] = (
                    user_data[user_name].get("insult_mentions", 0) + 1
                )
                user_data[user_name]["history_insult_mentions"] = (
                    user_data[user_name].get("history_insult_mentions", 0) + 1
                )
                user_data[user_name]["last_reset_date"] = user_data[user_name].get(
                    "last_reset_date", current_date
                )

            save_json(USER_DATA_FILE, user_data)

            insult_count = user_data[user_name].get("insult_mentions", 0)
            response_message = f"{message.author.display_name} ({user_data[user_name]['name']})\nTOXIC: {insult_count}"
            await message.channel.send(response_message)


async def auto_handle_praise(message: discord.Message):
    user_name = message.author.name
    current_date = datetime.now().strftime("%Y-%m-%d")

    if any(
        keyword.lower() in message.content.lower() for keyword in TARGET_KEYWORDS
    ) and any(
        praise in message.content.lower()
        for praise in constants.get("praise_keywords", [])
    ):

        if user_name not in user_data:
            user_data[user_name] = {
                "name": message.author.display_name,
                "display_name": message.author.display_name,
                "insult_mentions": 0,
                "praise_mentions": 1,
                "history_insult_mentions": 0,
                "history_praise_mentions": 1,
                "last_reset_date": current_date,
            }
        else:
            user_data[user_name]["display_name"] = message.author.display_name
            user_data[user_name]["praise_mentions"] = (
                user_data[user_name].get("praise_mentions", 0) + 1
            )
            user_data[user_name]["last_reset_date"] = user_data[user_name].get(
                "last_reset_date", current_date
            )

        save_json(USER_DATA_FILE, user_data)

        praise_count = user_data[user_name].get("praise_mentions", 0)
        response_message = f"{message.author.display_name} ({user_data[user_name]['name']})\nPRAISE: {praise_count}"
        await message.channel.send(response_message)


async def auto_nlp_process(
    message: discord.Message, nlp_processor: ToxicMessageProcessor
):
    nlp_result: ToxicDetectorResult = await nlp_processor.nlp_process(message)
    if nlp_result.score >= 0.9:
        if nlp_result.label == "Positive":
            message_type = "正面言論"
            embed_color = 0xA7C957
        else:
            message_type = "負面言論"
            embed_color = 0xBC4749

        embed = discord.Embed(
            title="NLP Processor",
            description=f"{message.author.display_name}\n你的訊息 [{message.content}] 被檢測為 **{message_type}**",
            colour=embed_color,
        )
        embed.set_author(name="NoMoreBully")
        return None
        # await message.channel.send(embed=embed)


async def delete_valorant_account(interaction: discord.Interaction, valorant_account):
    player_name, player_tag = await parse_player_name(interaction, valorant_account)
    if not player_name or not player_tag:
        await interaction.edit_original_response(
            content="Failed to parse Valorant account. Please ensure the account format is correct."
        )
        return

    valorant_account_orm = ValorantAccountOrm()
    try:
        await valorant_account_orm.remove_valorant_account(valorant_account)
        await interaction.edit_original_response(
            content=f"Valorant account {valorant_account} has been successfully removed."
        )
    except DoesNotExist:
        await interaction.edit_original_response(
            content=f"Valorant account {valorant_account} does not exist."
        )


async def registered_with_valorant_account(
    interaction: discord.Interaction, valorant_account
):

    player_name, player_tag = await parse_player_name(interaction, valorant_account)
    if not player_name or not player_tag:
        await interaction.edit_original_response(
            content="Failed to parse Valorant account. Please ensure the account format is correct."
        )

    dc_id = interaction.user.id
    dc_global_name = interaction.user.global_name
    dc_display_name = interaction.user.display_name

    try:
        player = ValorantPlayer(player_name, player_tag)
        account_data = await player.get_account_by_api()
        if account_data is None:
            await interaction.edit_original_response(
                content=f"Failed to fetch account: {valorant_account}"
            )
            return
    except IntegrityError as e:
        await interaction.edit_original_response(
            content=f"Failed to fetch account: {str(e)}"
        )
        return

    async with UserOrm() as user_model:
        try:
            await user_model.register_user(
                dc_id=dc_id,
                dc_global_name=dc_global_name,
                dc_display_name=dc_display_name,
                val_account=valorant_account,
                val_puuid=str(account_data["puuid"]),
            )
            await interaction.edit_original_response(
                content=f"{dc_display_name} Registered {valorant_account} successfully!"
            )
        except IntegrityError as e:
            await interaction.edit_original_response(
                content=f"Failed to register: {str(e)}"
            )
