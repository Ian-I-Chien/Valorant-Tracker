import discord
from util.ToxicDetector import ToxicDetector

toxic_detector: ToxicDetector = None

async def nlp_process(message: discord.Message):
    if toxic_detector is None:
        toxic_detector = ToxicDetector()
    result = toxic_detector.detect(message.content)
    print(message.content, result)