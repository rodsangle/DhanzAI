"use client";

import { ChatView } from "@/components/chat/chat-view";

// S03 New chat (home). Sending the first message turns this into S04 in place.
export default function HomePage() {
  return <ChatView key="home" />;
}
