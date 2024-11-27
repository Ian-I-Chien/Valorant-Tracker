from dataclasses import dataclass
from transformers import pipeline
from deep_translator import GoogleTranslator

@dataclass
class ToxicDetectorResult:
    text: str
    label: str
    score: float    

class ToxicDetector:
    def __init__(self) -> None:
        self.model_name = "IDEA-CCNL/Erlangshen-Roberta-110M-Sentiment"
        self.classifier = pipeline(task="text-classification", model=self.model_name, tokenizer=self.model_name)
    
    def google_translate(self, text: str) -> str:
        return GoogleTranslator(source='auto', target='en').translate(text)
    
    def detect(self, text: str) -> ToxicDetectorResult:
        result: dict = self.classifier(text)[0]
        result_label = result.get("label", 'Positive')
        reuslt_score = result.get("score", 0)
        return ToxicDetectorResult(text=text, label=result_label, score=reuslt_score)
