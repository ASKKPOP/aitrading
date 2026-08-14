import { useEffect, useRef } from 'react'
import { GLLineChart } from '../webgl/GLLineChart'

// Thin React wrapper around the line kernel. Feeds the equity series
// as a plain number[]; the kernel handles ring buffer, decimation, DPR,
// context-loss, and the Canvas2D fallback.
//
// mode '2d' skips WebGL entirely. Chromium caps a page at 16 live WebGL
// contexts (8 on Android) and silently EVICTS the oldest beyond that — the
// evicted canvas paints as a white box with a dead-face glyph. The runs grid
// mounts one chart per active run (20+ under fleet churn), so grid cards must
// use '2d'; only the single detail-drawer chart keeps WebGL.
export function RunSparkline({ values, color, height = 48, mode = 'gl' }: {
  values: number[]
  color: string
  height?: number
  mode?: 'gl' | '2d'
}) {
  const ref = useRef<HTMLCanvasElement | null>(null)
  const chartRef = useRef<GLLineChart | null>(null)

  useEffect(() => {
    if (!ref.current) return
    const chart = new GLLineChart(ref.current, { capacity: 8192, color, mode })
    chartRef.current = chart
    return () => { chart.dispose(); chartRef.current = null }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => { chartRef.current?.setColor(color) }, [color])
  useEffect(() => { chartRef.current?.setData(values) }, [values])

  return (
    <canvas
      ref={ref}
      style={{ width: '100%', height, display: 'block' }}
      aria-label="equity chart"
    />
  )
}
