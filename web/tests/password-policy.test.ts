import { describe, expect, it } from 'vitest';
import {
  PASSWORD_RULE_MESSAGE,
  validatePassword,
} from '@/utils/passwordPolicy';

describe('共享密码策略', () => {
  it('按 Unicode code point 计算最小长度，而不是 UTF-16 code unit', () => {
    // 11 个 code points，但 String.length 为 20；Python len 会拒绝。
    const password = `a1${'😀'.repeat(9)}`;
    expect(validatePassword(password)).toBe(PASSWORD_RULE_MESSAGE);
  });

  it('接受 12 至 64 位且包含 ASCII 字母和数字的密码', () => {
    expect(validatePassword('a1'.repeat(6))).toBeNull();
    expect(validatePassword('a1'.repeat(32))).toBeNull();
  });

  it('拒绝超过 64 个 code point 的密码', () => {
    expect(validatePassword(`a1${'😀'.repeat(63)}`)).toBe(
      '密码长度不能超过 64 个字符',
    );
  });

  it('保留 bcrypt 的 72 UTF-8 字节上限', () => {
    expect(validatePassword(`a1${'中'.repeat(24)}`)).toBe(
      '密码过长，UTF-8 编码后不能超过 72 字节',
    );
  });

  it('只认可 ASCII 字母和数字', () => {
    expect(validatePassword('１２３４５６７８９１１１Ａ')).toBe(PASSWORD_RULE_MESSAGE);
    expect(validatePassword('abcdefghijk1')).toBeNull();
  });
});
