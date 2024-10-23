from openai import OpenAI
import os


class FugiranaNeural:
    def __init__(self, api_key=None):
        self.client = OpenAI(
            api_key=api_key or os.environ['VGEGPT_API_KEY'],
            base_url="https://api.vsegpt.ru/v1",
        )

        self.model = 'openai/gpt-4o-2024-08-06'
        # self.model = 'anthropic/claude-3-haiku'

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
            max_tokens=4000,
            extra_headers={"X-Title": "SenseiAudioCore"},
        )

        print("Response BIG:", response_big)
        return response_big.choices[0].message.content

    def generate_furigana(self, sentences):
        if not sentences:
            return []

        text = """
Please, add furigana to the following sentences.
For each kanji and counters in the sentence, add furigana in the following format:
[漢字](かんじ)
Do not add furigana to hiragana, katakana or any other non-kanji characters except numbers with counters.
Output must not contain anything except result text in the same number of lines as input text.
""".strip()

        text += '\n\n'
        for i, sentence in enumerate(sentences, 1):
            text += f"{i}. {sentence}\n"

        print("Requesting AI with text:", text)

        response = self._request_ai(text)

        lines = response.split('\n')
        if len(lines) != len(sentences):
            print("🛑Number of lines in response does not match number of input sentences!")

        return lines
