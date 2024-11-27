from transformers import pipeline
from deep_translator import GoogleTranslator

class ToxicDetector:
    def __init__(self) -> None:
        self.model_name = "IDEA-CCNL/Erlangshen-Roberta-110M-Sentiment"
        self.classifier = pipeline(task="text-classification", model=self.model_name, tokenizer=self.model_name)
    
    def google_translate(self, text: str) -> str:
        return GoogleTranslator(source='auto', target='en').translate(text)
    
    def detect(self, text: str):
        result: dict = self.classifier(text)[0]
        result_label = result.get("label", 'Positive')
        reuslt_score = result.get("score", 0)
        if result_label == "Negative" and reuslt_score > 0.75:
            return True
        return False