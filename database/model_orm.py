from tortoise.exceptions import IntegrityError
from database.database import BaseOrm
from database.models import UserInfo


class UserOrm(BaseOrm):
    def __init__(self):
        super().__init__(UserInfo)

    async def get_all(self):
        return await self._model.all().values()

    async def register_user(self, account: str, display_name: str):
        try:
            await self._model.create(
                account=account,
                display_name=display_name
            )
        except IntegrityError:
            raise IntegrityError(f"Error!User {account} already exists!If want to update, please use update_user.")

    async def get_user(self, account: str, as_dict=True):
        data = await self._model.get(account=account)
        return data.to_dict() if as_dict else data

    async def update_user(self,
                          account: str,
                          display_name: str = None,
                          keyword: list = None,
                          valorant_account: str = None):
        original_data = await self._model.get(account=account)
        if not original_data:
            raise ValueError(f"User {account} not found")
        if display_name:
            original_data.display_name = display_name
        if keyword:
            original_data.keyword = keyword
        if valorant_account:
            original_data.valorant_account = valorant_account

        await original_data.save()
