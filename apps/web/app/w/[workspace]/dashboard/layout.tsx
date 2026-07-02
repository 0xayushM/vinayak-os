import type { Metadata } from "next";
import { Sidebar } from "@/components/dashboard/Sidebar";
import OnboardingGate from "@/components/dashboard/OnboardingGate";
import { SyncProgressBanner } from "@/components/dashboard/SyncProgressBanner";
import { NotificationsProvider } from "@/components/notifications/NotificationsProvider";
import { NotificationBell } from "@/components/notifications/NotificationBell";
import { ToastHost } from "@/components/notifications/ToastHost";
import { SyncWatcher } from "@/components/notifications/SyncWatcher";
import { SyncOnLogin } from "@/components/dashboard/SyncOnLogin";
import { ChatDockProvider } from "@/components/dashboard/ChatDock";

export const metadata: Metadata = {
  title: "Brain OS",
  description: "Business intelligence dashboard powered by TranzAct",
};

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <NotificationsProvider>
      <ChatDockProvider>
        <div className="flex h-screen overflow-hidden text-[#F2DEC8]">
          <Sidebar />
          <main className="flex-1 overflow-auto flex flex-col relative z-10 pt-12 lg:pt-0">
            <SyncProgressBanner />
            <OnboardingGate>{children}</OnboardingGate>
          </main>
        </div>
        {/* Global notification surfaces + the watcher that feeds them. */}
        <NotificationBell />
        <ToastHost />
        <SyncWatcher />
        <SyncOnLogin />
      </ChatDockProvider>
    </NotificationsProvider>
  );
}
