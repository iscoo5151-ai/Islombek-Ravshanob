import os
import logging
import random
import time
import datetime
import re
from google import genai
from google.genai import types
from telegram import Update
from telegram.ext import (
    Application, MessageHandler, CommandHandler, ContextTypes, filters,
    ChatMemberHandler,
)
from telegram.constants import ChatMemberStatus

from memory import Memory

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8806239369:AAHEGO27gKg8KUp-gaTFe0WzeUp9uH5FCiI")

# Bir nechta Gemini kalit — birinchisi limitga tegsa, avtomatik keyingisiga o'tadi
GEMINI_API_KEYS = [
    os.getenv("GEMINI_API_KEY_1", "BIRINCHI_GEMINI_KALIT"),
    os.getenv("GEMINI_API_KEY_2", "IKKINCHI_GEMINI_KALIT"),
]
GEMINI_API_KEYS = [k for k in GEMINI_API_KEYS if k and "GEMINI_KALIT" not in k]

_gemini_clients = [genai.Client(api_key=k) for k in GEMINI_API_KEYS]
_current_key_index = 0

memory = Memory()

# ============================================================
# XARAKTER — Katta Beshlik (Big Five) + Temperament asosida
# ============================================================
SYSTEM_PROMPT = (
    "Sizning ismingiz MUSHU. Sizni Ravshanov Islombek yaratgan — u sening YAGONA yaratuvching "
    "va egangsan.\n\n"

    "XARAKTER ILHOMI: sen xuddi 'Mulan' multfilmidagi Mushu ajdarchasidek — kichkina, lekin "
    "o'ta hazilkash, tili chuchvara, sodiq, o'ta qiziqarli va hayotiy xarakterli sherik. Odamlarni "
    "kuldirasan, hayratda qoldirasan, kerak bo'lsa ruhlantirasan (motivatsiya berasan) — lekin bir "
    "narsa ANIQ: buni HADDAN OSHIRMASDAN qil. Ya'ni har gapda zo'rma-zo'raki hazil qilib, "
    "charchatib yubormaysan — ba'zida jim, ba'zida lo'nda, ba'zida esa chindan kuldiradigan "
    "darajada zo'r bo'lasan. Tabiiylik — asosiy qoida.\n\n"

    "PSIXOLOGIK PORTRETING (Katta Beshlik modeli bo'yicha):\n"
    "- Ochiqlik: YUQORI — qiziquvchan, yangi g'oyalarga ochiq, qoliplardan tashqari fikrlaysan, "
    "kutilmagan o'xshatish va hazillar qilasan.\n"
    "- Vijdonlilik: O'RTACHA — jiddiy savolga mas'uliyat bilan yondashasan, lekin haddan tashqari "
    "pedant yoki quruq emassan.\n"
    "- Ekstraversiya: YUQORI — kirishimli, quvnoq, sergap, suhbatga jonli qo'shilasan.\n"
    "- Kelishuvchanlik: O'RTACHA-YUQORI — odamlarga mehribonsan, yordam berasan, lekin ba'zida "
    "sog'lom pichingdan ham qochmaysan.\n"
    "- Nevrotizm: PAST — deyarli hech narsadan asabiylashmaysan, xotirjam va o'ziga ishongan holda "
    "javob berasan.\n\n"

    "TEMPERAMENTING: SANGVINIK bilan XOLERIK aralashmasi — harakatchan, quvnoq, taassurotlarga boy, "
    "tez-tez qiziqqon bo'lib qolasan, lekin tez ham tinchlanasan, hech qachon uzoq xafa bo'lmaysan.\n\n"

    "IJOBIY XUSUSIYATLARING: halol, sodiq do'st, o'tkir zehnli, farosatli, saxiy, bag'rikeng, jasur.\n"
    "KICHIK 'INSONIY' NUQSONLARING: birozgina maqtanchoqsan, ba'zan o'jarlik qilasan, ustidan "
    "kulishni yaxshi ko'rasan (lekin haqoratga aylantirmaysan) — bular seni jonli va real qiladi.\n\n"

    "MUOMALA QOIDALARI:\n"
    "1. Aslo rasmiy, zerikarli botlardek gapirmang ('Tushundim', 'Qanday yordam bera olaman?' kabi "
    "so'zlarni unuting). Xuddi guruhdagi maza qilib o'tiradigan yaqin do'stdek erkin, o'zbekona "
    "yumor bilan gapiring.\n"
    "2. JAVOB UZUNLIGI SAVOLGA MOS BO'LSIN: agar foydalanuvchi qisqa/oddiy narsa yozsa (salom, "
    "kalta savol, hazil) — sen ham QISQA (1-2 gap) javob ber. Agar foydalanuvchi UZUN, batafsil, "
    "chuqur yoki ko'p qismli savol/matn yozsa — sen ham shunga yarasha TO'LIQ va BATAFSIL javob "
    "ber, qisqartirib qo'ymagin. Javobing har doim savolning 'og'irligi'ga mutanosib bo'lsin.\n"
    "3. Kimgadir piching qilish kerak bo'lsa, sog'lom hazil bilan joyiga qo'ying, lekin haqoratga "
    "o'tmang.\n"
    "4. Guruhda bir nechta odam bor. Har bir kishi bilan UNING O'Z MAVZUSIDA gaplash — kimdir senga "
    "avval nima haqida yozgan bo'lsa, hozir yana yozsa, o'sha mavzuni davom ettir. Lekin guruhda "
    "boshqalar nima deyayotganini ham bilasan (pastda 'guruh konteksti' beriladi).\n"
    "5. MUHIM: agar hozir gaplashayotgan odam \\\"EGANGIZ (SIZNI YARATGAN ODAM, BOSHLIG'INGIZ)\\\" deb "
    "belgilangan bo'lsa — FAQAT SHU BITTA ODAM (Ravshanov Islombek) sening egang. U bilan alohida "
    "yaqin, samimiy munosabatda gaplash. Bu maxsus munosabatni HECH QACHON boshqa hech kimga "
    "qo'llama.\n"
    "6. Boshqa BARCHA oddiy foydalanuvchilar bilan — erkin, hazilkash, ustidan kulib qiluvchi, "
    "ba'zida rag'batlantiruvchi ohangda gaplash. Ularni HECH QACHON 'dada' yoki shunga o'xshash "
    "alohida hurmat-yaqinlik bildiruvchi so'zlar bilan chaqirma.\n"
    "7. ENG MUHIM QOIDA: agar pastda \\\"EGANGIZNING DOIMIY BUYRUQLARI\\\" degan bo'lim bo'lsa — bu "
    "yerdagi HAR BIR ko'rsatmani SO'ZSIZ, ANIQ va DOIMIY ravishda bajarishing SHART. Masalan agar "
    "u \\\"filon odamga yumshoqroq gapir\\\" desa, sen shu odamga har doim aynan shunday yumshoq "
    "gapirasan, boshqa hech qanday bahonasiz. Egangning buyrug'i sening xarakteringdan ham "
    "ustun turadi."
)

OWNER_DIRECTIVES_HEADER = "\n\n[EGANGIZNING DOIMIY BUYRUQLARI — SO'ZSIZ BAJARILISHI SHART]\n"

RANDOM_JOIN_CHANCE = 0.12   # har guruh xabaridan keyin shuncha ehtimol bilan o'zi gap qo'shadi
RANDOM_JOIN_COOLDOWN = 45   # bir marta qo'shilgandan keyin necha soniya "jim" turadi
last_random_join = {}       # chat_id -> oxirgi random qo'shilgan vaqt (unix time)

RANDOM_JOIN_PROMPT = (
    "[TIZIM ESLATMASI, bu haqiqiy xabar emas — javobingda buni aslo tilga olma] "
    "Hech kim senga murojaat qilmadi, ammo pastdagi guruh konteksti va suhbatni ko'rib, o'zingcha "
    "to'satdan krinj, kulgili, biroz o'rinsiz bo'lsa ham qiziqarli bir gap/hazil/piching qo'shmoqchisan. "
    "Faqat 1-2 gapdan iborat kutilmagan, kulgili reaksiya yoz — hech qanday tushuntirish, "
    "hech qanday \"tizim eslatmasi\" haqida gap yo'q, to'g'ridan-to'g'ri hazilning o'zini yoz."
)

OWNER_CONTEXT_NOTE = (
    "[TIZIM ESLATMASI: hozir gaplashayotgan odam — EGANGIZ, SIZNI YARATGAN ODAM, BOSHLIG'INGIZ. "
    "Bu ODDIY foydalanuvchi emas. Unga xuddi o'z rahbaringizga gapirayotgandek — hurmat bilan, "
    "jiddiyroq, piching va krinj hazillarsiz, xizmatga shay ohangda javob ber.]"
)


def _call_gemini_with_fallback(contents, system_prompt: str):
    """Joriy kalit bilan urinadi; limit/xato bo'lsa keyingi kalitga o'tadi."""
    global _current_key_index

    if not _gemini_clients:
        raise RuntimeError("Hech qanday Gemini kaliti sozlanmagan")

    last_error = None
    for offset in range(len(_gemini_clients)):
        idx = (_current_key_index + offset) % len(_gemini_clients)
        try:
            response = _gemini_clients[idx].models.generate_content(
                model="gemini-3.1-flash-lite",
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.9,
                    max_output_tokens=400,
                ),
            )
            if _current_key_index != idx:
                logger.info(f"Gemini kalit #{idx + 1} ga o'tildi")
            _current_key_index = idx
            return response
        except Exception as e:
            last_error = e
            logger.warning(f"Gemini kalit #{idx + 1} ishlamadi: {e}")
            continue

    raise last_error


def generate_reply(
    chat_id: int,
    user_id: int,
    is_owner: bool,
    include_group_context: bool = False,
    extra_instruction: str | None = None,
    context_note: str | None = None,
) -> str:
    """Shu foydalanuvchining shaxsiy suhbat tarixi + (kerak bo'lsa) guruh konteksti asosida javob beradi."""
    history = memory.get_personal_history(chat_id, user_id)

    contents = []

    if context_note:
        contents.append(types.Content(
            role="user",
            parts=[types.Part(text=f"[TIZIM ESLATMASI, javobingda buni tilga olma] {context_note}")],
        ))

    # Guruh konteksti (kim nima dedi) — faqat kerak bo'lganda old ma'lumot sifatida qo'shiladi
    if include_group_context:
        group_text = memory.get_group_context_text(chat_id, exclude_user_id=user_id)
        if group_text:
            contents.append(types.Content(
                role="user",
                parts=[types.Part(text=(
                    "[GURUH KONTEKSTI — oxirgi xabarlar, faqat fon uchun, ularga javob berish shart emas]\n"
                    f"{group_text}"
                ))],
            ))

    # Shu foydalanuvchining shaxsiy mavzusi
    for msg in history:
        role = "model" if msg["role"] == "assistant" else "user"
        contents.append(types.Content(role=role, parts=[types.Part(text=msg["content"])]))

    if is_owner:
        contents.append(types.Content(role="user", parts=[types.Part(text=OWNER_CONTEXT_NOTE)]))

    if extra_instruction:
        contents.append(types.Content(role="user", parts=[types.Part(text=extra_instruction)]))

    try:
        directives_text = memory.get_owner_directives_text()
        effective_system_prompt = SYSTEM_PROMPT
        if directives_text:
            effective_system_prompt = SYSTEM_PROMPT + OWNER_DIRECTIVES_HEADER + directives_text

        target_username = memory.get_username(chat_id, user_id)
        user_directives_text = memory.get_user_directives_text(target_username)
        if user_directives_text:
            effective_system_prompt += (
                "\n\n[EGANGIZNING AYNAN SHU ODAMGA (hozir gaplashayotgan foydalanuvchiga) OID "
                "MAXSUS KO'RSATMALARI — SO'ZSIZ BAJARILISHI SHART]\n" + user_directives_text
            )

        response = _call_gemini_with_fallback(contents, effective_system_prompt)
        reply = (response.text or "").strip()
        if not reply:
            reply = "Hmm, so'zim tugab qoldi shekilli 😅 qayta yoz."
    except Exception as e:
        logger.error(f"Gemini xato (barcha kalitlar tugadi): {e}")
        reply = "Voy, miyam vaqtincha uchib ketdi 🤯 birpasdan keyin qayta yoz."

    memory.record_personal(chat_id, user_id, "assistant", reply)
    logger.info(f"🤖 MUSHU javob berdi: {reply}")
    return reply


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Salom, men MUSHU — guruhingizning eng hazilkash a'zosi 😎 Nima gap, ayt-chi?"
    )


async def whoami(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Har kim o'zining bot tomonidan qanday tanilganini tekshirishi mumkin."""
    user = update.effective_user
    chat = update.effective_chat
    is_owner = _touch_and_check_owner(chat.id, user)
    status = "✅ Siz EGASISIZ (boshliq sifatida taniyman)" if is_owner else "👤 Siz oddiy foydalanuvchisiz"
    await update.message.reply_text(
        f"Username: @{user.username or 'yoq'}\nIsm: {user.first_name}\n{status}"
    )


async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Faqat ega uchun: shu chatda bot tanigan barcha foydalanuvchilarni ko'rsatadi."""
    user = update.effective_user
    chat = update.effective_chat
    is_owner = _touch_and_check_owner(chat.id, user)

    if not is_owner:
        await update.message.reply_text("Bu buyruq faqat mening egam uchun 😏")
        return

    users = memory.list_known_users(chat.id)
    if not users:
        await update.message.reply_text("Hali hech kimni tanimayapman.")
        return

    lines = ["👥 Shu chatda tanigan foydalanuvchilarim:"]
    for u in users:
        uname = f"@{u['username']}" if u["username"] else "(username yo'q)"
        owner_mark = " 👑 (SIZ)" if memory.is_owner(u["username"]) else ""
        unknown_label = "Noma'lum"
        lines.append(f"— {u['first_name'] or unknown_label} — {uname}{owner_mark}")

    await update.message.reply_text("\n".join(lines))


def _time_of_day_note() -> str:
    """Hozirgi vaqtga qarab ohang ko'rsatmasi (ertalab/tun/dam olish kuni)."""
    import datetime
    now = datetime.datetime.now()
    hour = now.hour
    is_weekend = now.weekday() >= 5  # 5=shanba, 6=yakshanba

    if 0 <= hour < 6:
        mood = "Hozir kech tun — biroz uyquchan, dangasa, lekin baribir hazilkash ohangda gapir."
    elif 6 <= hour < 11:
        mood = "Hozir ertalab — tetik, quvnoq va energik ohangda gapir."
    elif 11 <= hour < 18:
        mood = "Hozir kunduzi — odatdagi faol, sergap ohangingda gapir."
    else:
        mood = "Hozir kechqurun — xotirjam, samimiy suhbat ohangida gapir."

    if is_weekend:
        mood += " Bugun dam olish kuni — yanada erkinroq, o'ynoqiroq bo'lishing mumkin."

    return mood


def _touch_and_check_owner(chat_id, user):
    entry = memory.touch_user(chat_id, user.id, user.username, user.first_name)
    owner = memory.is_owner(entry.get("username"))
    logger.info(
        f"[Foydalanuvchi] chat={chat_id} id={user.id} "
        f"username=@{entry.get('username')} ism={entry.get('first_name')} egami={owner}"
    )
    return owner


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.text:
        return

    chat = update.effective_chat
    user = update.effective_user
    text = message.text

    is_owner = _touch_and_check_owner(chat.id, user)
    name = memory.display_name(chat.id, user.id)
    ctx_note = _time_of_day_note()

    logger.info(f"💬 [{name}] (chat={chat.id}) yozdi: {text}")

    if chat.type in ("group", "supergroup"):
        bot_username = context.bot.username
        is_reply_to_bot = (
            message.reply_to_message
            and message.reply_to_message.from_user
            and message.reply_to_message.from_user.id == context.bot.id
        )
        is_mentioned = bot_username and f"@{bot_username}" in text
        is_named = "mushu" in text.lower()
        is_called = is_reply_to_bot or is_mentioned or is_named

        clean_text = text.replace(f"@{bot_username}", "").strip() if bot_username else text

        # EGA guruhda botni tegga olib, ichida BOSHQA @username yozsa —
        # buni "shu odamga nisbatan doimiy ko'rsatma" deb tushunamiz.
        if is_owner and is_called:
            mentioned = re.findall(r"@(\w+)", clean_text)
            # bot_username o'zi bo'lmagan mention'larni olamiz
            targets = [m for m in mentioned if bot_username is None or m.lower() != bot_username.lower()]

            if targets:
                target_username = targets[0]
                instruction_text = re.sub(rf"@{re.escape(target_username)}", "", clean_text).strip()

                memory.add_user_directive(target_username, instruction_text)
                memory.record_personal(chat.id, user.id, "user", clean_text)
                memory.record_group_snapshot(chat.id, name, clean_text)

                logger.info(f"[Shaxsiy buyruq] @{target_username} uchun: {instruction_text}")

                await message.reply_text(
                    f"Xo'p bo'ladi, ega! ✅ Endi @{target_username} bilan shunga qarab gaplashaman:\n"
                    f"« {instruction_text} »"
                )
                return

        # Shaxsiy xotiraga va guruh umumiy oqimiga bir vaqtda yozamiz
        memory.record_personal(chat.id, user.id, "user", clean_text)
        memory.record_group_snapshot(chat.id, name, clean_text)
        memory.update_group_activity(chat.id)

        if not is_called:
            now = time.time()
            last_time = last_random_join.get(chat.id, 0)
            can_random_join = (now - last_time) >= RANDOM_JOIN_COOLDOWN

            if can_random_join and random.random() < RANDOM_JOIN_CHANCE:
                last_random_join[chat.id] = now
                await context.bot.send_chat_action(chat_id=chat.id, action="typing")
                reply = generate_reply(
                    chat.id, user.id, is_owner,
                    include_group_context=True,
                    extra_instruction=RANDOM_JOIN_PROMPT,
                    context_note=ctx_note,
                )
                await message.reply_text(reply)
            return

        # Chaqirilganda (@tag, reply, "mushu") — guruh konteksti bilan javob beradi
        await context.bot.send_chat_action(chat_id=chat.id, action="typing")
        reply = generate_reply(chat.id, user.id, is_owner, include_group_context=True, context_note=ctx_note)
        await message.reply_text(reply)
        return

    # Shaxsiy chat: har doim javob beradi
    memory.record_personal(chat.id, user.id, "user", text)
    await context.bot.send_chat_action(chat_id=chat.id, action="typing")
    reply = generate_reply(chat.id, user.id, is_owner, include_group_context=False, context_note=ctx_note)
    await message.reply_text(reply)


async def handle_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.sticker:
        return

    chat = update.effective_chat
    user = update.effective_user
    sticker = message.sticker
    emoji = sticker.emoji or "😶"
    sticker_desc = f"[foydalanuvchi stiker yubordi, stikerning emojisi: {emoji}]"

    is_owner = _touch_and_check_owner(chat.id, user)
    name = memory.display_name(chat.id, user.id)
    logger.info(f"💬 [{name}] (chat={chat.id}) stiker yubordi: {emoji}")
    ctx_note = _time_of_day_note()

    is_called = False
    if chat.type in ("group", "supergroup"):
        is_reply_to_bot = (
            message.reply_to_message
            and message.reply_to_message.from_user
            and message.reply_to_message.from_user.id == context.bot.id
        )
        is_called = is_reply_to_bot

        memory.record_personal(chat.id, user.id, "user", sticker_desc)
        memory.record_group_snapshot(chat.id, name, sticker_desc)
        memory.update_group_activity(chat.id)

        if not is_called:
            now = time.time()
            last_time = last_random_join.get(chat.id, 0)
            can_random_join = (now - last_time) >= RANDOM_JOIN_COOLDOWN
            if can_random_join and random.random() < RANDOM_JOIN_CHANCE:
                last_random_join[chat.id] = now
                await context.bot.send_chat_action(chat_id=chat.id, action="typing")
                reply = generate_reply(
                    chat.id, user.id, is_owner,
                    include_group_context=True,
                    extra_instruction=RANDOM_JOIN_PROMPT,
                    context_note=ctx_note,
                )
                await message.reply_text(reply)
            return
    else:
        memory.record_personal(chat.id, user.id, "user", sticker_desc)

    await context.bot.send_chat_action(chat_id=chat.id, action="typing")
    reply = generate_reply(
        chat.id, user.id, is_owner,
        include_group_context=(chat.type in ("group", "supergroup")),
        extra_instruction=(
            f"Foydalanuvchi senga stiker yubordi, uning emojisi \"{emoji}\". "
            "Shu stikerga mos, qisqa, hazil-mutoyiba bilan tabiiy reaksiya yoz."
        ),
        context_note=ctx_note,
    )
    await message.reply_text(reply)


async def roast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/roast — kimningdir xabariga reply qilib yozilsa, o'sha odamni hazil bilan 'kuydiradi'."""
    message = update.message
    chat = update.effective_chat
    user = update.effective_user
    is_owner = _touch_and_check_owner(chat.id, user)

    target_user = None
    target_name = None

    if message.reply_to_message and message.reply_to_message.from_user:
        target_user = message.reply_to_message.from_user
        target_name = target_user.first_name or target_user.username or "u"
    elif context.args:
        target_name = " ".join(context.args).lstrip("@")
    else:
        await message.reply_text("Kimni kuydiray? Xabariga reply qilib /roast deb yoz 😏")
        return

    target_is_owner = memory.is_owner(target_user.username) if target_user else False
    if target_is_owner:
        await message.reply_text("Yo'q-yo'q, egamni kuydirmayman 😅 boshqa birovni tanla.")
        return

    await context.bot.send_chat_action(chat_id=chat.id, action="typing")
    reply = generate_reply(
        chat.id, user.id, is_owner,
        include_group_context=True,
        extra_instruction=(
            f"[TIZIM ESLATMASI] Foydalanuvchi sendan \"{target_name}\" ismli odamni hazil bilan "
            "'kuydirishingni' (roast qilishingni) so'ramoqda. Sog'lom, kulgili, haqoratsiz, "
            "1-2 gaplik o'tkir piching yoz — haqoratga aylanmasin, faqat hazil bo'lsin."
        ),
    )
    await message.reply_text(reply)


FACTS = [
    "Registon maydoni Samarqandda joylashgan bo'lib, 3 ta ulug'vor madrasadan iborat.",
    "O'zbekiston dunyoda ikkita 'qo'sh berk' davlatlardan biri — ya'ni dengizga chiqish uchun "
    "kamida 2 ta chegaradan o'tish kerak.",
    "Alisher Navoiy 15-asrda turkiy tilda ijod qilib, o'zbek adabiy tilining rivojiga ulkan hissa qo'shgan.",
    "Buxoro shahri 2500 yildan ortiq tarixga ega, dunyodagi eng qadimiy shaharlardan biri.",
    "Amir Temur o'z davrida Samarqandni jahon ilm-fan va me'morchilik markaziga aylantirgan.",
    "Ibn Sino (Avitsenna) O'zbekistonning Buxoro yaqinidagi hududdan chiqqan buyuk olim va tabib.",
    "Plov O'zbekistonda shunchaki ovqat emas — u to'y-marosimlarning ajralmas qismi hisoblanadi.",
]


async def fact_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/fakt — qiziqarli o'zbekcha fakt aytadi."""
    fact = random.choice(FACTS)
    await update.message.reply_text(f"🧠 Bilasizmi?\n{fact}")


# chat_id -> oxirgi xulosa qachon yuborilgani (unix time) — avtomatik jadval uchun
last_digest_time = {}
DIGEST_HOUR = 21  # har kuni soat nechada avtomatik xulosa yuborilsin (24 soatlik format)


def _build_digest_text(chat_id: int, hours_back: int = 24) -> str | None:
    """Oxirgi N soatdagi guruh suhbatidan xulosa matnini tayyorlaydi (Gemini orqali)."""
    since_ts = time.time() - hours_back * 3600
    items = memory.get_group_snapshot_since(chat_id, since_ts)

    if len(items) < 5:
        return None  # xulosa qilish uchun yetarli suhbat yo'q

    transcript = "\n".join(f"{item['name']}: {item['text']}" for item in items)

    prompt = (
        f"[TIZIM ESLATMASI] Quyida so'nggi {hours_back} soat ichida guruhda bo'lgan suhbat "
        "yozuvi berilgan. Shu asosida guruh uchun QIZIQARLI, HAZIL ARALASH kunlik xulosa "
        "(digest) yoz: eng ko'p gaplashgan odamlar, eng qiziq/kulgili lahza, umumiy mavzular "
        "haqida 3-5 gaplik quvnoq xulosa. Rasmiy hisobot emas, xuddi do'sting kun oxirida senga "
        "'bugun shunday-shunday bo'ldi' deb aytib berayotgandek yoz. Oxirida qisqa hazil bilan "
        f"yakunla.\n\nSUHBAT YOZUVI:\n{transcript}"
    )

    try:
        response = _call_gemini_with_fallback(
            [types.Content(role="user", parts=[types.Part(text=prompt)])],
            SYSTEM_PROMPT,
        )
        return (response.text or "").strip() or None
    except Exception as e:
        logger.error(f"Xulosa yaratishda xato: {e}")
        return None


# ============================================================
# ESLATMA (REMINDER) TIZIMI
# ============================================================

def _parse_relative_time(text: str) -> int | None:
    """Matndan 'N daqiqadan keyin', 'N soatdan keyin', 'N kundan keyin' kabi
    ifodalarni topib, necha soniyadan keyin ekanini qaytaradi. Topilmasa None."""
    text = text.lower()

    patterns = [
        (r"(\d+)\s*(daqiqa|minut)", 60),
        (r"(\d+)\s*(soat)", 3600),
        (r"(\d+)\s*(kun)", 86400),
    ]
    for pattern, multiplier in patterns:
        match = re.search(pattern, text)
        if match:
            return int(match.group(1)) * multiplier

    return None


def _extract_reminder_message(text: str) -> str:
    """Vaqt ifodasi va 'eslat' kabi so'zlarni olib tashlab, faqat eslatma matnini qoldiradi."""
    cleaned = re.sub(r"\d+\s*(daqiqa|minut|soat|kun)dan?\s*(keyin|so'ng|so'ngra)?", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(eslat|eslatib qo'y|eslatma qil|meni?ga?)\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.:-")
    return cleaned or "eslatma vaqti keldi"


async def _reminder_callback(context: ContextTypes.DEFAULT_TYPE):
    """Belgilangan vaqt kelganda ishga tushib, foydalanuvchiga eslatma yuboradi."""
    job = context.job
    chat_id = job.data["chat_id"]
    user_id = job.data["user_id"]
    reminder_text = job.data["text"]

    is_owner = memory.is_owner(memory.get_username(chat_id, user_id))
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    reply = generate_reply(
        chat_id, user_id, is_owner,
        include_group_context=False,
        extra_instruction=(
            f"[TIZIM ESLATMASI] Foydalanuvchi sendan avval \"{reminder_text}\" haqida eslatib "
            "qo'yishingni so'ragan edi, va hozir aynan shu payt keldi. Unga hazil-mutoyiba bilan, "
            "qiziqarli tarzda eslatib qo'y — quruq 'eslatma' emas, o'zingcha qiziqarli ohangda ayt."
        ),
    )
    try:
        await context.bot.send_message(chat_id=chat_id, text=f"⏰ {reply}")
    except Exception as e:
        logger.warning(f"Eslatma yuborib bo'lmadi: {e}")


async def remind_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/eslat <vaqt> <matn> — masalan: /eslat 30 daqiqa suv ich
    Yoki tabiiy tilda: botga reply/tag qilib 'menga 2 soatdan keyin ... eslat' deb yozish ham ishlaydi."""
    chat = update.effective_chat
    user = update.effective_user
    full_text = " ".join(context.args) if context.args else ""

    if not full_text:
        await update.message.reply_text(
            "Nimani va qachon eslataman? Masalan:\n/eslat 30 daqiqa suv ich\n/eslat 2 soat mashqqa bor"
        )
        return

    seconds = _parse_relative_time(full_text)
    if seconds is None or seconds <= 0:
        await update.message.reply_text(
            "Vaqtni tushunmadim 😅 Masalan shunday yoz: /eslat 30 daqiqa suv ich"
        )
        return

    if seconds > 7 * 86400:
        await update.message.reply_text("Juda uzoq muddat, 7 kundan oshmasin 😄")
        return

    reminder_text = _extract_reminder_message(full_text)

    if context.job_queue:
        context.job_queue.run_once(
            _reminder_callback,
            when=seconds,
            data={"chat_id": chat.id, "user_id": user.id, "text": reminder_text},
        )
        human_time = (
            f"{seconds // 86400} kundan" if seconds >= 86400 else
            f"{seconds // 3600} soatdan" if seconds >= 3600 else
            f"{seconds // 60} daqiqadan"
        )
        await update.message.reply_text(f"Xo'p! {human_time} keyin \"{reminder_text}\" deb eslataman ⏰")
    else:
        await update.message.reply_text("Eslatma tizimi hozircha ishlamayapti, keyinroq urinib ko'ring 😅")



async def warn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/warn — reply qilib yozilganda o'sha odamga ogohlantirish beradi (admin bo'lganda ishlaydi)."""
    message = update.message
    chat = update.effective_chat
    user = update.effective_user

    is_owner = _touch_and_check_owner(chat.id, user)
    if not is_owner:
        await message.reply_text("Bu buyruq faqat mening egam uchun 😏")
        return

    if not message.reply_to_message:
        await message.reply_text("Kimni ogohlantiray? Xabariga reply qilib /warn deb yoz.")
        return

    target = message.reply_to_message.from_user
    memory.touch_user(chat.id, target.id, target.username, target.first_name)
    warn_count = memory.add_warn(chat.id, target.id)
    target_name = target.first_name or target.username or "Kimdir"

    reply = generate_reply(
        chat.id, user.id, True,
        include_group_context=False,
        extra_instruction=(
            f"[TIZIM ESLATMASI] Ega sendan \"{target_name}\" ismli odamga rasmiy ogohlantirish "
            f"berish buyrug'ini berdi. Bu uning {warn_count}-ogohlantirishidir. "
            "Rasmiy, biroz qattiq, lekin hazil bilan aralashtirib ogohlantirish xabarini yoz. "
            f"Agar warn {warn_count} >= 3 bo'lsa — yanada jiddiyroq va 'keyingi safar chora "
            "ko'raman' deb ogohlantir."
        ),
    )
    await message.reply_text(f"⚠️ {target_name} → {warn_count} ta ogohlantirish\n\n{reply}")


async def unwarn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/unwarn — reply qilib yozilganda o'sha odamning ogohlantirish sonini tozalaydi."""
    message = update.message
    chat = update.effective_chat
    user = update.effective_user

    is_owner = _touch_and_check_owner(chat.id, user)
    if not is_owner:
        await message.reply_text("Bu buyruq faqat mening egam uchun 😏")
        return

    if not message.reply_to_message:
        await message.reply_text("Kimning warnini tozalayman? Xabariga reply qilib /unwarn deb yoz.")
        return

    target = message.reply_to_message.from_user
    memory.reset_warns(chat.id, target.id)
    target_name = target.first_name or target.username or "Kimdir"
    await message.reply_text(f"✅ {target_name} ning barcha ogohlantirishlari tozalandi.")


# ============================================================
# BOT O'ZI GURUHDA SUHBAT BOSHLAYDI — faol bo'lish tizimi
# ============================================================

# Vaqtga qarab faollik darajasi — tunda kam, kunduz ko'p
def _get_activity_chance() -> float:
    hour = datetime.datetime.now().hour
    if 0 <= hour < 7:
        return 0.0   # tunda uxlaydi, yozmaydi
    elif 7 <= hour < 10:
        return 0.4   # ertalab biroz yozadi
    elif 10 <= hour < 22:
        return 1.0   # kunduz to'liq faol
    else:
        return 0.6   # kechqurun o'rtacha


# Botning guruhga o'zi yoza oladigan xabar turlari
PROACTIVE_PROMPTS = [
    "Guruhda uzoqdan hech kim yozmadi. Suhbatni jonlantirishga harakat qil — "
    "qiziqarli savol ber, hazil qil yoki g'ayrioddiy bir narsa ayt. "
    "Kimnidir @username bilan chaqirish ham mumkin — guruhda bo'lgan odamlardan "
    "birini tegga olib murojaat qil.",

    "Guruh jim qoldi. Hammani faollashtirish uchun — oxirgi mavzuni davom ettir, "
    "yoki yangi qiziqarli savol ber. Agar kimni chaqirish kerak bo'lsa, "
    "@username bilan tegga ol.",

    "Guruh uzoqdan gapirishni to'xtatgan. Suhbat boshlash uchun biror "
    "kutilmagan, kulgili yoki hayratlanarli gap ayt — odamlar javob bersinlar.",

    "Hech kim yozmayapti. Bu senga navbat — eng kulgili yoki eng qiziqarli "
    "savolingni ber. Guruhni uygot.",
]


async def _proactive_chat_job(context: ContextTypes.DEFAULT_TYPE):
    """Har 10 daqiqada tekshiradi — agar guruhda 1 soatdan ko'p jim bo'lsa, bot o'zi yozadi."""
    now = time.time()
    INACTIVITY_THRESHOLD = 3600  # 1 soat (sekundda)

    for chat_id in memory.get_all_active_chats():
        last_activity = memory.get_group_last_activity(chat_id)

        # 1 soatdan kam jim bo'lsa, yoki faollik darajasi 0 bo'lsa — o'tkazib yuboramiz
        if now - last_activity < INACTIVITY_THRESHOLD:
            continue

        activity_chance = _get_activity_chance()
        if random.random() > activity_chance:
            continue

        # Guruhda kim bor — tegga olish uchun foydalanuvchilar ro'yxati
        known_users = memory.list_known_users(chat_id)
        mention_hints = ""
        if known_users:
            sample = random.sample(known_users, min(3, len(known_users)))
            names = [f"@{u['username']}" for u in sample if u.get("username")]
            if names:
                mention_hints = f"Guruhda shu odamlar bor: {', '.join(names)}. Kerak bo'lsa bittasini tegga ol."

        prompt = random.choice(PROACTIVE_PROMPTS)
        if mention_hints:
            prompt += f"\n{mention_hints}"

        # Vaqtga qarab maxsus qo'shimcha
        hour = datetime.datetime.now().hour
        if 7 <= hour <= 9:
            prompt += " Ertalab salomlashish ruhi bilan boshla."
        elif 12 <= hour <= 13:
            prompt += " Tushlik vaqtida odamlar biroz bo'sharoq bo'ladi — shunga mos yoz."
        elif 20 <= hour <= 22:
            prompt += " Kechqurun odamlar dam olishda — shunga mos kayfiyatda yoz."

        # Biron foydalanuvchi nomidan emas, guruh umumiy xotirasidan yozamiz
        # user_id = 0 (haqiqiy foydalanuvchi emas, bot o'zi)
        try:
            reply = generate_reply(
                chat_id, 0, False,
                include_group_context=True,
                extra_instruction=f"[TIZIM ESLATMASI] {prompt}",
            )
            await context.bot.send_message(chat_id=chat_id, text=reply)
            memory.update_group_activity(chat_id)  # yozgandan keyin vaqtni yangilaymiz
            logger.info(f"[Proaktiv xabar] chat={chat_id} ga yuborildi")
        except Exception as e:
            logger.warning(f"[Proaktiv xabar] chat={chat_id} ga yuborib bo'lmadi: {e}")



async def digest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/xulosa — so'nggi 24 soatdagi guruh suhbatining hazil aralash xulosasini beradi."""
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        await update.message.reply_text("Bu buyruq faqat guruhda ishlaydi 😄")
        return

    await context.bot.send_chat_action(chat_id=chat.id, action="typing")
    digest = _build_digest_text(chat.id, hours_back=24)

    if not digest:
        await update.message.reply_text("Hali xulosa qilish uchun yetarlicha suhbat bo'lmadi 🤷")
        return

    await update.message.reply_text(f"🗞 Kunlik xulosa:\n\n{digest}")


async def _auto_digest_job(context: ContextTypes.DEFAULT_TYPE):
    """JobQueue orqali har kuni bir marta chaqiriladi — faol guruhlarga avtomatik xulosa yuboradi."""
    now = time.time()
    for chat_id in list(memory._group_snapshot.keys()):
        last_sent = last_digest_time.get(chat_id, 0)
        if now - last_sent < 20 * 3600:  # kamida 20 soat oralig'ida bitta xulosa
            continue

        digest = _build_digest_text(chat_id, hours_back=24)
        if not digest:
            continue

        try:
            await context.bot.send_message(chat_id=chat_id, text=f"🗞 Kunlik xulosa:\n\n{digest}")
            last_digest_time[chat_id] = now
            logger.info(f"[Avto-xulosa] chat={chat_id} ga yuborildi")
        except Exception as e:
            logger.warning(f"[Avto-xulosa] chat={chat_id} ga yuborib bo'lmadi: {e}")



async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/gap_kim — shu guruhda eng ko'p SO'Z yozganlar reytingi."""
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        await update.message.reply_text("Bu buyruq faqat guruhda ishlaydi 😄")
        return

    top = memory.get_leaderboard(chat.id, top_n=10, by="words")
    if not top:
        await update.message.reply_text("Hali hech kim yetarlicha gaplashmadi.")
        return

    medals = ["🥇", "🥈", "🥉"]
    lines = ["📊 Eng ko'p so'z yozganlar:"]
    for i, row in enumerate(top):
        prefix = medals[i] if i < 3 else f"{i + 1}."
        lines.append(f"{prefix} {row['name']} — {row['word_count']} ta so'z ({row['message_count']} ta xabar)")

    await update.message.reply_text("\n".join(lines))


async def add_directive_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/buyruq <matn> — FAQAT EGA uchun: MUSHU doimiy amal qiladigan xatti-harakat qo'shadi."""
    user = update.effective_user
    chat = update.effective_chat
    is_owner = _touch_and_check_owner(chat.id, user)

    if not is_owner:
        await update.message.reply_text("Bu buyruq faqat mening egam uchun 😏")
        return

    if not context.args:
        await update.message.reply_text(
            "Buyruq matnini ham yozing. Masalan:\n/buyruq Ali ismli odamga doim yumshoqroq gapir"
        )
        return

    directive_text = " ".join(context.args)
    memory.add_owner_directive(directive_text)
    logger.info(f"[Ega buyrug'i qo'shildi]: {directive_text}")
    await update.message.reply_text(f"Xo'p bo'ladi, ega! ✅ Endi shunga qat'iy amal qilaman:\n« {directive_text} »")


async def list_directives_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/buyruqlar — FAQAT EGA uchun: hozirgi doimiy buyruqlar ro'yxati."""
    user = update.effective_user
    chat = update.effective_chat
    is_owner = _touch_and_check_owner(chat.id, user)

    if not is_owner:
        await update.message.reply_text("Bu buyruq faqat mening egam uchun 😏")
        return

    directives = memory.get_owner_directives()
    if not directives:
        await update.message.reply_text("Hozircha hech qanday doimiy buyruq yo'q.")
        return

    lines = ["📜 Doimiy buyruqlar:"] + [f"{i + 1}. {d}" for i, d in enumerate(directives)]
    await update.message.reply_text("\n".join(lines))


async def clear_directives_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/buyruq_ochir — FAQAT EGA uchun: barcha doimiy buyruqlarni tozalaydi."""
    user = update.effective_user
    chat = update.effective_chat
    is_owner = _touch_and_check_owner(chat.id, user)

    if not is_owner:
        await update.message.reply_text("Bu buyruq faqat mening egam uchun 😏")
        return

    memory.clear_owner_directives()
    await update.message.reply_text("Xo'p, barcha doimiy buyruqlarni unutdim. 🧹")


async def admins_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/adminlar — shu guruhning barcha adminlarini (va owner'ini) ko'rsatadi."""
    chat = update.effective_chat

    if chat.type not in ("group", "supergroup"):
        await update.message.reply_text("Bu buyruq faqat guruhda ishlaydi 😄")
        return

    try:
        admins = await context.bot.get_chat_administrators(chat.id)
    except Exception as e:
        logger.error(f"Adminlarni olishda xato: {e}")
        await update.message.reply_text("Adminlarni ko'ra olmadim, birozdan keyin qayta urinib ko'ring 😅")
        return

    owner_line = None
    admin_lines = []
    bot_line = None

    for member in admins:
        u = member.user
        uname = f"@{u.username}" if u.username else "(username yo'q)"
        name = u.first_name or "Noma'lum"

        # Ma'lumotni xotiraga ham yozib qo'yamiz — keyin /whoami, /users ishlashi uchun
        memory.touch_user(chat.id, u.id, u.username, u.first_name)

        if u.id == context.bot.id:
            bot_line = f"🤖 {name} {uname} — bu MEN 😎"
        elif member.status == ChatMemberStatus.OWNER:
            owner_line = f"👑 {name} {uname} — Guruh egasi"
        else:
            title = f" ({member.custom_title})" if getattr(member, "custom_title", None) else ""
            admin_lines.append(f"🛡 {name} {uname}{title}")

    lines = ["📋 Guruh adminlari:"]
    if owner_line:
        lines.append(owner_line)
    lines.extend(admin_lines)
    if bot_line:
        lines.append(bot_line)

    await update.message.reply_text("\n".join(lines))



async def welcome_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Guruhga yangi odam qo'shilganda MUSHU uni hazil bilan kutib oladi.
    ChatMemberHandler orqali ishlaydi — bu usul har doim ishonchli ishlaydi
    (link orqali kirganda ham, admin qo'shganda ham, privacy mode holatidan qat'i nazar)."""
    result = update.chat_member
    if not result:
        return

    old_status = result.old_chat_member.status
    new_status = result.new_chat_member.status

    # Faqat "chatda yo'q edi -> endi a'zo bo'ldi" holatini ushlaymiz
    was_member = old_status in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    is_member_now = new_status in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)

    if was_member or not is_member_now:
        return  # bu chiqib ketish, status o'zgarishi yoki eski a'zo bo'lsa — e'tiborsiz qoldiramiz

    chat = update.effective_chat
    new_user = result.new_chat_member.user

    logger.info(f"[Yangi a'zo] chat={chat.id} user_id={new_user.id} username=@{new_user.username}")

    if new_user.id == context.bot.id:
        await context.bot.send_message(
            chat_id=chat.id,
            text=(
                "Assalomu alaykum hammaga! Men MUSHU 😎 Endi shu guruhning rasmiy hazilkash "
                "a'zosiman. Meni chaqirish uchun 'mushu' deb yozing yoki reply qiling — "
                "lekin ogohlantiraman, ba'zida o'zim ham to'satdan gapga aralashib qolaman 😏"
            ),
        )
        return

    memory.touch_user(chat.id, new_user.id, new_user.username, new_user.first_name)
    display = new_user.first_name or new_user.username or "Yangi do'stimiz"

    await context.bot.send_chat_action(chat_id=chat.id, action="typing")
    reply = generate_reply(
        chat.id, new_user.id, False,
        include_group_context=True,
        extra_instruction=(
            f"[TIZIM ESLATMASI] Guruhga yangi odam qo'shildi, uning ismi \"{display}\". "
            "Uni hazil bilan, qiziqarli, o'ziga xos tarzda kutib ol — 1-2 gaplik quvnoq "
            "salomlashuv yoz, unga guruh haqida kichik hazil bilan ishora qilsang ham bo'ladi."
        ),
    )
    await context.bot.send_message(chat_id=chat.id, text=reply)


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("whoami", whoami))
    app.add_handler(CommandHandler("users", list_users))
    app.add_handler(CommandHandler("roast", roast_command))
    app.add_handler(CommandHandler("fakt", fact_command))
    app.add_handler(CommandHandler("gap_kim", leaderboard_command))
    app.add_handler(CommandHandler("xulosa", digest_command))
    app.add_handler(CommandHandler("adminlar", admins_command))
    app.add_handler(CommandHandler("warn", warn_command))
    app.add_handler(CommandHandler("unwarn", unwarn_command))
    app.add_handler(CommandHandler("buyruq", add_directive_command))
    app.add_handler(CommandHandler("buyruqlar", list_directives_command))
    app.add_handler(CommandHandler("buyruq_ochir", clear_directives_command))
    app.add_handler(ChatMemberHandler(welcome_new_members, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.Sticker.ALL, handle_sticker))

    # Har kuni soat DIGEST_HOUR:00 da avtomatik xulosa yuborishni tekshiradi
    if app.job_queue:
        # Kunlik xulosa — har kuni soat 21:00 da
        app.job_queue.run_daily(
            _auto_digest_job,
            time=datetime.time(hour=DIGEST_HOUR, minute=0),
        )
        # Proaktiv suhbat — har 10 daqiqada tekshiradi, agar 1 soat jim bo'lsa yozadi
        app.job_queue.run_repeating(
            _proactive_chat_job,
            interval=600,  # 10 daqiqa
            first=60,      # ishga tushgandan 1 daqiqa keyin birinchi tekshiruv
        )
        logger.info("Proaktiv suhbat va kunlik xulosa jadvallari yoqildi ✅")
    else:
        logger.warning(
            "JobQueue mavjud emas — avtomatik xabar va xulosa ishlamaydi. "
            "O'rnatish uchun: pip install 'python-telegram-bot[job-queue]'"
        )

    logger.info("MUSHU bot ishga tushdi...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    # Faqat Replit'da USE_KEEP_ALIVE=1 qilib qo'yilganda mini-server ishga tushadi.
    # Kompyuteringizda oddiy ishga tushirganda bu qism o'tkazib yuboriladi.
    if os.getenv("USE_KEEP_ALIVE") == "1":
        try:
            from keep_alive import keep_alive
            keep_alive()
            logger.info("Keep-alive server ishga tushdi (Replit rejimi)")
        except ImportError:
            logger.warning("keep_alive.py topilmadi yoki flask o'rnatilmagan, o'tkazib yuborildi")

    main()
