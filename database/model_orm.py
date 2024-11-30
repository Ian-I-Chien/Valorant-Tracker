from tortoise.exceptions import IntegrityError
from database.database import BaseOrm
from database.models import UserInfo


class UserOrm(BaseOrm):
    def __init__(self):
        self._model = UserInfo

    async def get_all(self):
        return await self._model.all().values()

    async def register_user(self,
                            dc_id: str,
                            dc_global_name: str,
                            dc_display_name: str,
                            val_account=None
                            ):
        try:
            await self._model.create(
                dc_id=dc_id,
                dc_global_name=dc_global_name,
                dc_display_name=dc_display_name,
                val_account=val_account
            )
        except IntegrityError:
            raise IntegrityError(f"Error!User {dc_id} already exists!If want to update, please use update_user.")

    async def get_user(self, account: str, as_dict=True):
        data = await self._model.get(account=account)
        return data.to_dict() if as_dict else data

    async def update_user(self,
                          dc_id: str,
                          dc_global_name: str = None,
                          dc_display_name: str = None,
                          keyword: str = None,
                          val_account: str = None,
                          val_puuid: str = None
                          ):
        original_data = await self._model.get(dc_id=dc_id)
        if not original_data:
            raise ValueError(f"User {dc_id} not found")
        if dc_global_name:
            original_data.dc_global_name = dc_global_name
        if dc_display_name:
            original_data.dc_display_name = dc_display_name
        if keyword:
            original_data.keyword = keyword
        if val_account:
            original_data.val_account = val_account
        if val_puuid:
            original_data.val_puuid = val_puuid
        await original_data.save()
