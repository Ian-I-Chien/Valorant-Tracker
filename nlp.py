import discord
from model.toxic_detector import ToxicDetector, ToxicDetectorResult

toxic_detector: ToxicDetector = None

async def nlp_process(message: discord.Message):
    global toxic_detector
    result: ToxicDetectorResult = toxic_detector.detect(message.content)
    print(message.content, result)

def init_nlp_model():
    """Initial NLP Model"""
    global toxic_detector
    if toxic_detector is None:
        toxic_detector = ToxicDetector()
