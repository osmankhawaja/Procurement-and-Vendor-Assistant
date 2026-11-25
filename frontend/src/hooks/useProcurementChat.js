import { useCallback, useRef, useState } from "react";
import { sendChatMessage } from "../services/api.js";

function createWelcomeMessage() {
  return {
    id: "welcome",
    role: "assistant",
    time: new Date(),
    text: "Welcome. Tell me what your team needs, and I can help find approved vendors, check procurement policy, and prepare a purchase order for review.",
  };
}

export default function useProcurementChat() {
  const [threadId, setThreadId] = useState("");
  const [messages, setMessages] = useState(() => [createWelcomeMessage()]);
  const [prompt, setPrompt] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState("");
  const sendingRef = useRef(false);
  const messageSequence = useRef(0);
  const conversationGenerationRef = useRef(0);

  const nextMessageId = useCallback((role) => {
    messageSequence.current += 1;
    return `${role}-${Date.now()}-${messageSequence.current}`;
  }, []);

  const sendMessage = useCallback(
    async (value) => {
      const message = typeof value === "string" ? value.trim() : "";
      if (!message || sendingRef.current) return;

      sendingRef.current = true;
      const activeGeneration = conversationGenerationRef.current;
      const activeThreadId = threadId;

      setError("");
      setPrompt("");
      const userMessage = {
        id: nextMessageId("user"),
        role: "user",
        text: message,
        time: new Date(),
      };
      setMessages((current) => [...current, userMessage]);
      setIsSending(true);

      try {
        const result = await sendChatMessage({
          message,
          threadId: activeThreadId || undefined,
        });
        if (conversationGenerationRef.current !== activeGeneration) {
          return;
        }

        const payload = result && typeof result === "object" ? result : {};
        if (typeof payload.thread_id === "string" && payload.thread_id.trim()) {
          setThreadId(payload.thread_id.trim());
        }

        const assistantMessage = {
          id: nextMessageId("assistant"),
          role: "assistant",
          time: new Date(),
          text:
            payload.response ||
            (payload.status === "waiting_for_approval"
              ? "This request is paused for manager approval."
              : "The workflow completed. Review the purchase details below."),
          status: payload.status,
          citations: payload.citations,
          purchaseOrder: payload.purchase_order,
        };
        setMessages((current) => [...current, assistantMessage]);
      } catch (sendError) {
        if (conversationGenerationRef.current !== activeGeneration) {
          return;
        }
        setError(
          sendError instanceof Error
            ? sendError.message
            : "Unable to send the request. Check the backend connection and try again.",
        );
      } finally {
        if (conversationGenerationRef.current === activeGeneration) {
          sendingRef.current = false;
          setIsSending(false);
        }
      }
    },
    [nextMessageId, threadId],
  );

  const startNewConversation = useCallback(() => {
    conversationGenerationRef.current += 1;
    sendingRef.current = false;
    setIsSending(false);
    setThreadId("");
    setMessages([createWelcomeMessage()]);
    setPrompt("");
    setError("");
  }, []);

  return {
    threadId,
    messages,
    prompt,
    setPrompt,
    isSending,
    error,
    sendMessage,
    startNewConversation,
  };
}
