"use client";

import { useEffect, useState } from "react";
import { apiService, AllowlistResponse, StatusResponse } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Plus, X, Loader2, Settings, Users, Shield } from "lucide-react";

export function AllowlistView() {
  const [allowlistEmails, setAllowlistEmails] = useState<string[]>([]);
  const [newEmail, setNewEmail] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState<StatusResponse | null>(null);

  useEffect(() => {
    loadAllowlist();
    loadStatus();
  }, []);

  const loadStatus = async () => {
    try {
      const statusData = await apiService.getStatus();
      setStatus(statusData);
    } catch (error) {
      console.error("Failed to load status:", error);
    }
  };

  const loadAllowlist = async () => {
    try {
      const { emails } = await apiService.getAllowlist();
      setAllowlistEmails(emails);
    } catch (error) {
      console.error("Failed to load allowlist:", error);
    } finally {
      setLoading(false);
    }
  };

  const addEmail = async () => {
    if (!newEmail || allowlistEmails.includes(newEmail)) return;

    setIsLoading(true);
    try {
      const updatedList = [...allowlistEmails, newEmail];
      await apiService.updateAllowlist(updatedList);
      setAllowlistEmails(updatedList);
      setNewEmail("");
    } catch (error) {
      console.error("Failed to update allowlist:", error);
    } finally {
      setIsLoading(false);
    }
  };

  const removeEmail = async (email: string) => {
    setIsLoading(true);
    try {
      const updatedList = allowlistEmails.filter((e) => e !== email);
      await apiService.updateAllowlist(updatedList);
      setAllowlistEmails(updatedList);
    } catch (error) {
      console.error("Failed to update allowlist:", error);
    } finally {
      setIsLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="space-y-4">
        <Card className="animate-pulse">
          <CardHeader>
            <div className="h-6 bg-muted rounded w-1/3"></div>
            <div className="h-4 bg-muted rounded w-2/3"></div>
          </CardHeader>
          <CardContent>
            <div className="h-20 bg-muted rounded"></div>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="container mx-auto py-8 space-y-6">
      <div>
        <h1 className="text-3xl font-bold flex items-center">
          <Shield className="mr-3 h-8 w-8" />
          Syft Reviewer Allowlist
        </h1>
        <p className="text-muted-foreground mt-2">
          Manage trusted senders for automatic job approval
        </p>
      </div>

      {/* Status Card */}
      {status && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center">
              <Settings className="mr-2 h-5 w-5" />
              Application Status
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <span className="font-medium">Version:</span> {status.version}
              </div>
              <div>
                <span className="font-medium">User:</span> {status.syftbox.user_email}
              </div>
              <div>
                <span className="font-medium">Backend:</span>{" "}
                <Badge variant="outline" className="ml-1">
                  {status.components.backend}
                </Badge>
              </div>
              <div>
                <span className="font-medium">Allowlist:</span>{" "}
                <Badge variant="outline" className="ml-1">
                  {status.components.allowlist}
                </Badge>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Allowlist Management Card */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center">
            <Users className="mr-2 h-5 w-5" />
            Trusted Senders Allowlist
          </CardTitle>
          <CardDescription>
            Emails in this list will have their code jobs automatically approved
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Add Email Section */}
          <div className="flex space-x-2">
            <div className="flex-1">
              <Label htmlFor="email">Add trusted email address</Label>
              <Input
                id="email"
                placeholder="trusted@example.com"
                value={newEmail}
                type="email"
                autoComplete="off"
                onChange={(e) => setNewEmail(e.target.value)}
                onKeyPress={(e) => e.key === "Enter" && addEmail()}
                disabled={isLoading}
              />
            </div>
            <Button
              onClick={addEmail}
              className="mt-6"
              disabled={isLoading || !newEmail}
            >
              {isLoading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Plus className="h-4 w-4" />
              )}
            </Button>
          </div>

          {/* Current Allowlist */}
          <div>
            <Label>Current allowlist ({allowlistEmails.length} emails):</Label>
            <div className="flex flex-wrap gap-2 mt-2">
              {allowlistEmails.length === 0 ? (
                <p className="text-muted-foreground text-sm">
                  No trusted emails configured. Add one above to get started.
                </p>
              ) : (
                allowlistEmails.map((email) => (
                  <Badge
                    key={email}
                    variant="secondary"
                    className="flex items-center gap-1"
                  >
                    {email}
                    <button
                      onClick={() => removeEmail(email)}
                      className="ml-1 hover:text-destructive"
                      disabled={isLoading}
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </Badge>
                ))
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Help Card */}
      <Card>
        <CardHeader>
          <CardTitle>How it works</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-muted-foreground">
          <p>
            • The auto-approval service checks for pending code jobs every second
          </p>
          <p>
            • Jobs from emails in the allowlist are automatically approved
          </p>
          <p>
            • Jobs from other senders remain pending for manual review
          </p>
          <p>
            • Changes to the allowlist take effect within 30 seconds
          </p>
        </CardContent>
      </Card>
    </div>
  );
} 