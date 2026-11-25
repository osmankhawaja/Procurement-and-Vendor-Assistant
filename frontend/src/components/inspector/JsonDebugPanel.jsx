function formatJson(value) {
  if (value === undefined) return "null";
  try {
    const serialized = JSON.stringify(value, null, 2);
    return serialized ?? "null";
  } catch (error) {
    return JSON.stringify(
      {
        serialization_error:
          error instanceof Error ? error.message : "Unable to serialize value",
      },
      null,
      2,
    );
  }
}

export default function JsonDebugPanel({ snapshot }) {
  if (!snapshot || typeof snapshot !== "object" || Array.isArray(snapshot)) {
    return null;
  }

  const nextNodes = Array.isArray(snapshot.next)
    ? snapshot.next.filter(Boolean).map(String)
    : [];

  const sections = [
    { title: "State values", value: snapshot.values ?? null, open: true },
    {
      title: "Tasks and metadata",
      value: {
        tasks: snapshot.tasks ?? [],
        metadata: snapshot.metadata ?? {},
      },
      open: false,
    },
  ];

  return (
    <div className="snapshot-results">
      <div className="snapshot-summary">
        <span>
          Thread <code>{snapshot.thread_id || "unknown"}</code>
        </span>
        <span>
          Next: {nextNodes.length > 0 ? nextNodes.join(", ") : "Complete"}
        </span>
      </div>
      {sections.map(({ title, value, open }) => (
        <details key={title} open={open}>
          <summary>{title}</summary>
          <pre>
            <code>{formatJson(value)}</code>
          </pre>
        </details>
      ))}
    </div>
  );
}