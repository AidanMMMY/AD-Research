import React, { useState } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import OtpInput from '@/components/auth/OtpInput';

/** Stateful wrapper so parent-driven value round-trips like the real page. */
function Harness(props: {
  onSubmit?: () => void;
  status?: 'idle' | 'error' | 'success';
  disabled?: boolean;
}) {
  const [value, setValue] = useState('');
  return (
    <OtpInput
      value={value}
      onChange={setValue}
      onSubmit={props.onSubmit}
      status={props.status}
      disabled={props.disabled}
    />
  );
}

function cells() {
  return screen.getAllByLabelText(/第 \d 位邮箱验证码/);
}

describe('OtpInput 交互', () => {
  afterEach(cleanup);

  it('输入数字自动进格，逐格填满', () => {
    render(<Harness />);
    const list = cells();
    fireEvent.change(list[0], { target: { value: '1' } });
    fireEvent.change(list[1], { target: { value: '2' } });
    expect(list[0]).toHaveValue('1');
    expect(list[1]).toHaveValue('2');
    expect(document.activeElement).toBe(list[2]);
  });

  it('退格回退：空格回退并清掉前一位', () => {
    render(<Harness />);
    const list = cells();
    fireEvent.change(list[0], { target: { value: '1' } });
    fireEvent.change(list[1], { target: { value: '2' } });
    // 光标已自动停在 cell[2]（空格），退格应清掉 '2' 并聚焦 cell[1]
    fireEvent.keyDown(list[2], { key: 'Backspace' });
    expect(list[1]).toHaveValue('');
    expect(list[0]).toHaveValue('1');
    expect(document.activeElement).toBe(list[1]);
    // 再退一次清掉 '1'
    fireEvent.keyDown(list[1], { key: 'Backspace' });
    expect(list[0]).toHaveValue('');
    expect(document.activeElement).toBe(list[0]);
  });

  it('整段粘贴自动分列：只取数字、超出截断', () => {
    render(<Harness />);
    const list = cells();
    fireEvent.paste(list[0], {
      clipboardData: { getData: () => 'ab12cd34ef56x7' },
    });
    expect(list.map((c) => (c as HTMLInputElement).value)).toEqual([
      '1',
      '2',
      '3',
      '4',
      '5',
      '6',
    ]);
    // 粘贴后光标落在最后一格
    expect(document.activeElement).toBe(list[5]);
  });

  it('Enter 直接提交', () => {
    const onSubmit = vi.fn();
    render(<Harness onSubmit={onSubmit} />);
    fireEvent.keyDown(cells()[0], { key: 'Enter' });
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it('非数字输入被忽略', () => {
    render(<Harness />);
    const list = cells();
    fireEvent.change(list[0], { target: { value: 'x' } });
    expect(list[0]).toHaveValue('');
  });

  it('error 状态标记 aria-invalid 并给格子加错误类', () => {
    const { rerender } = render(<Harness />);
    rerender(<Harness status="error" />);
    const list = cells();
    list.forEach((cell) => expect(cell).toHaveAttribute('aria-invalid', 'true'));
    const group = list[0].parentElement as HTMLElement;
    expect(group.className).toContain('otp-group--error');
    // 新到达的 error 会触发一次 shake（480ms 后移除类）
    expect(group.className).toContain('otp-group--shake');
  });

  it('success 状态给整组加成功类', () => {
    const { rerender } = render(<Harness />);
    rerender(<Harness status="success" />);
    const group = cells()[0].parentElement as HTMLElement;
    expect(group.className).toContain('otp-group--success');
  });
});
