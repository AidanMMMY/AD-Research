/**
 * 按需注册的 ECharts 实例（前端审计 2026-08-06）。
 *
 * 之前所有图表组件 `import ReactECharts from 'echarts-for-react'` 会拉入
 * 整个 echarts（minified ~1.05MB）。这里用 echarts/core 只注册本项目实际
 * 用到的图表类型与组件，构建后 echarts chunk 约 350KB。
 *
 * 组件必须通过 `<ReactECharts echarts={echarts} ... />` 显式传入本实例，
 * 否则 echarts-for-react 会回退到未注册的全局 echarts 并报错。
 */
import * as echarts from 'echarts/core';
import {
  BarChart,
  HeatmapChart,
  LineChart,
  PieChart,
  RadarChart,
} from 'echarts/charts';
import {
  AriaComponent,
  DataZoomComponent,
  DatasetComponent,
  GraphicComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  MarkPointComponent,
  TitleComponent,
  ToolboxComponent,
  TooltipComponent,
  VisualMapComponent,
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

echarts.use([
  LineChart,
  BarChart,
  PieChart,
  RadarChart,
  HeatmapChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  TitleComponent,
  DataZoomComponent,
  VisualMapComponent,
  ToolboxComponent,
  MarkLineComponent,
  MarkPointComponent,
  AriaComponent,
  DatasetComponent,
  GraphicComponent,
  CanvasRenderer,
]);

export default echarts;
