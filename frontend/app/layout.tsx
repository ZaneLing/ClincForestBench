import type { Metadata } from 'next';
import { Geist, Geist_Mono } from 'next/font/google';
import { ApplicationShell } from '@/components/application-shell';
import { AuthProvider } from '@/features/auth/auth-context';
import './globals.css';

const geistSans = Geist({
  variable: '--font-geist-sans',
  subsets: ['latin'],
});

const geistMono = Geist_Mono({
  variable: '--font-geist-mono',
  subsets: ['latin'],
});

export const metadata: Metadata = {
  title: 'ClincForestBench',
  description:
    'An evidence-locked clinical reasoning arena and diagnostic forest benchmark.',
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        <AuthProvider>
          <ApplicationShell>{children}</ApplicationShell>
        </AuthProvider>
      </body>
    </html>
  );
}
