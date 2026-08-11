import { useEffect, useRef } from 'react'
import katex from 'katex'

interface MathFormulaProps {
  latex: string
  block?: boolean
}

export default function MathFormula({ latex, block = false }: MathFormulaProps) {
  const containerRef = useRef<HTMLSpanElement>(null)

  useEffect(() => {
    if (!containerRef.current) return
    katex.render(latex, containerRef.current, {
      displayMode: block,
      throwOnError: false,
      strict: false,
    })
  }, [block, latex])

  return <span ref={containerRef} className={block ? 'math-formula block' : 'math-formula'} />
}
