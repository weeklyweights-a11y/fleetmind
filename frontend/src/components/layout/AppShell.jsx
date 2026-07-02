import { useEffect, useMemo, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { apiGet } from "../../api/client.js";
import { ChatProvider, useChat } from "../../context/ChatContext.jsx";
import { ProcessingQueueProvider } from "../../context/ProcessingQueueContext.jsx";
import { Header } from "./Header.jsx";
import { Sidebar } from "./Sidebar.jsx";
import { ChatSidebar } from "../chat/ChatSidebar.jsx";
import { UploadZone } from "../upload/UploadZone.jsx";
import { ProcessingQueue } from "../upload/ProcessingQueue.jsx";

function AppShellInner() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [reviewCount, setReviewCount] = useState(0);
  const { open: chatOpen, setOpen: setChatOpen } = useChat();
  const location = useLocation();

  const chatChips = useMemo(() => {
    const truckMatch = location.pathname.match(/^\/trucks\/(\d+)/);
    if (truckMatch) {
      const unit = truckMatch[1];
      return [
        "Why is this truck expensive?",
        "Compare with other trucks",
        `Show maintenance history for Unit ${unit}`,
      ];
    }
    return [];
  }, [location.pathname]);

  useEffect(() => {
    apiGet("/api/fleet/overview")
      .then((d) => setReviewCount(d.review_queue_count || 0))
      .catch(() => {});
  }, []);

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      <div className="flex-1 flex flex-col min-w-0">
        <Header
          onMenuClick={() => setSidebarOpen(true)}
          onUploadClick={() => setUploadOpen(true)}
          onChatToggle={() => setChatOpen(!chatOpen)}
          notificationCount={reviewCount}
          chatOpen={chatOpen}
        />
        <div className="flex flex-1 min-h-0">
          <main className="flex-1 overflow-y-auto">
            <Outlet />
          </main>
          <ChatSidebar contextChips={chatChips} />
        </div>
      </div>
      <UploadZone open={uploadOpen} onClose={() => setUploadOpen(false)} />
      <ProcessingQueue />
    </div>
  );
}

export function AppShell() {
  return (
    <ProcessingQueueProvider>
      <ChatProvider>
        <AppShellInner />
      </ChatProvider>
    </ProcessingQueueProvider>
  );
}
