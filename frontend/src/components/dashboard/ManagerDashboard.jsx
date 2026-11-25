import ApprovalCard from "./ApprovalCard.jsx";

function DefaultIcon({ size = 18 }) {
  return (
    <span aria-hidden="true" style={{ fontSize: size }}>
      •
    </span>
  );
}

export default function ManagerDashboard({
  approvals = [],
  loading = false,
  error = "",
  notice = "",
  workingThread = null,
  onRefresh,
  onDecision,
  IconComponent = DefaultIcon,
  formatCurrency,
}) {
  const list = Array.isArray(approvals) ? approvals : [];
  const count = list.length;

  return (
    <section className="approvals-view" aria-label="Manager approval queue">
      <div className="approval-summary">
        <div className="summary-icon">
          <IconComponent name="check" size={21} />
        </div>
        <div>
          <strong>{count}</strong>
          <span>
            {count === 1 ? "request needs" : "requests need"} your review
          </span>
        </div>
        <span className="summary-note">
          Decisions resume the procurement workflow.
        </span>
      </div>
      {notice && (
        <div className="success-alert" role="status">
          {notice}
        </div>
      )}
      {error && (
        <div className="inline-alert" role="alert">
          {error}
        </div>
      )}
      {loading ? (
        <div className="empty-state">
          <span className="loader" /> Loading approval queue...
        </div>
      ) : error && count === 0 ? (
        <div className="empty-state">
          <h2>Approval queue unavailable</h2>
          <p>
            Resolve the connection issue above, then try loading the queue
            again.
          </p>
          <button
            className="quiet-button"
            type="button"
            onClick={onRefresh}
            disabled={typeof onRefresh !== "function"}
          >
            <IconComponent name="refresh" size={16} /> Retry
          </button>
        </div>
      ) : count === 0 ? (
        <div className="empty-state">
          <span className="empty-icon">
            <IconComponent name="check" size={23} />
          </span>
          <h2>All caught up</h2>
          <p>There are no pending approvals in the workflow right now.</p>
          <button
            className="quiet-button"
            type="button"
            onClick={onRefresh}
            disabled={typeof onRefresh !== "function"}
          >
            <IconComponent name="refresh" size={16} /> Refresh queue
          </button>
        </div>
      ) : (
        <div className="approval-grid">
          {list.map((item, index) => {
            const threadId = item?.thread_id;
            return (
              <ApprovalCard
                item={item}
                key={threadId ?? `approval-${index}`}
                busy={Boolean(threadId && workingThread === threadId)}
                onDecision={onDecision}
                IconComponent={IconComponent}
                formatCurrency={formatCurrency}
              />
            );
          })}
        </div>
      )}
      {count > 0 && (
        <p className="approval-footnote">
          Confirm each request against your organization’s procurement policy
          before deciding.
        </p>
      )}
    </section>
  );
}
