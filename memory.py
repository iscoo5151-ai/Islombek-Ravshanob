"""
memory.py — MUSHU botining xotira moduli.

Vazifasi:
- Har bir foydalanuvchini (username, ism) eslab qolish
- Har kimning shaxsiy suhbat mavzusini alohida saqlash (bir-biriga aralashmasin)
- Guruhdagi umumiy "kim nima dedi" kontekstini ham saqlash — shunda bot boshqa
  odamlarning gaplarini ham biladi, lekin har kimga o'z mavzusida javob beradi
- Botning EGASINI (username orqali) tanib olish
"""

import time

# Botni yaratgan odamning Telegram username'i (@ belgisisiz, kichik harfda solishtiriladi)
OWNER_USERNAME = "islombekravshanov51"

MAX_USER_HISTORY = 8     # har bir foydalanuvchining shaxsiy xotirasida nechta xabar saqlansin
MAX_GROUP_SNAPSHOT = 150  # guruh umumiy kontekstida nechta oxirgi xabar saqlansin (kunlik xulosa uchun ko'proq)
CONTEXT_SNAPSHOT_TAIL = 10  # oddiy javob berishda promptga faqat oxirgi shuncha xabar qo'shiladi


class Memory:
    def __init__(self):
        # (chat_id, user_id) -> {"username": str, "first_name": str, "history": [ {role, content} ]}
        self._users = {}
        # chat_id -> [ {"name": str, "text": str, "ts": float} ]  — guruh umumiy oqimi
        self._group_snapshot = {}
        # Egangiz bergan doimiy xatti-harakat buyruqlari (masalan "X ga yumshoqroq gapir")
        self._owner_directives = []
        # username -> [buyruqlar ro'yxati] — ma'lum bir odamga nisbatan berilgan ko'rsatmalar
        self._user_directives = {}

    # ---------- Foydalanuvchi ma'lumotlari ----------

    def _key(self, chat_id: int, user_id: int):
        return (chat_id, user_id)

    def touch_user(self, chat_id: int, user_id: int, username: str | None, first_name: str | None):
        """Foydalanuvchi haqidagi ma'lumotni yangilaydi (username o'zgarishi mumkin)."""
        key = self._key(chat_id, user_id)
        entry = self._users.setdefault(key, {
            "username": None, "first_name": None, "history": [],
            "message_count": 0, "word_count": 0, "first_seen": time.time(), "last_seen": time.time(),
        })
        entry["username"] = (username or "").lstrip("@") or entry["username"]
        entry["first_name"] = first_name or entry["first_name"]
        return entry

    def is_owner(self, username: str | None) -> bool:
        if not username:
            return False
        return username.lstrip("@").lower() == OWNER_USERNAME.lower()

    def display_name(self, chat_id: int, user_id: int) -> str:
        entry = self._users.get(self._key(chat_id, user_id))
        if not entry:
            return "Kimdir"
        return entry.get("first_name") or entry.get("username") or "Kimdir"

    def get_username(self, chat_id: int, user_id: int) -> str | None:
        entry = self._users.get(self._key(chat_id, user_id))
        return entry.get("username") if entry else None

    # ---------- Shaxsiy suhbat tarixi ----------

    def record_personal(self, chat_id: int, user_id: int, role: str, text: str):
        entry = self._users.setdefault(
            self._key(chat_id, user_id),
            {"username": None, "first_name": None, "history": [],
             "message_count": 0, "word_count": 0, "first_seen": time.time(), "last_seen": time.time()},
        )
        entry["history"].append({"role": role, "content": text})
        entry["history"][:] = entry["history"][-MAX_USER_HISTORY:]

        # Faqat foydalanuvchining o'z xabarlarini sanaymiz (bot javoblarini emas)
        if role == "user":
            entry["message_count"] = entry.get("message_count", 0) + 1
            entry["word_count"] = entry.get("word_count", 0) + len(text.split())
            entry["last_seen"] = time.time()

    def get_personal_history(self, chat_id: int, user_id: int):
        entry = self._users.get(self._key(chat_id, user_id))
        return entry["history"] if entry else []

    # ---------- Guruh umumiy oqimi (kim nima dedi) ----------

    def record_group_snapshot(self, chat_id: int, name: str, text: str):
        snap = self._group_snapshot.setdefault(chat_id, [])
        snap.append({"name": name, "text": text, "ts": time.time()})
        snap[:] = snap[-MAX_GROUP_SNAPSHOT:]

    def get_group_context_text(self, chat_id: int, exclude_user_id: int | None = None) -> str:
        """Guruhda oxirgi kim nima deganini bitta matn qilib qaytaradi (javob berish uchun, qisqa)."""
        snap = self._group_snapshot.get(chat_id, [])
        if not snap:
            return ""
        tail = snap[-CONTEXT_SNAPSHOT_TAIL:]
        lines = [f"{item['name']}: {item['text']}" for item in tail]
        return "\n".join(lines)

    def get_group_snapshot_since(self, chat_id: int, since_ts: float):
        """Berilgan vaqtdan keyingi barcha guruh xabarlarini qaytaradi (kunlik xulosa uchun)."""
        snap = self._group_snapshot.get(chat_id, [])
        return [item for item in snap if item["ts"] >= since_ts]

    # ---------- Debug / admin uchun: barcha tanilgan foydalanuvchilar ----------

    def list_known_users(self, chat_id: int | None = None):
        """Har bir (chat_id, user_id) uchun username va ismni qaytaradi.
        chat_id berilsa faqat o'sha chatdagilar, aks holda hammasi."""
        result = []
        for (c_id, u_id), entry in self._users.items():
            if chat_id is not None and c_id != chat_id:
                continue
            result.append({
                "chat_id": c_id,
                "user_id": u_id,
                "username": entry.get("username"),
                "first_name": entry.get("first_name"),
            })
        return result

    def get_leaderboard(self, chat_id: int, top_n: int = 10, by: str = "words"):
        """Shu chatda eng ko'p gaplashganlar reytingi.
        by='words' -> so'z soni bo'yicha (default), by='messages' -> xabar soni bo'yicha."""
        key_field = "word_count" if by == "words" else "message_count"
        rows = []
        for (c_id, u_id), entry in self._users.items():
            if c_id != chat_id:
                continue
            rows.append({
                "name": entry.get("first_name") or entry.get("username") or "Kimdir",
                "message_count": entry.get("message_count", 0),
                "word_count": entry.get("word_count", 0),
            })
        rows.sort(key=lambda r: r[key_field], reverse=True)
        return rows[:top_n]

    # ---------- Egangiz bergan doimiy xatti-harakat buyruqlari ----------

    MAX_DIRECTIVES = 15

    def add_owner_directive(self, text: str):
        """Ega '/buyruq ...' orqali bergan ko'rsatmani doimiy ro'yxatga qo'shadi."""
        self._owner_directives.append(text)
        self._owner_directives[:] = self._owner_directives[-self.MAX_DIRECTIVES:]

    def get_owner_directives(self):
        return list(self._owner_directives)

    def clear_owner_directives(self):
        self._owner_directives.clear()

    def get_owner_directives_text(self) -> str:
        if not self._owner_directives:
            return ""
        lines = [f"- {d}" for d in self._owner_directives]
        return "\n".join(lines)

    # ---------- Egangiz ma'lum bir ODAMGA nisbatan bergan buyruqlar ----------
    # Masalan: ega guruhda "@ali ga jahl bilan gapir" desa, bu FAQAT ali bilan
    # gaplashganda qo'llaniladi, boshqalarga tegmaydi.

    MAX_USER_DIRECTIVES_PER_PERSON = 5

    def add_user_directive(self, username: str, text: str):
        username = username.lstrip("@").lower()
        lst = self._user_directives.setdefault(username, [])
        lst.append(text)
        lst[:] = lst[-self.MAX_USER_DIRECTIVES_PER_PERSON:]

    def get_user_directives_text(self, username: str | None) -> str:
        if not username:
            return ""
        lst = self._user_directives.get(username.lstrip("@").lower())
        if not lst:
            return ""
        lines = [f"- {d}" for d in lst]
        return "\n".join(lines)

    def clear_user_directives(self, username: str):
        self._user_directives.pop(username.lstrip("@").lower(), None)