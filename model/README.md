# Model

This folder contains all the ML models used in our project.

## ToxicMessageProcessor
A NLP model that checks if messages are toxic or friendly. We use the [Erlangshen-Roberta-110M-Sentiment](https://huggingface.co/IDEA-CCNL/Erlangshen-Roberta-110M-Sentiment) language model.

### What it does
- Spots toxic vs friendly content in text
- Perfect for content moderation

### How to use it
```python
from model.toxic_detector import ToxicMessageProcessor, ToxicDetectorResult

# Create processor
toxic_message_processor = ToxicMessageProcessor()

# Fire up the model
toxic_message_processor.init_nlp_model()

# Check some text
result: ToxicDetectorResult = toxic_message_processor.detect("your text here")

# Used async
result: ToxicDetectorResult = await nlp_processor.nlp_process("your text here")
```

### What you get back
The model tells you:
- A labal toxic or friendly ("Positive" or "Negative")
- A score from 0 to 1 (how toxic or friendly the message is)

### Reference
- https://github.com/huggingface/transformers
- https://huggingface.co/
- https://pypi.org/project/transformers/
- https://pypi.org/project/deep-translator/
