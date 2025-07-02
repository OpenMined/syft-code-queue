"use client";

import { type React } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ThemeProvider } from "@/components/theme-provider";
import { DragDropProvider } from "@/components/drag-drop-context";
import { ModeToggle } from "@/components/mode-toggle";
import { Button } from "@/components/ui/button";
import { Code, Briefcase } from "lucide-react";

interface LayoutProps {
  children: React.ReactNode;
  showHeader?: boolean;
}

export function Layout({ children, showHeader = true }: LayoutProps) {
  const pathname = usePathname();
  const isJobs = pathname === "/" || pathname === "/jobs/";

  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
      <DragDropProvider>
        <div className="min-h-screen bg-background">
          {/* Header */}
          {showHeader && (
            <header className="border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
              <div className="container mx-auto px-4 py-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-4">
                    {/* SyftBox Logo */}
                    <div className="flex items-center space-x-2">
                      <Code className="h-8 w-8 text-primary" />
                      <span className="text-xl font-bold">Syft Code Queue UI</span>
                    </div>
                  </div>

                  <div className="flex items-center space-x-4">
                    <ModeToggle />
                  </div>
                </div>
              </div>
            </header>
          )}

          {/* Navigation */}
          <nav className="container animate-fade-in mx-auto px-4 py-8">
            <div className="flex space-x-1 bg-muted p-1 rounded-lg w-fit">
              <Link href="/">
                <Button
                  variant={isJobs ? "default" : "ghost"}
                  size="sm"
                  className="flex items-center space-x-2"
                >
                  <Briefcase className="h-4 w-4" />
                  <span>Job Browser</span>
                </Button>
              </Link>
            </div>
          </nav>

          {/* Main Content */}
          <main className="container mx-auto px-4 py-8">{children}</main>
        </div>
      </DragDropProvider>
    </ThemeProvider>
  );
}
