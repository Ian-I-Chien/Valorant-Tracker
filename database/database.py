import abc
import os
from typing import Type

from tortoise import Tortoise, Model


def get_dp_path(server_name="default"):
    return os.path.join(os.path.dirname(__file__), f"{server_name}_no_bully.db")


async def db_init(server_name="default"):
    """
    init DB
    :param server_name: every server has its own DB
    :return:
    """
    await Tortoise.init(
        db_url=f"sqlite://{get_dp_path(server_name)}",
        modules={"models": ["database.models"]},
    )
    await Tortoise.generate_schemas()


async def db_close():
    """
    Close the database connections
    """
    await Tortoise.close_connections()


class BaseModel(Model):
    class Meta:
        abstract = True

    def to_dict(self):
        return {
            field: getattr(self, field)
            for field in self._meta.fields_map
            if field not in ["sent_messages", "received_messages"]
        }


@abc.abstractmethod
class BaseOrm:
    async def __aenter__(self):
        await db_init()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        await db_close()
