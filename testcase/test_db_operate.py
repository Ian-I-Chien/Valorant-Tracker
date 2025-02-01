import pytest

from database.model_orm import UserOrm, MatchOrm, ValorantAccountOrm

#  PYTHONPATH=$(pwd) pytest -s testcase/test_db_operate.py::test_get_all_usr


@pytest.mark.asyncio
async def test_get_all_user():
    print("")
    async with UserOrm() as user_model:
        data = await user_model.get_all()
        print(f"取得所有資料:{data}")
    async with MatchOrm() as model:
        data = await model.get_all()
        print(f"取得所有資料:{data}")


@pytest.mark.asyncio
async def test_get_valorant_account():
    async with ValorantAccountOrm() as user_model:
        data = await user_model.get_valorant_accounts(val_account="yui#1121")
        print(f"取得資料:{data}")
