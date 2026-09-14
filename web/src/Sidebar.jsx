export default function Sidebar({ processes, active, onPick }) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <h1>Back-office Assist</h1>
        <p>Drafts each case. A person approves every one.</p>
      </div>

      <nav className="nav" aria-label="Processes">
        <div className="nav-label">Queues</div>
        {processes.map((p) => {
          const pending = p.pending ?? p.counts[p.states.pending] ?? 0
          const ready = p.ready ?? 0
          const review = Math.max(pending - ready, 0)
          const total = Math.max(pending, 1)
          return (
            <button
              key={p.label}
              className="nav-item"
              aria-current={p.label === active}
              onClick={() => onPick(p.label)}
            >
              <span className="row1">
                <span className="name jp">{p.display_name}</span>
                <span className="count num">{pending}</span>
              </span>
              <span className="sys jp">{p.system.name}</span>
              {pending > 0 && (
                <span
                  className="bar"
                  role="img"
                  aria-label={`${ready} ready, ${review} need review`}
                >
                  <i className="b-ready" style={{ width: `${(ready / total) * 100}%` }} />
                  <i className="b-review" style={{ width: `${(review / total) * 100}%` }} />
                </span>
              )}
            </button>
          )
        })}
      </nav>

      <div className="sidebar-foot">
        <kbd>J</kbd><kbd>K</kbd> move · <kbd>↵</kbd> approve · <kbd>E</kbd> edit
      </div>
    </aside>
  )
}
