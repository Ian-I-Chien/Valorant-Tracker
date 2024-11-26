import pytest

from database.model_orm import UserOrm


@pytest.mark.asyncio
async def test_register_user():
    print('')
    test_userinfo = {'account': 'test', 'display_name': '測試帳號'}
    async with UserOrm() as user_model:
        try:
            await user_model.register_user(**test_userinfo)
        except Exception as e:
            print(e)
        data = await user_model.get_all()
        print(f'取得資料:{data}')


@pytest.mark.asyncio
async def test_get_all_user():
    print('')
    async with UserOrm() as user_model:
        data = await user_model.get_all()
        print(f'取得所有資料:{data}')


@pytest.mark.asyncio
async def test_get_user():
    print('')
    async with UserOrm() as user_model:
        data = await user_model.get_user(account='test')
        print(f'取得資料:{data}')


@pytest.mark.asyncio
async def test_update_user():
    print('')
    update_account = 'test'
    to_update_info = {'display_name': '測試帳號', 'valorant_account': '冷酷槍男#1234', 'keyword': ['測試人', '測試']}
    async with UserOrm() as user_model:
        await user_model.update_user(account=update_account, **to_update_info)
        data = await user_model.get_all()
        print(f'取得資料:{data}')
