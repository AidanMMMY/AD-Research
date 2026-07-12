import { Form, InputNumber, Select, Switch, Input } from 'antd';
import type { ParamSpec } from '@/types/strategy';

interface StrategyParamFormProps {
  paramSpecs: Record<string, ParamSpec>;
  prefix?: string[];
}

export default function StrategyParamForm({ paramSpecs, prefix = ['params'] }: StrategyParamFormProps) {
  return (
    <>
      {Object.entries(paramSpecs).map(([key, spec]) => {
        const name = [...prefix, key];
        const label = spec.label || key;
        const help = spec.description;

        if (spec.type === 'bool') {
          return (
            <Form.Item
              key={key}
              name={name}
              label={label}
              initialValue={spec.default}
              valuePropName="checked"
              help={help}
            >
              <Switch />
            </Form.Item>
          );
        }

        if (spec.type === 'choice') {
          return (
            <Form.Item
              key={key}
              name={name}
              label={label}
              initialValue={spec.default}
              help={help}
            >
              <Select
                options={spec.options?.map((opt) => ({ label: opt, value: opt }))}
              />
            </Form.Item>
          );
        }

        if (spec.type === 'int' || spec.type === 'float') {
          return (
            <Form.Item
              key={key}
              name={name}
              label={label}
              initialValue={spec.default}
              help={help}
            >
              <InputNumber
                className="ad-form-input--full"
                min={spec.min}
                max={spec.max}
                step={spec.type === 'int' ? 1 : 0.01}
                precision={spec.type === 'int' ? 0 : 4}
              />
            </Form.Item>
          );
        }

        return (
          <Form.Item
            key={key}
            name={name}
            label={label}
            initialValue={spec.default}
            help={help}
          >
            <Input />
          </Form.Item>
        );
      })}
    </>
  );
}
