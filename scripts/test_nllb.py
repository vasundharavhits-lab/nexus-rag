import time
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

NAME = "facebook/nllb-200-distilled-600M"

t = time.time()
tok = AutoTokenizer.from_pretrained(NAME, src_lang="eng_Latn")
model = AutoModelForSeq2SeqLM.from_pretrained(NAME)
print("model loaded in", round(time.time() - t, 1), "seconds")

def translate(text, target):
    inputs = tok(text, return_tensors="pt")
    out = model.generate(**inputs,
                         forced_bos_token_id=tok.convert_tokens_to_ids(target),
                         max_new_tokens=200)
    return tok.decode(out[0], skip_special_tokens=True)

sentence = "The war took place in Kurukshetra."
for target in ["hin_Deva", "mar_Deva", "tam_Taml"]:
    t = time.time()
    print(target, "->", translate(sentence, target), "|", round(time.time() - t, 1), "s")