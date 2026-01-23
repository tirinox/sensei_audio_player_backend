import re

import MeCab
import jaconv
try:
    import pykakasi
except ImportError:
    print("Warning: pykakasi module not found. FuriganaClassic will not work.")
    pykakasi = None


def add_furigana(sentence):
    tagger = MeCab.Tagger()
    node = tagger.parseToNode(sentence)

    output = ''
    while node:
        if node.surface != '':
            surface = node.surface
            features = node.feature.split(',')
            # Get the reading (pronunciation) in katakana
            if len(features) >= 8 and features[7] != '*':
                reading = features[7]
                # Convert katakana to hiragana
                hiragana = jaconv.kata2hira(reading)
            else:
                hiragana = ''
            # Check if the surface contains kanji
            if any('\u4e00' <= char <= '\u9fff' for char in surface):
                # Add furigana
                output += f'{surface}({hiragana})'
            else:
                output += surface
        node = node.next
    return output


parentheses_to_ruby_pattern = re.compile(r'([\u4e00-\u9fff]+)\((.*?)\)')


def parentheses_to_ruby(text):
    # Regular expression pattern to match kanji followed by furigana in parentheses
    def repl(match):
        kanji = match.group(1)
        furigana = match.group(2)
        return f'<ruby>{kanji}<rt>{furigana}</rt></ruby>'

    # Substitute all occurrences in the text
    return parentheses_to_ruby_pattern.sub(repl, text)


def parentheses_to_ruby_v2(text):
    """
    Converts text in [original](translated) format to HTML ruby tags.

    Args:
        text (str): The input text containing [original](translated) patterns.

    Returns:
        str: The text with [original](translated) replaced by HTML ruby tags.
    """
    # Regular expression pattern to match [original](translated)
    pattern = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')

    # Replacement function
    def repl(match):
        original = match.group(1)
        translated = match.group(2)
        return f'<ruby>{original}<rt>{translated}</rt></ruby>'

    # Substitute all occurrences in the text
    new_text = pattern.sub(repl, text)
    return new_text



def convert_ruby_to_parenthesis(html_string):
    # Regular expression to match ruby structure
    ruby_pattern = re.compile(r'<ruby>(.*?)<rt>(.*?)</rt></ruby>')

    # Function to replace ruby tags with the desired format
    def replace_ruby(match):
        kanji = match.group(1)
        reading = match.group(2)
        return f'[{kanji}]({reading})'

    # Substitute the ruby pattern with the formatted string
    result = ruby_pattern.sub(replace_ruby, html_string)

    # Return the converted string
    return result


class FuriganaClassic:
    # Regular expression pattern to match kanji and numbers but skip katakana
    # Kanji Unicode range: \u4E00-\u9FFF
    # Numbers: ASCII 0-9 and full-width numbers \uFF10-\uFF19
    PATTERN = re.compile(r'[\u4E00-\u9FFF\uFF10-\uFF19\u0030-\u0039]+')

    def __init__(self):
        self.tagger = MeCab.Tagger()
        self.kakasi = pykakasi.kakasi()

    def add_furigana_v2(self, text):

        # Function to replace matched kanji and numbers with their readings
        def replace_match(match):
            original = match.group()
            # Use pykakasi to get the reading
            result = self.kakasi.convert(original)
            # Concatenate readings
            readings = ''.join([item['hira'] for item in result])
            # Return the formatted string
            return f'[{original}]({readings})'

        # Replace all occurrences in the text
        new_text = self.PATTERN.sub(replace_match, text)
        return new_text

    def generate_furigana(self, sentences):
        if not sentences:
            return []

        processed_sentences = [self.add_furigana_v2(sentence) for sentence in sentences]
        return processed_sentences
