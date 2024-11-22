import discord
import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")

user_data = {
    '.err': {'name': 'YUI', 'mentions': 0},
    'wenjung': {'name': '白金二戰士', 'mentions': 0},
    'mengted': {'name': '小公主', 'mentions': 0},
    'xiang__aa': {'name': '金三戰士', 'mentions': 0},
    'yuwen1018': {'name': '玉文', 'mentions': 0},
    'stupidcat1103' : {'name': '女-曾經ㄉ鑽石戰士', 'mentions': 0},

}

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f'Logged in as {client.user}')

@client.event
async def on_message(message):
    global user_data 
    if message.author == client.user:
        return
    
    if message.content == "!rank":
        if not any(user_info['mentions'] > 0 for user_info in user_data.values()):
            await message.channel.send("你們都會上天堂<3")
            return
        
        sorted_users = sorted(
            ((user_name, user_info) for user_name, user_info in user_data.items() if user_info['mentions'] > 0),
            key=lambda x: x[1]['mentions'],
            reverse=True
        )
        
        ranking_message = "今天臭修哥的排名：\n"
        
        if sorted_users:
            first_user_name, first_user_info = sorted_users[0]
            ranking_message += (
                f"恭喜臭臭人[ {first_user_info['name']} ] 總共臭了 {first_user_info['mentions']} 次！你是真會下地獄 ==\n"
                "請聯繫YUI繳交贖罪券(支援轉帳,街口,LinePay) 1000NTD 乙次\n"
            )
        
        for idx, (user_name, user_info) in enumerate(sorted_users[1:5], start=2): 
            ranking_message += f"{idx}. {user_info['name']} (ID: {user_name}) - {user_info['mentions']} 次\n"
        
        await message.channel.send(ranking_message)
        return

    user_name = message.author.name 
    
    if user_name in user_data:
        if any(mention.lower() in message.content.lower() for mention in ['修哥', '修歌', 'showmaker', '阿修', '啊修', 'maker', 'arvoice', '修修', '修老師', '修教授']):
            user_data[user_name]['mentions'] += 1
            mentions_count = user_data[user_name]['mentions']
            user_display_name = user_data[user_name]['name']

            await message.channel.send(f'{user_display_name} 今天臭修哥的次數: {mentions_count}')
    else:
        if any(mention in message.content for mention in ['修哥', '修歌', 'showmaker']):
            user_data[user_name] = {'name': user_name, 'mentions': 1}
            await message.channel.send(f'{user_name} 今天臭修哥的次數: 1')

client.run(TOKEN)
