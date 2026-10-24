import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { Alert, Button, Form, Input, message } from 'antd';
import { AxiosError } from 'axios';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import Panel from '@/components/Panel';
import SectionHeading from '@/components/SectionHeading';
import { authApi } from '@/api';
import { useAuthStore } from '@/stores/auth';
import { PASSWORD_RULE_MESSAGE, validatePassword } from '@/utils/passwordPolicy';
import { meQueryKey } from '@/hooks/useAuth';

interface FormValues {
  old_password: string;
  new_password: string;
  confirm_password: string;
}

export default function ChangePassword() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user, setTokens, setUser } = useAuthStore();
  const [form] = Form.useForm<FormValues>();
  const [submitting, setSubmitting] = useState(false);

  const forced = user?.must_change_password === true;

  const handleSubmit = async (values: FormValues) => {
    setSubmitting(true);
    try {
      const { data } = await authApi.changePassword({
        old_password: values.old_password,
        new_password: values.new_password,
      });
      // The backend revoked every old refresh token and returned a fresh
      // pair. Persist it first so this session does not go offline when
      // the previous access token expires, then clear the forced flag.
      await setTokens(data.access_token, data.refresh_token);
      const currentUser = useAuthStore.getState().user;
      if (currentUser) {
        const updatedUser = { ...currentUser, must_change_password: false };
        setUser(updatedUser);
        // Keep useMe's cached Axios-shaped response in sync; otherwise a
        // stale cached `must_change_password=true` could redirect us back.
        queryClient.setQueryData(meQueryKey(useAuthStore.getState().token), {
          data: updatedUser,
        });
      }
      message.success('密码修改成功，当前会话已保持登录');
      navigate('/dashboard', { replace: true });
    } catch (err) {
      const status = (err as AxiosError)?.response?.status;
      const detail = (err as AxiosError<{ detail?: string }>)?.response?.data?.detail;
      if (status === 400) {
        message.error(detail || '旧密码不正确');
      } else if (status === 422) {
        message.error(detail || PASSWORD_RULE_MESSAGE);
      } else {
        message.error('密码修改失败，请稍后再试');
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <PageShell maxWidth="reading">
      <PageHeader
        title="修改密码"
        description={
          forced
            ? '为保障账号安全，首次登录请先修改密码'
            : '定期更换密码可以降低账号被盗风险'
        }
      />

      <SectionHeading title="设置新密码" />
      <Panel variant="default" padding="md">
        {forced && (
          <Alert
            type="warning"
            showIcon
            style={{ marginBottom: 16 }}
            message="首次登录需修改密码"
            description="您当前使用的是初始密码，请设置一个不少于 12 位、同时包含英文字母和数字的新密码。修改成功后其他设备需要重新登录，当前会话会保持登录。"
          />
        )}
        <Form form={form} layout="vertical" onFinish={handleSubmit} requiredMark={false}>
          <Form.Item
            name="old_password"
            label="当前密码"
            rules={[{ required: true, message: '请输入当前密码' }]}
          >
            <Input.Password placeholder="当前密码" autoComplete="current-password" />
          </Form.Item>
          <Form.Item
            name="new_password"
            label="新密码"
            rules={[
              {
                validator: (_, value: string) => {
                  if (!value) return Promise.reject(new Error('请输入新密码'));
                  const error = validatePassword(value);
                  return error ? Promise.reject(new Error(error)) : Promise.resolve();
                },
              },
            ]}
          >
            <Input.Password
              placeholder="至少 12 位，含英文字母和数字"
              autoComplete="new-password"
            />
          </Form.Item>
          <Form.Item
            name="confirm_password"
            label="确认新密码"
            dependencies={['new_password']}
            rules={[
              { required: true, message: '请再次输入新密码' },
              ({ getFieldValue }) => ({
                validator: (_, value: string) =>
                  !value || getFieldValue('new_password') === value
                    ? Promise.resolve()
                    : Promise.reject(new Error('两次输入的密码不一致')),
              }),
            ]}
          >
            <Input.Password placeholder="再次输入新密码" autoComplete="new-password" />
          </Form.Item>
          <Form.Item style={{ marginBottom: 0 }}>
            <Button type="primary" htmlType="submit" loading={submitting} block>
              确认修改
            </Button>
          </Form.Item>
        </Form>
      </Panel>
    </PageShell>
  );
}
