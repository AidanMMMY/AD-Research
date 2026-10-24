"""Password policy helpers shared by all password-setting code paths.

Policy (2026-10-24): at least 12 characters, at least one ASCII letter
and at least one ASCII digit. Upper bound is 64 characters. bcrypt also
truncates at 72 *bytes*, so multi-byte UTF-8 passwords get a second byte
length check; over-long passwords are rejected instead of pre-hashed
(keeps the hash format uniform and the rule easy to explain to users).

Used by:
  * ``app/api/v1/admin_users.py`` (create user / admin reset password)
  * ``app/api/v1/auth.py``       (self-service change password)
"""

import secrets
import string

MIN_LENGTH = 12
MAX_LENGTH = 64
# A 64-character limit alone is insufficient for multi-byte UTF-8 input.
BCRYPT_MAX_BYTES = 72

POLICY_HINT = "密码至少 12 位，且需包含英文字母和数字"

# Ambiguous/hostile characters are excluded from generated passwords:
# quotes, backslash and whitespace (break copy-paste into shells/JSON)
# and look-alikes are kept — generated passwords are meant to be copied
# once, not typed, so look-alike ambiguity is acceptable.
_GENERATE_SPECIALS = "!@#$%^&*()-_=+[]"
_GENERATE_ALPHABET = string.ascii_letters + string.digits + _GENERATE_SPECIALS


def validate_password(password: str) -> str | None:
    """Return a Chinese error message if the password violates the policy.

    Returns ``None`` when the password is acceptable, so callers can do::

        error = validate_password(pw)
        if error:
            raise HTTPException(status_code=422, detail=error)
    """
    if not password:
        return "密码不能为空"
    if len(password) < MIN_LENGTH:
        return POLICY_HINT
    if len(password) > MAX_LENGTH:
        return f"密码长度不能超过 {MAX_LENGTH} 个字符"
    try:
        encoded = password.encode("utf-8")
    except UnicodeEncodeError:
        # Lone Unicode surrogates can arrive through JSON decoders. Treat
        # them as invalid input instead of failing the request with a 500.
        return "密码包含无效字符，请更换后重试"
    if len(encoded) > BCRYPT_MAX_BYTES:
        return f"密码过长，UTF-8 编码后不能超过 {BCRYPT_MAX_BYTES} 字节"
    if not any(ch.isascii() and ch.isalpha() for ch in password):
        return POLICY_HINT
    if not any(ch in string.digits for ch in password):
        return POLICY_HINT
    return None


def generate_random_password(length: int = 16) -> str:
    """Generate a random password guaranteed to satisfy the policy.

    Composition: at least one letter, one digit and one special character,
    the remainder drawn from the full alphabet; then shuffled so the
    guaranteed characters are not always at the head.
    """
    if length < MIN_LENGTH:
        length = MIN_LENGTH
    chars = [
        secrets.choice(string.ascii_letters),
        secrets.choice(string.digits),
        secrets.choice(_GENERATE_SPECIALS),
    ]
    chars.extend(secrets.choice(_GENERATE_ALPHABET) for _ in range(length - len(chars)))
    # Fisher-Yates with secrets for a cryptographic-quality shuffle.
    for i in range(len(chars) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        chars[i], chars[j] = chars[j], chars[i]
    return "".join(chars)
