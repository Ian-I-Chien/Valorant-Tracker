from tortoise.exceptions import IntegrityError
from database.database import BaseOrm
from database.models import UserInfo, ValorantAccount, ValorantMatch
from tortoise.transactions import atomic
from tortoise.exceptions import DoesNotExist


class UserOrm(BaseOrm):
    def __init__(self):
        self._model = UserInfo
        self._val_account_orm = ValorantAccountOrm()

    async def get_all(self):
        users = await self._model.all().prefetch_related("valorant_accounts")
        result = []
        for user in users:
            user_data = {
                "id": user.id,
                "dc_id": user.dc_id,
                "dc_global_name": user.dc_global_name,
                "dc_display_name": user.dc_display_name,
                "valorant_accounts": [
                    {
                        "id": account.id,
                        "valorant_account": account.valorant_account,
                        "valorant_puuid": account.valorant_puuid,
                    }
                    for account in user.valorant_accounts
                ],
            }
            result.append(user_data)
        return result

    @atomic()
    async def register_user(
        self,
        dc_id: str,
        dc_global_name: str,
        dc_display_name: str,
        val_account=None,
        val_puuid=None,
    ):
        try:
            user = await self._model.create(
                dc_id=dc_id,
                dc_global_name=dc_global_name,
                dc_display_name=dc_display_name,
            )
            if val_account and val_puuid:
                await self._val_account_orm.register_valorant_account(
                    dc_id, val_account, val_puuid
                )
        except IntegrityError as e:
            raise IntegrityError(f"{str(e)}")

    async def get_user(self, account: str, as_dict=True):
        data = await self._model.get(dc_id=account)
        return data.to_dict() if as_dict else data

    async def update_user(
        self,
        dc_id: str,
        dc_global_name: str = None,
        dc_display_name: str = None,
    ):
        original_data = await self._model.get(dc_id=dc_id)
        if not original_data:
            raise ValueError(f"User {dc_id} not found")
        if dc_global_name:
            original_data.dc_global_name = dc_global_name
        if dc_display_name:
            original_data.dc_display_name = dc_display_name
        await original_data.save()


class ValorantAccountOrm(BaseOrm):
    def __init__(self):
        self._model = ValorantAccount

    @atomic()
    async def register_valorant_account(
        self, dc_id: str, valorant_account: str, valorant_puuid: str
    ):
        user_info = await UserInfo.filter(dc_id=dc_id).first()
        if not user_info:
            raise IntegrityError(f"User with dc_id {dc_id} does not exist!")

        existing_entry = await self._model.filter(valorant_puuid=valorant_puuid).first()

        if existing_entry:
            existing_entry.valorant_account = valorant_account
            await existing_entry.save()
            print(
                f"Account updated: {existing_entry.valorant_account} changed to {valorant_account}"
            )
        else:
            await self._model.create(
                valorant_account=valorant_account,
                valorant_puuid=valorant_puuid,
                dc_id=user_info,
            )

    async def get_valorant_accounts(self, val_account: str):
        return await self._model.filter(valorant_account__iexact=val_account).all()

    async def check_if_puuid_exist(self, valorant_puuid: str) -> bool:
        existing_entry = await self._model.filter(valorant_puuid=valorant_puuid).first()
        return existing_entry is not None

    @atomic()
    async def remove_valorant_account(self, valorant_account: str):
        account = await self._model.filter(valorant_account=valorant_account).first()
        if not account:
            raise DoesNotExist(f"Valorant account {valorant_account} does not exist.")
        await account.delete()
        print(f"Valorant account {valorant_account} removed successfully.")


class MatchOrm(BaseOrm):
    def __init__(self):
        self._model = ValorantMatch

    async def match_exists(self, match_id: str):
        return await self._model.filter(match_id=match_id).first()

    async def get_match_data(self, match_id: str, valorant_puuid: str):
        match = await self.match_exists(match_id)

        if match:
            existing_match = await self._model.filter(
                match_id=match_id, valorant_puuid=valorant_puuid
            ).first()

            if existing_match:
                return existing_match.match_data

            print(
                f"Match data does not exist for {valorant_puuid}, storing new data..."
            )
            match_data = match.match_data
            saved_match_data = await self.save_match(
                match_id, valorant_puuid, match_data
            )
            if saved_match_data:
                return saved_match_data

        return None

    async def save_match(self, match_id: str, valorant_puuid: str, match_data: dict):
        try:
            valorant_account = await ValorantAccount.get(valorant_puuid=valorant_puuid)

            created_match = await self._model.create(
                match_id=match_id,
                valorant_puuid=valorant_puuid,
                match_data=match_data,
                valorant_account=valorant_account,
            )
            return created_match.match_data

        except DoesNotExist:
            print(f"Valorant account with puuid {valorant_puuid} does not exist.")
            return None

    async def get_all(self):
        matches = await self._model.all().prefetch_related("valorant_account")
        result = []
        for match in matches:
            match_data = {
                "match_id": match.match_id,
                "valorant_puuid": match.valorant_puuid,
                "match_data": match.match_data,
                "match_date": match.match_date,
                "valorant_account": {
                    "valorant_account": match.valorant_account.valorant_account,
                    "valorant_puuid": match.valorant_account.valorant_puuid,
                },
            }
            result.append(match_data)
        return result
