import type { Metadata } from "next";
import { Sidebar } from "@/components/dashboard/Sidebar";
import OnboardingGate from "@/components/dashboard/OnboardingGate";
import { SyncProgressBanner } from "@/components/dashboard/SyncProgressBanner";

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
    <div className="flex h-screen overflow-hidden text-[#F2DEC8]">
      <Sidebar />
      <main className="flex-1 overflow-auto flex flex-col relative z-10 pt-12 lg:pt-0">
        <SyncProgressBanner />
        <OnboardingGate>{children}</OnboardingGate>
      </main>
    </div>
  );
}
