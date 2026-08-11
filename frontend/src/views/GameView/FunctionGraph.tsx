import { useEffect, useRef } from 'react'
import functionPlotImport from 'function-plot'
import type { FunctionPlotDatum } from 'function-plot'
import type { GraphPoint } from '../../clients/games/GraphMatchClient'

interface FunctionGraphProps {
  target: GraphPoint[]
  player: GraphPoint[]
  agent?: GraphPoint[]
}

const functionPlot = (
  functionPlotImport as typeof functionPlotImport & { default?: typeof functionPlotImport }
).default ?? functionPlotImport

export default function FunctionGraph({ target, player, agent = [] }: FunctionGraphProps) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const render = () => {
      const width = Math.max(300, container.clientWidth)
      container.replaceChildren()
      const data: FunctionPlotDatum[] = [
        { fnType: 'points', graphType: 'polyline', points: target.map(({ x, y }) => [x, y]), color: '#111827', skipTip: true },
        { fnType: 'points', graphType: 'polyline', points: player.map(({ x, y }) => [x, y]), color: '#e44d26', skipTip: true },
      ]
      if (agent.length) {
        data.push({ fnType: 'points', graphType: 'polyline', points: agent.map(({ x, y }) => [x, y]), color: '#168a79', skipTip: true })
      }
      functionPlot({
        target: container,
        width,
        height: Math.max(340, Math.min(520, width * 0.64)),
        grid: true,
        disableZoom: true,
        xAxis: { domain: [-4, 4], label: 'x', position: 'sticky' },
        yAxis: { domain: [-8, 12], label: 'y', position: 'sticky' },
        data,
      })
    }

    render()
    const observer = new ResizeObserver(render)
    observer.observe(container)
    return () => observer.disconnect()
  }, [agent, player, target])

  return <div ref={containerRef} className="graph-match-chart" aria-label="Exponential function graph" />
}
