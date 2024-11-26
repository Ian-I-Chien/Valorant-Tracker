from tortoise import fields
from database.const import ChatType
from database.database import BaseModel


class UserInfo(BaseModel):
    class Meta:
        table = "user_info"

    account = fields.CharField(max_length=255, unique=True)
    valorant_account = fields.CharField(max_length=255, default=None, null=True)
    display_name = fields.CharField(max_length=255, null=True)
    keyword = fields.JSONField(null=True)


class ChatHistory(BaseModel):
    class Meta:
        table = "chat_history"

    send_by = fields.ForeignKeyField('models.UserInfo', related_name='sent_messages',
                                     on_delete=fields.CASCADE)
    target = fields.ForeignKeyField('models.UserInfo', related_name='received_messages',
                                    on_delete=fields.CASCADE)
    type = fields.CharEnumField(enum_type=ChatType)
    created_at = fields.DatetimeField(auto_now_add=True)


class ChatKeyword(BaseModel):
    class Meta:
        table = "chat_keyword"

    keyword = fields.CharField(max_length=255, unique=True)
    type = fields.CharEnumField(enum_type=ChatType)
