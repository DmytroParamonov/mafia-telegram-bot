from __future__ import annotations

import random
from collections.abc import Sequence

ZONE_EVENT_CHANCE = 0.35
READY_SECONDS = 60
LAST_WORD_SECONDS = 30
BANDIT_CHAT_SECONDS = 30
ZONE_MAX_PLAYERS = 10

CALLSIGNS = (
    "Шрам",
    "Борода",
    "Хмурий",
    "Кабан",
    "Привид",
    "Ворон",
    "Сірий",
    "Моль",
    "Бункер",
    "Фантом",
    "Кремінь",
    "Грім",
    "Хорс",
    "Рись",
    "Болотник",
    "Туман",
    "Клык",
    "Сич",
    "Гайка",
    "Бродяга",
    "Барс",
    "Шукач",
    "Дим",
    "Крот",
    "Сектор",
    "Вітер",
    "Клин",
    "Стриж",
    "Яструб",
    "Пілігрим",
)

NIGHT_ZONE_EVENTS = (
    "☢️ <b>ПДА: підвищений радіаційний фон</b>\n\nДесь неподалік затріщав дозиметр. Хмара пройшла повз табір — можна рухатися далі.",
    "🌫 <b>Зону накрив густий туман</b>\n\nВидимість майже нульова. Біля багаття всі ще на місці, але за периметром краще не тинятися.",
    "📻 <b>На ПДА пішли перешкоди</b>\n\nКілька секунд у навушниках був лише тріск і чужий уривчастий голос. Сигнал відновився.",
    "🐕 <b>За периметром чути зграю</b>\n\nУ темряві загавкали сліпі пси. Вони покружляли біля табору й пішли далі.",
    "⚡ <b>Аномальна активність</b>\n\nДесь між бетонними плитами спалахнула аномалія. Сталкери перечекали — шлях знову чистий.",
    "🧠 <b>Короткий пси-імпульс</b>\n\nУ декого на мить загуло у вухах. ПДА показує: загроза минула.",
)

DAY_ZONE_EVENTS = (
    "☢️ <b>Далекий викид</b>\n\nНебо на горизонті налилося червоним, але хвиля пройшла далеко від табору. Сходка триває.",
    "🪖 <b>На околиці помітили чужий загін</b>\n\nСилуети пройшли вздовж посадки й не наблизилися. Табір лишився непоміченим.",
    "🔩 <b>ПДА зафіксував аномалію поруч</b>\n\nХтось кинув гайку — спалахнуло так, що всі одразу стали уважнішими. Ніхто не постраждав.",
    "🎒 <b>Біля табору знайшли покинутий рюкзак</b>\n\nУсередині лише бинт, порожня банка й зламаний детектор. Нічого корисного, зате підозр більше.",
    "📟 <b>Невідомий сигнал на ПДА</b>\n\nКоротке повідомлення без підпису: «Не довіряй тому, хто сидить поруч». Канал одразу зник.",
    "🔥 <b>Багаття раптом згасло</b>\n\nПорив вітру розніс іскри по бетону. Вогонь розпалили знову, а розмова стала ще нервовішою.",
)

NIGHT_DEATH_LINES = (
    "☠️ До багаття не повернувся <b>{name}</b>. Його ПДА більше не відповідає.{role_suffix}",
    "🔫 Уночі біля старих бетонних плит чули коротку чергу. <b>{name}</b> не вижив.{role_suffix}",
    "🌫 У ранковому тумані знайшли розбитий ПДА <b>{name}</b>. Самого сталкера вже не врятувати.{role_suffix}",
    "🎒 Біля периметра залишився тільки рюкзак <b>{name}</b>. Зона забрала ще одного.{role_suffix}",
    "☠️ На ранковій перекличці не відповів <b>{name}</b>. Ця ніч стала для нього останньою.{role_suffix}",
)

SAVED_TEMPLATES = (
    "🌅 <b>Світанок у Зоні</b>\n\n💉 Уночі когось намагалися прибрати, але польовий медик встиг стабілізувати пораненого. Цього разу всі дожили до ранку.",
    "🌅 <b>Світанок у Зоні</b>\n\n🩹 На землі є сліди крові, але біля багаття всі живі. Медик цієї ночі відпрацював бездоганно.",
    "🌅 <b>Світанок у Зоні</b>\n\n💉 Постріли були, жертва теж була — але медик витягнув її з того світу. Цього разу ніхто не загинув.",
)

QUIET_NIGHT_TEMPLATES = (
    "🌅 <b>Світанок у Зоні</b>\n\nТиха ніч — рідкісна розкіш. На ранковій перекличці всі на місці.",
    "🌅 <b>Світанок у Зоні</b>\n\nЛише вітер ганяв пил між плитами. Цієї ночі ніхто не загинув.",
    "🌅 <b>Світанок у Зоні</b>\n\nПДА мовчали до самого ранку. Усі, хто засинав біля багаття, прокинулися живими.",
)


def callsigns_for(game_id: int, user_ids: Sequence[int]) -> dict[int, str]:
    callsigns = list(CALLSIGNS)
    random.Random(game_id * 7919 + len(user_ids)).shuffle(callsigns)
    return {user_id: callsigns[index] for index, user_id in enumerate(user_ids)}


def choose_zone_event(phase: str, *, rng: random.Random | None = None, chance: float = ZONE_EVENT_CHANCE) -> str | None:
    source = rng or random.SystemRandom()
    if source.random() >= chance:
        return None
    events: Sequence[str] = NIGHT_ZONE_EVENTS if phase == "night" else DAY_ZONE_EVENTS
    return source.choice(events)


def night_death_line(name: str, role_suffix: str = "", *, rng: random.Random | None = None) -> str:
    source = rng or random.SystemRandom()
    return source.choice(NIGHT_DEATH_LINES).format(name=name, role_suffix=role_suffix)


def night_death_text(name: str, role_suffix: str = "", *, rng: random.Random | None = None) -> str:
    return "🌅 <b>Світанок у Зоні</b>\n\n" + night_death_line(name, role_suffix, rng=rng)


def saved_text(*, rng: random.Random | None = None) -> str:
    return (rng or random.SystemRandom()).choice(SAVED_TEMPLATES)


def quiet_night_text(*, rng: random.Random | None = None) -> str:
    return (rng or random.SystemRandom()).choice(QUIET_NIGHT_TEMPLATES)
