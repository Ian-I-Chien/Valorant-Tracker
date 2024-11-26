import os

from tortoise import Tortoise


def get_dp_path(server_name='default'):
    return os.path.join(os.path.dirname(__file__), f'{server_name}_no_bully.db')


async def db_init(server_name='default'):
    """
    init DB
    :param server_name: every server has its own DB
    :return:
    """
    await Tortoise.init(
        db_url=f'sqlite://{get_dp_path(server_name)}',
        modules={'models': ['database.models']}
    )
    await Tortoise.generate_schemas()


async def db_close():
    """
    Close the database connections
    """
    await Tortoise.close_connections()
