// Mirrors app/services/password_policy.py. Array.from counts Unicode code
// points like Python's len(str), rather than JavaScript UTF-16 code units.
export const PASSWORD_RULE_MESSAGE = '密码至少 12 位，且需包含英文字母和数字';

export function validatePassword(password: string): string | null {
  const length = Array.from(password).length;
  if (!password) return '密码不能为空';
  if (length < 12) return PASSWORD_RULE_MESSAGE;
  if (length > 64) return '密码长度不能超过 64 个字符';
  if (new TextEncoder().encode(password).length > 72) {
    return '密码过长，UTF-8 编码后不能超过 72 字节';
  }
  if (!/[A-Za-z]/.test(password) || !/\d/.test(password)) {
    return PASSWORD_RULE_MESSAGE;
  }
  return null;
}
