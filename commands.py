import discord
from tortoise.exceptions import IntegrityError, DoesNotExist
from database.model_orm import UserOrm, MatchOrm, ValorantAccountOrm
from valorant.match import Match
from valorant.player import ValorantPlayer
from utils import parse_player_name, get_env_or_interaction_channel
import traceback


async def handle_polling_matches(interaction: discord.Interaction = None):
    try:
        async with UserOrm() as user_model:
            users_data = await user_model.get_all()
            print(users_data)

            for user_data in users_data:
                for account_data in user_data["valorant_accounts"]:
                    try:
                        player_name, player_tag = account_data[
                            "valorant_account"
                        ].split("#")
                        valorant_puuid = account_data["valorant_puuid"]
                        dc_channel_id = user_data.get("dc_channel_id")

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
                                    return (
                                        await match.sorted_formatted_player(),
                                        dc_channel_id,
                                    )

                    except Exception as e:
                        print(
                            f"Error processing account {account_data['valorant_account']}: {e}"
                        )
                        traceback.print_exc()

    except Exception as e:
        print(f"Critical error in handle_polling_matches: {e}")
        traceback.print_exc()

    return None, None


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
    interaction: discord.Interaction, valorant_account: str
):
    player_name, player_tag = await parse_player_name(interaction, valorant_account)
    if not player_name or not player_tag:
        await interaction.edit_original_response(
            content="Failed to parse Valorant account. Format must be like `user#1234`."
        )
        return

    dc_id = str(interaction.user.id)
    dc_global_name = interaction.user.global_name
    dc_display_name = interaction.user.display_name
    dc_server_id = str(interaction.guild.id)
    dc_channel_id = str(get_env_or_interaction_channel(interaction))

    print(
        f"[DEBUG] user_id={dc_id}, global_name={dc_global_name}, display_name={dc_display_name}, server_id={dc_server_id}, channel_id={dc_channel_id}"
    )

    try:
        player = ValorantPlayer(player_name, player_tag)
        account_data = await player.get_account_by_api()
        if account_data is None:
            await interaction.edit_original_response(
                content=f"Could not fetch account: {valorant_account}"
            )
            return
    except Exception as e:
        await interaction.edit_original_response(
            content=f"Error fetching account: {str(e)}"
        )
        return

    async with UserOrm() as user_model:
        try:
            await user_model.register_user(
                dc_id=dc_id,
                dc_global_name=dc_global_name,
                dc_display_name=dc_display_name,
                dc_server_id=dc_server_id,
                dc_channel_id=dc_channel_id,
                val_account=valorant_account,
                val_puuid=str(account_data["puuid"]),
            )
            await interaction.edit_original_response(
                content=f"{dc_display_name} registered `{valorant_account}` successfully!"
            )
        except IntegrityError as e:
            await interaction.edit_original_response(
                content=f"Registration failed: {str(e)}"
            )
