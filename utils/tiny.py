"""Unicode tiny-text helper. Use on plain words only (never on HTML tags)."""

_SRC = "abcdefghijklmnopqrstuvwxyz"
_DST = "ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢ"
assert len(_SRC) == len(_DST)
_MAP = {ord(a): b for a, b in zip(_SRC, _DST)}


def tiny(text) -> str:
    return str(text).lower().translate(_MAP)
