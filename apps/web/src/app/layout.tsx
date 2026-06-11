import type { Metadata } from "next";

import { Providers } from "@/app/providers";
import "./globals.css";

export const metadata: Metadata = {
  title: "ContactGraph",
  description: "Your private, agent-native contact graph",
  metadataBase: new URL("https://contactgraph.ai"),
  openGraph: {
    title: "ContactGraph",
    description:
      "Keep track of who you know professionally. Share your network with trusted friends — names and roles only, never emails.",
    siteName: "ContactGraph",
    type: "website",
    url: "https://contactgraph.ai",
  },
  twitter: {
    card: "summary",
    title: "ContactGraph",
    description:
      "Keep track of who you know professionally. Share your network with trusted friends — names and roles only, never emails.",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased">
      <body
        suppressHydrationWarning
        className="min-h-full flex flex-col bg-background text-foreground"
      >
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
