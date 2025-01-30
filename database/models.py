from tortoise import fields
from database.const import ChatType
from database.database import BaseModel
from enum import Enum


class MentionTypeEnum(Enum):
    PRAISE = "PRAISE"
    INSULT = "INSULT"


class UserInfo(BaseModel):
    class Meta:
        table = "user_info"

    dc_id = fields.CharField(max_length=255)
    dc_global_name = fields.CharField(max_length=255, null=True)
    dc_display_name = fields.CharField(max_length=255, null=True)


class ValorantAccount(BaseModel):
    class Meta:
        table = "valorant_accounts"

    valorant_account = fields.CharField(max_length=255)
    valorant_puuid = fields.CharField(max_length=255, unique=True)
    dc_id = fields.ForeignKeyField(
        "models.UserInfo", related_name="valorant_accounts", on_delete=fields.CASCADE
    )


class ValorantMatch(BaseModel):
    class Meta:
        table = "valorant_matches"

    match_id = fields.CharField(max_length=255, primary_key=True)
    valorant_puuid = fields.CharField(max_length=255)
    match_data = fields.JSONField()
    match_date = fields.DatetimeField(auto_now_add=True)

    valorant_account = fields.ForeignKeyField(
        "models.ValorantAccount",
        related_name="matches",
        on_delete=fields.CASCADE,
        to_field="valorant_puuid",
    )


class NickName(BaseModel):
    class Meta:
        table = "nick_names"

    nickname_id = fields.IntField(auto_increment=True, primary_key=True)
    nickname = fields.CharField(max_length=255)
    dc_id = fields.ForeignKeyField(
        "models.UserInfo", related_name="nicknames", on_delete=fields.CASCADE
    )


class Mention(BaseModel):
    class Meta:
        table = "mentions"

    id = fields.IntField(auto_increment=True, primary_key=True)
    mention_type = fields.CharEnumField(enum_type=MentionTypeEnum)
    mention_count = fields.IntField()
    mentioned_time = fields.DatetimeField(auto_now_add=True)
    mentioned_to = fields.ForeignKeyField(
        "models.UserInfo", related_name="received_mentions", on_delete=fields.CASCADE
    )
    mentioned_by = fields.ForeignKeyField(
        "models.UserInfo", related_name="sent_mentions", on_delete=fields.CASCADE
    )


class ChatHistory(BaseModel):
    class Meta:
        table = "chat_history"

    send_by = fields.ForeignKeyField(
        "models.UserInfo", related_name="sent_messages", on_delete=fields.CASCADE
    )
    target = fields.ForeignKeyField(
        "models.UserInfo", related_name="received_messages", on_delete=fields.CASCADE
    )
    type = fields.CharEnumField(enum_type=ChatType)
    created_at = fields.DatetimeField(auto_now_add=True)
