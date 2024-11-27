import discord
from transformers import pipeline

async def nlp_process(message: discord.Message):
    sentiment_analysis = pipeline('sentiment-analysis', model="IDEA-CCNL/Erlangshen-Roberta-110M-Sentiment", device = 1)
    result = sentiment_analysis(message.content)
    print(message.content, result)
