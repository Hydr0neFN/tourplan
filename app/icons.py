"""24-entry avatar pool: emoji + zh/en icon-derived display names."""
POOL = [
    {"emoji": "\U0001F338", "zh": "小花", "en": "Flower"},      # 🌸 小花
    {"emoji": "\U0001F41F", "zh": "小魚", "en": "Fish"},        # 🐟 小魚
    {"emoji": "\U0001F436", "zh": "小狗", "en": "Dog"},         # 🐶 小狗
    {"emoji": "\U0001F431", "zh": "小貓", "en": "Cat"},         # 🐱 小貓
    {"emoji": "\U0001F430", "zh": "小兔", "en": "Rabbit"},      # 🐰 小兔
    {"emoji": "\U0001F98B", "zh": "小蝶", "en": "Butterfly"},   # 🦋 小蝶
    {"emoji": "\U0001F426", "zh": "小鳥", "en": "Bird"},        # 🐦 小鳥
    {"emoji": "\U0001F43B", "zh": "小熊", "en": "Bear"},        # 🐻 小熊
    {"emoji": "\U0001F437", "zh": "小豬", "en": "Pig"},         # 🐷 小豬
    {"emoji": "\U0001F438", "zh": "小蛙", "en": "Frog"},        # 🐸 小蛙
    {"emoji": "\U0001F435", "zh": "小猴", "en": "Monkey"},      # 🐵 小猴
    {"emoji": "\U0001F424", "zh": "小雞", "en": "Chick"},       # 🐤 小雞
    {"emoji": "\U0001F422", "zh": "小龜", "en": "Turtle"},      # 🐢 小龜
    {"emoji": "\U0001F41D", "zh": "小蜜蜂", "en": "Bee"},   # 🐝 小蜜蜂
    {"emoji": "\U0001F41E", "zh": "小瓢蟲", "en": "Ladybug"},  # 🐞 小瓢蟲
    {"emoji": "\U0001F981", "zh": "小獅", "en": "Lion"},        # 🦁 小獅
    {"emoji": "\U0001F42F", "zh": "小老虎", "en": "Tiger"}, # 🐯 小老虎
    {"emoji": "\U0001F418", "zh": "小象", "en": "Elephant"},    # 🐘 小象
    {"emoji": "\U0001F433", "zh": "小鯨", "en": "Whale"},       # 🐳 小鯨
    {"emoji": "\U0001F419", "zh": "小章魚", "en": "Octopus"},  # 🐙 小章魚
    {"emoji": "\U0001F427", "zh": "小企鵝", "en": "Penguin"},  # 🐧 小企鵝
    {"emoji": "\U0001F98A", "zh": "小狐狸", "en": "Fox"},   # 🦊 小狐狸
    {"emoji": "\U0001F344", "zh": "小蘑菇", "en": "Mushroom"},  # 🍄 小蘑菇
    {"emoji": "\U0001F31F", "zh": "小星", "en": "Star"},        # 🌟 小星
]


def anon_label(icon_idx: int, dup_ordinal: int, lang: str) -> str:
    """Display name for a nameless visitor: 小花, 小花2, ... / Flower, Flower2, ..."""
    base = POOL[icon_idx % len(POOL)]["zh" if lang == "zh" else "en"]
    return base if dup_ordinal <= 1 else f"{base}{dup_ordinal}"
