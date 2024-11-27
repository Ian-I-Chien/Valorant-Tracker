import discord
from model.toxic_detector import ToxicDetector

toxic_detector: ToxicDetector = None

async def nlp_process(message: discord.Message):
    global toxic_detector
    if toxic_detector is None:
        toxic_detector = ToxicDetector()
    result = toxic_detector.detect(message.content)
    print(message.content, result)
