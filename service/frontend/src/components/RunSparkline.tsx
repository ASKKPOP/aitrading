import { useEffect, useRef } from 'react'
import { GLLineChart } from '../webgl/GLLineChart'

// Thin React wrapper around the WebGL2 line kernel. Feeds the equity series
// as a plain number[]; the kernel handles ring buffer, decimation, DPR,
// context-loss, and the Canvas2D fallback.
export function RunSparkline({ values, color, height = 48 }: {
  values: number[]
  color: string
  height?: number
}) {
  const ref = useRef<HTMLCanvasElement | null>(null)
  const chartRef = useRef<GLLineChart | null>(null)

  useEffect(() => {
    if (!ref.current) return
    const chart = new GLLineChart(ref.current, { capacity: 8192, color })
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
