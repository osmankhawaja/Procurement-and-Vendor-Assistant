import CitationDrawer from "./CitationDrawer.jsx";

function formatTime(value = new Date()) {
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return new Intl.DateTimeFormat(undefined, {
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function fallbackFormatCurrency(amount, currency = "USD") {
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

function PurchaseOrderSummary({ order, formatCurrency }) {
  if (!order || typeof order !== "object" || !Array.isArray(order.items))
    return null;
  const currency = order.currency || "USD";
  const formatMoney =
    typeof formatCurrency === "function"
      ? formatCurrency
      : fallbackFormatCurrency;

  const computedItemsTotal = order.items.reduce((sum, item) => {
    const qty = Number(item?.quantity ?? 1);
    const price = Number(item?.unit_price ?? 0);
    const lineTotal =
      item?.line_total !== undefined && item?.line_total !== null
        ? Number(item.line_total)
        : (Number.isFinite(qty) ? qty : 1) *
          (Number.isFinite(price) ? price : 0);
    return sum + (Number.isFinite(lineTotal) ? lineTotal : 0);
  }, 0);

  const orderTotal =
    order.total_amount !== undefined &&
    order.total_amount !== null &&
    Number.isFinite(Number(order.total_amount))
      ? Number(order.total_amount)
      : computedItemsTotal;

  return (
    <section className="purchase-order-card" aria-label="Purchase order draft">
      <div className="po-card-heading">
        <div>
          <span className="eyebrow">Purchase order</span>
          <strong>{order.po_id || "Draft for review"}</strong>
        </div>
        {order.status && <span className="status-tag">{order.status}</span>}
      </div>
      {(order.department || order.cost_center_id) && (
        <p className="po-meta">
          {[order.department, order.cost_center_id].filter(Boolean).join(" · ")}
        </p>
      )}
      <div className="po-items">
        {order.items.map((item, index) => {
          const itemCurrency = item?.currency || currency;
          const qty = Number(item?.quantity ?? 1);
          const unitPrice = Number(item?.unit_price ?? 0);
          const safeQty = Number.isFinite(qty) ? qty : 1;
          const safeUnitPrice = Number.isFinite(unitPrice) ? unitPrice : 0;
          const lineTotal =
            item?.line_total !== undefined &&
            item?.line_total !== null &&
            Number.isFinite(Number(item.line_total))
              ? Number(item.line_total)
              : safeQty * safeUnitPrice;

          return (
            <div
              className="po-item"
              key={`${item?.product_id || item?.item_name || "item"}-${index}`}
            >
              <div>
                <strong>
                  {item?.item_name || item?.product_id || "Catalog item"}
                </strong>
                <span>
                  {safeQty} × {formatMoney(safeUnitPrice, itemCurrency)}
                </span>
              </div>
              <span className="po-line-total">
                {formatMoney(lineTotal, itemCurrency)}
              </span>
            </div>
          );
        })}
      </div>
      <div className="po-total">
        <span>Estimated total</span>
        <strong>{formatMoney(orderTotal, currency)}</strong>
      </div>
    </section>
  );
}

export default function MessageBubble({
  message,
  IconComponent,
  formatCurrency,
}) {
  if (!message || typeof message !== "object") return null;
  const isAssistant = message.role === "assistant";
  const formattedTime = formatTime(message.time);

  return (
    <article
      className={`message-row ${isAssistant ? "message-assistant" : "message-user"}`}
    >
      {isAssistant && IconComponent && (
        <span className="message-avatar">
          <IconComponent name="brand" size={16} />
        </span>
      )}
      <div className="message-content">
        <div className="message-meta">
          <strong>{isAssistant ? "Procurement assistant" : "You"}</strong>
          {formattedTime && <time>{formattedTime}</time>}
          {message.status === "waiting_for_approval" && (
            <span className="message-status">Manager review</span>
          )}
        </div>
        <div className="message-bubble">{message.text}</div>
        {message.purchaseOrder && (
          <PurchaseOrderSummary
            order={message.purchaseOrder}
            formatCurrency={formatCurrency}
          />
        )}
        {isAssistant && <CitationDrawer citations={message.citations} />}
      </div>
    </article>
  );
}
