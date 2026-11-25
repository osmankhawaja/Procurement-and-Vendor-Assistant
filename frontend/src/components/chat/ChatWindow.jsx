import { useEffect, useRef } from "react";
import MessageBubble from "./MessageBubble.jsx";

const suggestions = [
  "Find approved laptops for the Engineering team",
  "What policies apply to SaaS procurement?",
  "Help me draft a purchase order for Business Laptop",
];

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

function DefaultIcon({ size = 16 }) {
  return (
    <span aria-hidden="true" style={{ fontSize: size }}>
      •
    </span>
  );
}

export default function ChatWindow({
  messages = [],
  threadId = "",
  isSending = false,
  error = "",
  prompt = "",
  setPrompt,
  onSubmit,
  onNewConversation,
  IconComponent = DefaultIcon,
  formatCurrency = defaultFormatCurrency,
}) {
  const conversationScroll = useRef(null);

  useEffect(() => {
    const conversation = conversationScroll.current;
    if (!conversation) return;
    const distanceFromBottom =
      conversation.scrollHeight -
      conversation.scrollTop -
      conversation.clientHeight;
    if (distanceFromBottom < 140 || messages.length <= 1) {
      conversation.scrollTo({
        top: conversation.scrollHeight,
        behavior: "smooth",
      });
    }
  }, [messages.length, isSending]);

  function handleKeyDown(event) {
    if (
      event.key === "Enter" &&
      !event.shiftKey &&
      !event.nativeEvent?.isComposing
    ) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  }

  function handleFormSubmit(event) {
    event.preventDefault();
    if (typeof onSubmit === "function") {
      onSubmit(prompt);
    }
  }

  return (
    <div className="assistant-layout">
      <section className="chat-panel" aria-label="Procurement conversation">
        <div className="chat-toolbar">
          <div className="chat-thread">
            <span className="thread-indicator" aria-hidden="true" />
            <span>{threadId ? "Active request" : "New request"}</span>
            {threadId && <code title={threadId}>{threadId}</code>}
          </div>
          <button
            className="quiet-button"
            type="button"
            onClick={onNewConversation}
            disabled={isSending || typeof onNewConversation !== "function"}
          >
            <IconComponent name="plus" size={16} />
            New conversation
          </button>
        </div>

        <div className="conversation-scroll" ref={conversationScroll}>
          <div className="conversation-inner">
            {messages.map((message, index) => (
              <MessageBubble
                key={message?.id ?? `msg-${index}`}
                message={message}
                IconComponent={IconComponent}
                formatCurrency={formatCurrency}
              />
            ))}
            {isSending && (
              <div
                className="typing-indicator"
                role="status"
                aria-label="Assistant is responding"
              >
                <span className="message-avatar">
                  <IconComponent name="brand" size={16} />
                </span>
                <span className="typing-dots" aria-hidden="true">
                  <i />
                  <i />
                  <i />
                </span>
                <span>Checking your request</span>
              </div>
            )}
          </div>
        </div>

        <div className="composer-wrap">
          {error && (
            <div className="inline-alert" role="alert">
              {error}
            </div>
          )}
          {messages.length === 1 &&
            !isSending &&
            typeof onSubmit === "function" && (
              <div
                className="suggestion-row"
                aria-label="Suggested procurement requests"
              >
                {suggestions.map((suggestion) => (
                  <button
                    type="button"
                    className="suggestion-chip"
                    key={suggestion}
                    onClick={() => onSubmit(suggestion)}
                  >
                    {suggestion}
                    <IconComponent name="arrow" size={14} />
                  </button>
                ))}
              </div>
            )}
          <form className="composer" onSubmit={handleFormSubmit}>
            <label className="visually-hidden" htmlFor="procurement-message">
              Describe the purchase or procurement question
            </label>
            <textarea
              id="procurement-message"
              value={prompt}
              onChange={(event) => setPrompt?.(event.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Describe what you need, or ask about procurement policy..."
              rows={2}
              maxLength={10000}
              disabled={isSending}
            />
            <div className="composer-footer">
              <span>
                AI responses are grounded in your policies and approved catalog.
              </span>
              <button
                className="send-button"
                type="submit"
                disabled={isSending || !String(prompt).trim()}
                aria-label="Send procurement request"
              >
                <span>{isSending ? "Working..." : "Send request"}</span>
                <IconComponent name="send" size={16} />
              </button>
            </div>
          </form>
          <p className="composer-disclaimer">
            Review generated purchase details before submitting or approving an
            order.
          </p>
        </div>
      </section>

      <aside className="context-rail" aria-label="Procurement context">
        <div className="context-card context-card-highlight">
          <span className="context-icon">
            <IconComponent name="brand" size={18} />
          </span>
          <div className="eyebrow">YOUR PROCUREMENT COPILOT</div>
          <h2>From request to review</h2>
          <p>
            Get help finding approved suppliers, checking policy, and preparing
            purchase details.
          </p>
          <div className="context-divider" />
          <ul className="capability-list">
            <li>
              <span className="capability-check">✓</span> Approved vendor
              lookups
            </li>
            <li>
              <span className="capability-check">✓</span> Policy references with
              citations
            </li>
            <li>
              <span className="capability-check">✓</span> Purchase order drafts
            </li>
            <li>
              <span className="capability-check">✓</span> Human approval routing
            </li>
          </ul>
        </div>
        <div className="context-card thread-card">
          <div className="card-title-row">
            <div>
              <div className="eyebrow">CURRENT THREAD</div>
              <h3>{threadId ? "Request in progress" : "No request started"}</h3>
            </div>
            <IconComponent name="clock" size={18} />
          </div>
          <p>
            {threadId
              ? "This conversation is linked to a workflow thread. You can inspect its latest state from the workflow inspector."
              : "Start a conversation to create a traceable procurement workflow."}
          </p>
          {threadId && <code className="thread-code">{threadId}</code>}
        </div>
        <div className="privacy-note">
          <IconComponent name="check" size={16} />
          <span>
            Keep sensitive information out of chat. Requests are checked against
            configured safeguards.
          </span>
        </div>
      </aside>
    </div>
  );
}
