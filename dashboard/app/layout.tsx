import "./globals.css";

import type { ReactNode } from "react";

import Sidebar from "../components/Sidebar";

export const metadata = {
  title: "Compliance Dashboard",
  description: "Internal compliance digest dashboard"
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="layout">
          <aside className="sidebar">
            <div className="brand">
              <h1>Compliance Digest</h1>
            </div>
            <Sidebar />
          </aside>
          <main className="main">{children}</main>
        </div>
      </body>
    </html>
  );
}

