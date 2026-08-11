import { useMemo, useState } from 'react'
import { CornerDownLeft, Delete } from 'lucide-react'
import { parse } from 'mathjs'
import MathFormula from './MathFormula'

interface ExpressionKeypadProps {
  value: string
  onChange: (value: string) => void
  onSubmit: () => void
  disabled?: boolean
}

const numberKeys = [
  ['x', 'pi', 'e', '(', ')'],
  ['7', '8', '9', '*', '/'],
  ['4', '5', '6', '+', '-'],
  ['1', '2', '3', '^', '.'],
  ['0', '^2', 'sqrt(', 'abs(', ','],
]

const functionKeys = [
  ['sin(', 'cos(', 'tan('],
  ['log(', 'ln(', 'sqrt('],
  ['x', 'pi', 'e'],
  ['(', ')', '^'],
]

export default function ExpressionKeypad({ value, onChange, onSubmit, disabled }: ExpressionKeypadProps) {
  const [tab, setTab] = useState<'numbers' | 'functions'>('numbers')
  const latex = useMemo(() => {
    try {
      return `f(x)=${parse(value || '0').toTex({ parenthesis: 'keep' })}`
    } catch {
      return 'f(x)=?'
    }
  }, [value])
  const keys = tab === 'numbers' ? numberKeys : functionKeys

  const insert = (token: string) => {
    onChange(`${value}${token}`.slice(0, 120))
  }

  return (
    <section className="expression-calculator" aria-label="Function calculator">
      <div className="expression-preview"><MathFormula latex={latex} block /></div>
      <input
        value={value}
        onChange={event => onChange(event.target.value)}
        placeholder="Enter a function of x"
        spellCheck={false}
        aria-label="Function expression"
        disabled={disabled}
      />
      <div className="calculator-tabs" role="tablist">
        <button className={tab === 'numbers' ? 'active' : ''} onClick={() => setTab('numbers')} role="tab">123</button>
        <button className={tab === 'functions' ? 'active' : ''} onClick={() => setTab('functions')} role="tab">f(x)</button>
      </div>
      <div className={`calculator-grid ${tab}`}>
        {keys.flat().map((key, index) => (
          <button key={`${key}-${index}`} onClick={() => insert(key)} disabled={disabled}>{key}</button>
        ))}
        <button className="calculator-command" onClick={() => onChange(value.slice(0, -1))} disabled={disabled} aria-label="Backspace" title="Backspace"><Delete size={19} /></button>
        <button className="calculator-command clear" onClick={() => onChange('')} disabled={disabled}>AC</button>
        <button className="calculator-command enter" onClick={onSubmit} disabled={disabled || !value.trim()} aria-label="Submit function" title="Submit function"><CornerDownLeft size={20} /></button>
      </div>
    </section>
  )
}
