// 按需注册 ECharts 组件，减小打包体积
import { BarChart, CandlestickChart, HeatmapChart, LineChart, ScatterChart } from 'echarts/charts'
import {
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkAreaComponent,
  MarkLineComponent,
  MarkPointComponent,
  TooltipComponent,
  VisualMapComponent,
} from 'echarts/components'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'

use([
  CanvasRenderer,
  LineChart,
  BarChart,
  HeatmapChart,
  CandlestickChart,
  ScatterChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DataZoomComponent,
  MarkPointComponent,
  MarkLineComponent,
  MarkAreaComponent,
  VisualMapComponent,
])
