import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { DashboardProvider } from "@/context/DashboardContext";
import { DashboardLayout } from "@/components/layout/DashboardLayout";

const inter = Inter({ subsets: ["latin"], variable: "--font-sans" });

export const metadata: Metadata = {
  title: "TradeAX Copilot | AI 무역·수출 영업 어시스턴트",
  description: "글로벌 무역 및 수출 영업 전문가를 위한 AI 어시스턴트",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko" className={inter.variable}>
      <body className="min-h-screen bg-gray-50 font-sans">
        <DashboardProvider>
          <DashboardLayout>{children}</DashboardLayout>
        </DashboardProvider>
      </body>
    </html>
  );
}
