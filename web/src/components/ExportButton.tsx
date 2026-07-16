import { useCallback, useState } from 'react';
import { Button, Dropdown, message, type MenuProps } from 'antd';
import {
  DownloadOutlined,
  FileTextOutlined,
  FileExcelOutlined,
  LoadingOutlined,
} from '@ant-design/icons';
import { exportToCSV, exportToXLSX, type ExportRow } from '@/utils/exportData';

/**
 * 通用导出按钮 — 把当前可见/已筛选的表格数据一键下载为 CSV 或 XLSX。
 *
 * 用法：
 *   <ExportButton rows={tableRows} filename="signals-20260716" />
 *
 * 设计：
 * - antd Dropdown 触发，两个 MenuItem：CSV / Excel
 * - rows 为空时自动 disabled（同时提示）
 * - 触发后短暂 Loading → message 提示，避免用户重复点击
 * - 不引入 xlsx 库；CSV 默认 / XLSX 走 exportData.ts 内手写 zip 实现
 */

export interface ExportButtonProps {
  /** 要导出的行数组；空数组时按钮自动 disabled */
  rows: ExportRow[];
  /** 文件名（不含扩展名，自动补 .csv / .xlsx）；不传则用 'export' */
  filename?: string;
  /** 可选 — Excel sheet 名；默认 'Sheet1' */
  sheetName?: string;
  /** 可选 — 锁定列顺序（保证导出与 UI 一致） */
  headers?: string[];
  /** 按钮大小，默认 'small'（与面板 header 一致） */
  size?: 'small' | 'middle' | 'large';
  /** 触发后的提示文案前缀；不传则 '已导出' */
  successPrefix?: string;
  /** Optional className passthrough */
  className?: string;
  /** 按钮类型，默认 'default' */
  type?: 'default' | 'primary' | 'text' | 'link';
}

export default function ExportButton({
  rows,
  filename = 'export',
  sheetName,
  headers,
  size = 'small',
  successPrefix = '已导出',
  className,
  type = 'default',
}: ExportButtonProps) {
  const [loading, setLoading] = useState(false);
  const isEmpty = !rows || rows.length === 0;

  const handleExport = useCallback(
    (format: 'csv' | 'xlsx') => {
      if (isEmpty) {
        // 防御性：disabled 也会触发，但保留提示避免 hover 时被遮蔽
        message.warning('当前没有可导出的数据');
        return;
      }
      setLoading(true);
      // 用 microtask + setTimeout 把 loading 推一帧，避免阻塞浏览器下载
      const safeRun = () => {
        try {
          if (format === 'csv') {
            exportToCSV(rows, filename, headers);
          } else {
            exportToXLSX(rows, filename, sheetName, headers);
          }
          message.success(
            `${successPrefix} ${rows.length.toLocaleString()} 行（${format.toUpperCase()}）`,
          );
        } catch (err) {
          // 大多数场景下浏览器会拦截下载；这里给用户一个明确错误
          message.error(`导出失败：${(err as Error)?.message ?? '未知错误'}`);
        } finally {
          // 50ms 后释放 loading —— 浏览器下载已经在另一线程跑了
          setTimeout(() => setLoading(false), 50);
        }
      };
      // 双帧延后，确保 loading 视觉先呈现
      setTimeout(safeRun, 0);
    },
    [rows, filename, headers, sheetName, successPrefix, isEmpty],
  );

  const menuItems: MenuProps['items'] = [
    {
      key: 'csv',
      label: '导出 CSV',
      icon: <FileTextOutlined />,
      onClick: () => handleExport('csv'),
      disabled: isEmpty || loading,
    },
    {
      key: 'xlsx',
      label: '导出 Excel',
      icon: <FileExcelOutlined />,
      onClick: () => handleExport('xlsx'),
      disabled: isEmpty || loading,
    },
  ];

  return (
    <Dropdown
      menu={{ items: menuItems }}
      trigger={['click']}
      placement="bottomRight"
      // disabled 状态下不弹出 dropdown
      disabled={isEmpty || loading}
    >
      <Button
        type={type}
        size={size}
        icon={
          loading ? (
            <LoadingOutlined spin />
          ) : (
            <DownloadOutlined />
          )
        }
        loading={loading}
        disabled={isEmpty}
        className={className}
        // 给屏幕阅读器一个明确的标签
        aria-label={isEmpty ? '暂无可导出数据' : `导出 ${rows.length} 行`}
        // 阻止冒泡，避免父容器把它当成 "行点击" 误触
        onClick={(e) => e.stopPropagation()}
      >
        导出
      </Button>
    </Dropdown>
  );
}