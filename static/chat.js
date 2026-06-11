// Chat page logic: keeps the conversation history and talks to /api/chat.

const chatBox = document.getElementById("chat-box");
const form = document.getElementById("chat-form");
const input = document.getElementById("chat-input");
const sendBtn = document.getElementById("chat-send");

// Full conversation so the AI remembers earlier questions.
const messages = [];

function addBubble(text, who) {
  const div = document.createElement("div");
  div.className = "msg " + who;
  div.textContent = text;
  chatBox.appendChild(div);
  chatBox.scrollTop = chatBox.scrollHeight;
  return div;
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const question = input.value.trim();
  if (!question) return;

  addBubble(question, "user");
  messages.push({ role: "user", content: question });
  input.value = "";
  input.disabled = true;
  sendBtn.disabled = true;

  const thinking = addBubble("Thinking...", "assistant thinking");

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages }),
    });
    const data = await res.json();
    thinking.remove();

    if (!res.ok) {
      addBubble(data.error || "Something went wrong. Please try again.", "assistant error");
      // Drop the failed question so the history stays valid.
      messages.pop();
    } else {
      addBubble(data.reply, "assistant");
      messages.push({ role: "assistant", content: data.reply });
    }
  } catch (err) {
    thinking.remove();
    addBubble("Could not reach the app. Is it still running?", "assistant error");
    messages.pop();
  } finally {
    input.disabled = false;
    sendBtn.disabled = false;
    input.focus();
  }
});
