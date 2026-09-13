export default function ProcessPicker({ processes, active, onPick }) {
  return (
    <nav className="picker">
      {processes.map((p) => {
        const pending = p.counts[p.states.pending] ?? 0
        return (
          <button
            key={p.label}
            className={p.label === active ? 'chip active' : 'chip'}
            onClick={() => onPick(p.label)}
          >
            <span className="jp">{p.display_name}</span>
            <span className="meta">
              {p.system.name} · {pending} pending
            </span>
          </button>
        )
      })}
    </nav>
  )
}
