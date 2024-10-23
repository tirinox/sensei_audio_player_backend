import re

from openai import OpenAI
import os


def process_numbered_list(text):
    # Split the input into lines
    lines = text.splitlines()

    # Remove the leading number and period from each line
    processed_lines = [re.sub(r'^\d+\.\s*', '', line) for line in lines]

    return processed_lines


class FugiranaNeural:
    def __init__(self, api_key=None):
        self.client = OpenAI(
            api_key=api_key or os.environ['VGEGPT_API_KEY'],
            base_url="https://api.vsegpt.ru/v1",
        )

        self.model = 'openai/gpt-4o-2024-08-06'
        # self.model = 'anthropic/claude-3-haiku'

    def _request_ai(self, prompt):
        # mock
        # return '1. 練習B\n2. 1\n3. [新聞](しんぶん)を[読](よ)むとき、[眼鏡](めがね)をかけます。\n4. [病院](びょういん)へ[行](い)くとき、[保険証](ほけんしょう)を[忘](わす)れないでください。\n5. [散歩](さんぽ)するときいつもカメラを[持](も)っていきます。\n6. [漢字](かんじ)がわからないときこの[辞書](じしょ)を[使](つか)います。\n7. [現金](げんきん)がないときカードで[買い物](かいもの)します。\n8. 2\n9. [出](で)かけるとき[行](い)ってまいりますと[言](い)います。\n10. [家](いえ)へ[帰](かえ)った[時](とき)、ただいまと[言](い)います。\n11. 1.\n12. [寝](ね)るときおやすみなさいと[言](い)います。\n13. [朝](あさ)[知](し)り[合](あ)いに[会](あ)った[時](とき)おはようございますと[言](い)います。\n14. ご[飯](はん)を[食](た)べた[時](とき)ごちそうさまと[言](い)います。\n15. [部長](ぶちょう)の[部屋](へや)に[入](はい)るとき[失礼](しつれい)しますと[言](い)います。\n16. 3\n17. [寂](さび)しい[時](とき)[家族](かぞく)に[電話](でんわ)をかけます。\n18. [頭](あたま)が[痛](いた)いときこの[薬](くすり)を[飲](の)みます。\n19. [暇](ひま)な[時](とき)ビデオを[見](み)ます。\n20. [妻](つま)が[病気](びょうき)の[時](とき)[会社](かいしゃ)を[休](やす)みます。\n21. [晩御飯](ばんごはん)の[時](とき)ワインを[飲](の)みます。'

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

        lines = process_numbered_list(response)

        if len(lines) != len(sentences):
            print("🛑Number of lines in response does not match number of input sentences!")

        return lines
