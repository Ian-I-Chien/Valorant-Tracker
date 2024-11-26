from tortoise import fields
from tortoise.models import Model
from database.const import ChatType


class BaseModel(Model):
    class Meta:
        abstract = True

    def to_dict(self):
        return {field: getattr(self, field) for field in self._meta.fields_map if field not in ['sent_messages',
                                                                                                'received_messages']}


class UserInfo(BaseModel):
    class Meta:
        table = "user_info"

    account = fields.CharField(max_length=255, unique=True)
    volorant_account = fields.CharField(max_length=255, default=None, null=True)
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
