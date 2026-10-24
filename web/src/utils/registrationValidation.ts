// Field-level validation for the self-service registration flow
// (docs/dev-notes/20261025-self-registration-design.md). The username pattern
// mirrors the backend contract ^[a-zA-Z0-9_]{3,30}$; password rules live in
// utils/passwordPolicy.ts so registration and /change-password share one
// source of truth.
export const USERNAME_PATTERN = /^[a-zA-Z0-9_]{3,30}$/;
export const USERNAME_RULE_HINT = '3–30 位，只能用字母、数字或下划线';

export function validateEmail(email: string): string | null {
  if (!email) return '先填一个邮箱，验证邮件要发到这里';
  if (email.trim() !== email) return '邮箱前后好像多了空格，去掉再试试';
  // Pragmatic shape check (local@domain.tld); the backend re-validates anyway.
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email)) {
    return '邮箱格式看起来不太对，检查一下有没有漏字符？';
  }
  return null;
}

export function validateUsername(username: string): string | null {
  if (!username) return '给自己起个名字吧（3–30 位字母 / 数字 / 下划线）';
  if (username.length < 3) return '用户名至少 3 位，再加一两个字符？';
  if (username.length > 30) return '用户名最多 30 位，精简一下？';
  if (!USERNAME_PATTERN.test(username)) {
    return '用户名只能包含英文字母、数字和下划线';
  }
  return null;
}
