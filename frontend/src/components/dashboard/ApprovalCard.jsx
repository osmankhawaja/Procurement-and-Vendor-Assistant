import { useEffect, useRef, useState } from "react";

import { getWorkflowState } from "../../services/api.js";

const ORDER_KEYS = [
  "purchase_order",
  "po_draft",
  "draft_po",
  "approval_request",
  "approval",
  "request",
  "value",
];

function purchaseOrderFrom(details, seen = new WeakSet()) {
  if (!details || typeof details !== "object" || Array.isArray(details)) {
    return null;
  }
  if (seen.has(details)) {
    return null;
  }
  seen.add(details);

  if (Array.isArray(details.items)) {
    return details;
  }
  for (const key of ORDER_KEYS) {
    const found = purchaseOrderFrom(details[key], seen);
    if (found) {
      return found;
    }
  }
  return null;
}

function defaultFormatCurrency(amount, currency = "USD") {
  const numeric = Number(amount);
  const safeAmount = Number.isFinite(numeric) ? numeric : 0;
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency: currency || "USD",
    }).format(safeAmount);
  } catch {
    return `${currency || "USD"} ${safeAmount.toFixed(2)}`;
  }
}

function DefaultIcon({ size = 18 }) {
  return (
    <span aria-hidden="true" style={{ fontSize: size }}>
      •
    </span>
  );
}

export default function ApprovalCard({
  item,
  busy = false,
  onDecision,
  IconComponent = DefaultIcon,
  formatCurrency = defaultFormatCurrency,
}) {
  const safeItem = item && typeof item === "object" ? item : {};
  const [order, setOrder] = useState(() => purchaseOrderFrom(safeItem.details));
  const [orderLoading, setOrderLoading] = useState(false);
  const [orderError, setOrderError] = useState("");
  const mountedRef = useRef(true);
  const activeThreadIdRef = useRef(safeItem.thread_id);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    const threadChanged = activeThreadIdRef.current !== safeItem.thread_id;
    activeThreadIdRef.current = safeItem.thread_id;
    const initialOrder = purchaseOrderFrom(safeItem.details);
    if (threadChanged || initialOrder) {
      setOrder(initialOrder);
      setOrderError("");
    }
  }, [safeItem.thread_id, safeItem.details]);

  const requester =
    order?.requester_name || order?.department || "Procurement request";
  const orderItems = Array.isArray(order?.items) ? order.items : [];
  const formatMoney =
    typeof formatCurrency === "function"
      ? formatCurrency
      : defaultFormatCurrency;

  async function loadOrderDetails() {
    if (!safeItem.thread_id) {
      setOrderError("Missing workflow thread ID.");
      return;
    }
    const requestedThreadId = safeItem.thread_id;
    setOrderLoading(true);
    setOrderError("");
    try {
      const state = await getWorkflowState(requestedThreadId);
      const foundOrder = purchaseOrderFrom(state?.values ?? state);
      if (!foundOrder) {
        throw new Error(
          "No purchase order details were found for this workflow.",
        );
      }
      if (
        mountedRef.current &&
        activeThreadIdRef.current === requestedThreadId
      ) {
        setOrder(foundOrder);
      }
    } catch (error) {
      if (
        mountedRef.current &&
        activeThreadIdRef.current === requestedThreadId
      ) {
        setOrderError(
          error instanceof Error
            ? error.message
            : "Unable to load purchase order details.",
        );
      }
    } finally {
      if (
        mountedRef.current &&
        activeThreadIdRef.current === requestedThreadId
      ) {
        setOrderLoading(false);
      }
    }
  }

  function handleDecision(action) {
    if (typeof onDecision === "function") {
      onDecision(safeItem, action);
    }
  }

  return (
    <article className="approval-card">
      <div className="approval-card-top">
        <span className="approval-icon">
          <IconComponent name="clock" size={18} />
        </span>
        <div className="approval-title">
          <span className="eyebrow">AWAITING REVIEW</span>
          <h3>{requester}</h3>
        </div>
        <span className="status-tag status-pending">
          {safeItem.status || "Pending"}
        </span>
      </div>
      {order ? (
        <div className="approval-order">
          <div className="approval-order-meta">
            <span>{order.po_id || "Purchase order draft"}</span>
            {order.cost_center_id && <span>{order.cost_center_id}</span>}
          </div>
          <div className="approval-items">
            {orderItems.slice(0, 3).map((line, index) => (
              <div
                key={`${line?.product_id || line?.item_name || "item"}-${index}`}
              >
                <span>
                  {line?.item_name || line?.product_id || "Catalog item"}
                </span>
                <span>×{line?.quantity || 1}</span>
              </div>
            ))}
            {orderItems.length > 3 && (
              <span className="muted-copy">
                +{orderItems.length - 3} more items
              </span>
            )}
          </div>
          <div className="approval-total">
            <span>Estimated total</span>
            <strong>
              {formatMoney(order.total_amount, order.currency || "USD")}
            </strong>
          </div>
        </div>
      ) : (
        <div className="approval-order approval-details-missing">
          <p className="muted-copy">
            Load the request state to review its purchase details.
          </p>
          {orderError && (
            <p className="inline-alert" role="alert">
              {orderError}
            </p>
          )}
          <button
            className="quiet-button"
            type="button"
            onClick={() => void loadOrderDetails()}
            disabled={orderLoading}
          >
            {orderLoading ? "Loading details..." : "Load purchase details"}
          </button>
        </div>
      )}
      <div className="approval-card-footer">
        <div className="thread-reference">
          <span>THREAD</span>
          <code title={safeItem.thread_id || ""}>
            {safeItem.thread_id || "Unknown thread"}
          </code>
        </div>
        <div className="approval-actions">
          <button
            className="decision-button decision-reject"
            type="button"
            disabled={busy || !order}
            onClick={() => handleDecision("reject")}
            title={!order ? "Load purchase details before deciding" : undefined}
          >
            Reject
          </button>
          <button
            className="decision-button decision-approve"
            type="button"
            disabled={busy || !order}
            onClick={() => handleDecision("approve")}
            title={!order ? "Load purchase details before deciding" : undefined}
          >
            {busy ? "Saving..." : "Approve"}
          </button>
        </div>
      </div>
    </article>
  );
}
