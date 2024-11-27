from transformers import pipeline
from deep_translator import GoogleTranslator

class ToxicDetector:
    def __init__(self) -> None:
        self.model_name = "IDEA-CCNL/Erlangshen-Roberta-110M-Sentiment"
        self.classifier = pipeline(task="text-classification", model=self.model_name, tokenizer=self.model_name)
    
    def google_translate(self, text: str) -> str:
        return GoogleTranslator(source='auto', target='en').translate(text)
    
    def detect(self, text: str):
        # text = self.google_translate(text=text)
        result: dict = self.classifier(text)[0]
        if result.get("score", 0) > 0.5:
            return True
        return False