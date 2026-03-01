import os
import re

from openai import OpenAI

PROMPT_1 = """
You are a Japanese text processor.

Task:
Add furigana to ALL kanji in the input text.

Rules:

1. For each kanji character or kanji compound, wrap it using this exact format:
   [漢字](かんじ)

2. If a number is written using Arabic numerals and followed by a counter,
   wrap both number and counter together:
   Example:
   3人 → [3人](さんにん)

3. Do NOT add furigana to:
   - hiragana
   - katakana
   - punctuation
   - particles
   - words normally written only in kana

4. Do NOT:
   - change wording
   - paraphrase
   - replace kana words with kanji
   - add explanations
   - add extra spaces
   - add empty lines

5. Output must:
   - contain exactly the same number of lines as input
   - contain ONLY the processed text

Example:

Input:
今日は3人で学校へ行きます。

Output:
[今日](きょう)は[3人](さんにん)で[学校](がっこう)へ[行](い)きます。
"""

def process_numbered_list(text):
    # Split the input into lines
    lines = text.splitlines()

    # Remove the leading number and period from each line
    processed_lines = [re.sub(r'^\d+\.\s*', '', line) for line in lines]

    return processed_lines


class FuriganaNeural:
    def __init__(self, api_url, api_key, model, prompt=PROMPT_1):
        self.client = OpenAI(
            api_key=api_key,
            base_url=api_url,
        )
        self.model = model
        self.prompt = prompt.strip()

    def _request_ai(self, prompt):
        messages = [
            {"role": "user", "content": prompt}
        ]
        # messages.append({"role": "system", "content": system_text})

        response_big = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.7,
            n=1,
            max_tokens=5000,
            extra_headers={"X-Title": "SenseiAudioCore"},
        )

        print("Response BIG:", response_big)
        return response_big.choices[0].message.content

    def generate_furigana(self, sentences):
        if not sentences:
            return []

        text = self.prompt
        text += '\n\n'
        for i, sentence in enumerate(sentences, 1):
            text += f"{i}. {sentence}\n"

        print("Requesting AI with text:", text)

        response = self._request_ai(text)

        lines = process_numbered_list(response)

        if len(lines) != len(sentences):
            print("🛑Number of lines in response does not match number of input sentences!")

        return lines

    @classmethod
    def from_env(cls):
        api_url = os.environ.get("AI_API_URL", "https://api.deepseek.com")
        api_key = os.environ.get("AI_API_KEY")
        model = os.environ.get("AI_API_MODEL", "deepseek-chat")

        if not api_key:
            raise ValueError("API key for DeepSeek is not set in environment variables.")

        return cls(api_url, api_key, model)
