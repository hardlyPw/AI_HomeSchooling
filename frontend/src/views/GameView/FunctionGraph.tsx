import { useEffect, useRef } from 'react'
import functionPlotImport from 'function-plot'
import type { FunctionPlotDatum } from 'function-plot'
import type { GraphPoint } from '../../clients/games/GameClient'

interface FunctionGraphProps {
  target: GraphPoint[]
  player: GraphPoint[]
}

const functionPlot = (
  functionPlotImport as typeof functionPlotImport & { default?: typeof functionPlotImport }
).default ?? functionPlotImport

export default function FunctionGraph({ target, player }: FunctionGraphProps) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    let lastWidth = 0
    let frame = 0

    const render = () => {
      const width = Math.max(300, container.clientWidth)
      if (Math.abs(width - lastWidth) < 1 && container.childElementCount > 0) return
      lastWidth = width
      container.replaceChildren()
      const data: FunctionPlotDatum[] = [
        { fnType: 'points', graphType: 'polyline', points: target.map(({ x, y }) => [x, y]), color: '#111827', skipTip: true },
        { fnType: 'points', graphType: 'polyline', points: player.map(({ x, y }) => [x, y]), color: '#e44d26', skipTip: true },
      ]
      functionPlot({
        target: container,
        width,
        height: Math.max(340, Math.min(520, width * 0.64)),
        grid: true,
        disableZoom: false,
        xAxis: { domain: [-6, 6], label: 'x', position: 'sticky' },
        yAxis: { domain: [-12, 12], label: 'y', position: 'sticky' },
        data,
      })
    }

    const scheduleRender = () => {
      window.cancelAnimationFrame(frame)
      frame = window.requestAnimationFrame(render)
    }

    render()
    const observer = new ResizeObserver(scheduleRender)
    observer.observe(container)
    return () => {
      window.cancelAnimationFrame(frame)
      observer.disconnect()
    }
  }, [player, target])

  return <div ref={containerRef} className="graph-match-chart interactive" aria-label="Interactive function graph" />
}
