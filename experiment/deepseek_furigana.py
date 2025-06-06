import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.environ["DEEP_SEEK_API_KEY"],
    base_url="https://api.deepseek.com"
)

input_text = ("疲れたし、それに明日大阪に出張ですから。\n"
              "体の調子もあまり良くないし、それに明日大阪に出張ですから。")

# Construct the prompt
system_prompt = (
    "You are a Japanese language assistant. Your task is to annotate each kanji (and numbers with counters) "
    "with its reading in furigana using this format: [漢字](ふりがな).\n"
    "Do NOT add furigana to hiragana, katakana, Latin letters, or other non-kanji characters.\n"
    "Maintain the exact number of lines as in the input text. Return only the annotated result."
)

response = client.chat.completions.create(
    model="deepseek-chat",
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": input_text},
    ],
    stream=False
)

print(response.choices[0].message.content)
