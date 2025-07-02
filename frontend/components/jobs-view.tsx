"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Eye,
  RefreshCw,
  Clock,
  User,
  FileText,
  Play,
  CheckCircle,
  XCircle,
  AlertCircle,
  Copy,
  ExternalLink,
  Loader2,
} from "lucide-react";
import { toast } from "sonner";

// Types for our job data
interface JobFile {
  path: string;
  type: string;
  size: number;
  content?: string;
  modified_at?: string;
}

interface Job {
  uid: string;
  sender: string;
  status: string;
  created_at: string;
  time_ago: string;
  datasite: string;
  files: JobFile[];
  description?: string;
  is_recent: boolean;
}

interface JobDetails extends Job {
  logs?: string;
  output?: string;
}

interface JobStats {
  total: number;
  pending: number;
  running: number;
  completed: number;
  failed: number;
  recent: number;
}

// API service functions
const apiService = {
  async getJobs(limit = 100, status?: string, sender?: string): Promise<{ jobs: Job[]; total: number }> {
    const params = new URLSearchParams();
    params.append('limit', limit.toString());
    if (status) params.append('status', status);
    if (sender) params.append('sender', sender);
    
    const response = await fetch(`/api/v1/jobs?${params}`);
    if (!response.ok) throw new Error('Failed to fetch jobs');
    return response.json();
  },

  async getJobStats(): Promise<JobStats> {
    const response = await fetch('/api/v1/jobs/stats');
    if (!response.ok) throw new Error('Failed to fetch job stats');
    return response.json();
  },

  async getJobDetails(uid: string): Promise<JobDetails> {
    const response = await fetch(`/api/v1/jobs/${uid}`);
    if (!response.ok) throw new Error('Failed to fetch job details');
    return response.json();
  },

  async performJobAction(uid: string, action: string): Promise<{ message: string; code?: string }> {
    const response = await fetch(`/api/v1/jobs/${uid}/action`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action })
    });
    if (!response.ok) throw new Error('Failed to perform action');
    return response.json();
  }
};

export function JobsView() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [stats, setStats] = useState<JobStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [selectedStatus, setSelectedStatus] = useState<string>("all");
  const [selectedSender, setSelectedSender] = useState<string>("");
  const [selectedJob, setSelectedJob] = useState<JobDetails | null>(null);
  const [jobDetailsLoading, setJobDetailsLoading] = useState(false);

  useEffect(() => {
    loadJobs();
    loadStats();
    
    // Auto-refresh every 2 seconds
    const interval = setInterval(() => {
      loadJobs(true);
      loadStats();
    }, 2000);
    
    return () => clearInterval(interval);
  }, [selectedStatus, selectedSender]);

  const loadJobs = async (isRefresh = false) => {
    try {
      if (isRefresh) {
        setRefreshing(true);
      } else {
        setLoading(true);
      }
      
      const status = selectedStatus === "all" ? undefined : selectedStatus;
      const sender = selectedSender || undefined;
      
      const response = await apiService.getJobs(100, status, sender);
      setJobs(response.jobs);
    } catch (error) {
      console.error("Failed to load jobs:", error);
      toast.error("Failed to load jobs");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  const loadStats = async () => {
    try {
      const statsData = await apiService.getJobStats();
      setStats(statsData);
    } catch (error) {
      console.error("Failed to load stats:", error);
    }
  };

  const handleJobClick = async (job: Job) => {
    setJobDetailsLoading(true);
    try {
      const details = await apiService.getJobDetails(job.uid);
      setSelectedJob(details);
    } catch (error) {
      console.error("Failed to load job details:", error);
      toast.error("Failed to load job details");
    } finally {
      setJobDetailsLoading(false);
    }
  };

  const handleJobAction = async (uid: string, action: string) => {
    try {
      const result = await apiService.performJobAction(uid, action);
      if (result.code) {
        await navigator.clipboard.writeText(result.code);
        toast.success(`${action} code copied to clipboard!`);
      } else {
        toast.success(result.message);
      }
    } catch (error) {
      console.error(`Failed to perform ${action}:`, error);
      toast.error(`Failed to perform ${action}`);
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status.toLowerCase()) {
      case "pending":
        return <Clock className="h-4 w-4 text-yellow-500" />;
      case "running":
        return <Play className="h-4 w-4 text-blue-500" />;
      case "completed":
        return <CheckCircle className="h-4 w-4 text-green-500" />;
      case "failed":
        return <XCircle className="h-4 w-4 text-red-500" />;
      default:
        return <AlertCircle className="h-4 w-4 text-gray-500" />;
    }
  };

  const getStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case "pending":
        return "bg-yellow-100 text-yellow-800 border-yellow-200";
      case "running":
        return "bg-blue-100 text-blue-800 border-blue-200";
      case "completed":
        return "bg-green-100 text-green-800 border-green-200";
      case "failed":
        return "bg-red-100 text-red-800 border-red-200";
      default:
        return "bg-gray-100 text-gray-800 border-gray-200";
    }
  };

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-center h-64">
          <Loader2 className="h-8 w-8 animate-spin" />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Job Browser</h1>
          <p className="text-muted-foreground">
            Browse and manage jobs across the SyftBox network
          </p>
        </div>
        <Button
          onClick={() => loadJobs(true)}
          disabled={refreshing}
          variant="outline"
        >
          {refreshing ? (
            <Loader2 className="h-4 w-4 animate-spin mr-2" />
          ) : (
            <RefreshCw className="h-4 w-4 mr-2" />
          )}
          Refresh
        </Button>
      </div>

      {/* Stats Cards */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-6 gap-4">
          <Card>
            <CardContent className="p-4">
              <div className="text-2xl font-bold">{stats.total}</div>
              <div className="text-sm text-muted-foreground">Total</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="text-2xl font-bold text-yellow-600">{stats.pending}</div>
              <div className="text-sm text-muted-foreground">Pending</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="text-2xl font-bold text-blue-600">{stats.running}</div>
              <div className="text-sm text-muted-foreground">Running</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="text-2xl font-bold text-green-600">{stats.completed}</div>
              <div className="text-sm text-muted-foreground">Completed</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="text-2xl font-bold text-red-600">{stats.failed}</div>
              <div className="text-sm text-muted-foreground">Failed</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="text-2xl font-bold text-purple-600">{stats.recent}</div>
              <div className="text-sm text-muted-foreground">Recent</div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Filters */}
      <div className="flex gap-4">
        <div>
          <Label htmlFor="status-filter">Status</Label>
          <Select value={selectedStatus} onValueChange={setSelectedStatus}>
            <SelectTrigger className="w-[180px]">
              <SelectValue placeholder="Filter by status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All</SelectItem>
              <SelectItem value="pending">Pending</SelectItem>
              <SelectItem value="running">Running</SelectItem>
              <SelectItem value="completed">Completed</SelectItem>
              <SelectItem value="failed">Failed</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label htmlFor="sender-filter">Sender</Label>
          <Input
            id="sender-filter"
            placeholder="Filter by sender email"
            value={selectedSender}
            onChange={(e) => setSelectedSender(e.target.value)}
            className="w-[250px]"
          />
        </div>
      </div>

      {/* Jobs List */}
      <div className="space-y-4">
        {jobs.length === 0 ? (
          <Card>
            <CardContent className="p-8 text-center">
              <div className="text-muted-foreground">No jobs found</div>
            </CardContent>
          </Card>
        ) : (
          jobs.map((job) => (
            <Card 
              key={job.uid} 
              className={`cursor-pointer hover:shadow-md transition-shadow ${
                job.is_recent ? 'bg-gradient-to-r from-purple-50 to-pink-50 border-purple-200' : ''
              }`}
              onClick={() => handleJobClick(job)}
            >
              <CardContent className="p-4">
                <div className="flex items-center justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-2">
                      {getStatusIcon(job.status)}
                      <Badge className={getStatusColor(job.status)}>
                        {job.status}
                      </Badge>
                      <span className="font-mono text-sm text-muted-foreground">
                        {job.uid.substring(0, 8)}...
                      </span>
                      <span className="text-sm text-muted-foreground">
                        {job.time_ago}
                      </span>
                    </div>
                    <div className="flex items-center gap-4 text-sm">
                      <div className="flex items-center gap-1">
                        <User className="h-4 w-4" />
                        <span>{job.sender}</span>
                      </div>
                      <div className="flex items-center gap-1">
                        <ExternalLink className="h-4 w-4" />
                        <span>{job.datasite}</span>
                      </div>
                      <div className="flex items-center gap-1">
                        <FileText className="h-4 w-4" />
                        <span>{job.files.length} files</span>
                      </div>
                    </div>
                    {job.description && (
                      <p className="text-sm text-muted-foreground mt-2">
                        {job.description}
                      </p>
                    )}
                  </div>
                  <div className="flex gap-2">
                    {job.status === "pending" && (
                      <Button
                        size="sm"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleJobAction(job.uid, "review");
                        }}
                      >
                        <Eye className="h-4 w-4 mr-1" />
                        Review
                      </Button>
                    )}
                    {(job.status === "running" || job.status === "completed") && (
                      <>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleJobAction(job.uid, "logs");
                          }}
                        >
                          <FileText className="h-4 w-4 mr-1" />
                          Logs
                        </Button>
                        {job.status === "completed" && (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleJobAction(job.uid, "output");
                            }}
                          >
                            <Copy className="h-4 w-4 mr-1" />
                            Output
                          </Button>
                        )}
                      </>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          ))
        )}
      </div>

      {/* Job Details Dialog */}
      <Dialog open={!!selectedJob} onOpenChange={() => setSelectedJob(null)}>
        <DialogContent className="max-w-4xl max-h-[80vh]">
          <DialogHeader>
            <DialogTitle>Job Details</DialogTitle>
            <DialogDescription>
              {selectedJob && `${selectedJob.uid} - ${selectedJob.sender}`}
            </DialogDescription>
          </DialogHeader>
          
          {jobDetailsLoading ? (
            <div className="flex items-center justify-center h-64">
              <Loader2 className="h-8 w-8 animate-spin" />
            </div>
          ) : selectedJob && (
            <Tabs defaultValue="files" className="w-full">
              <TabsList>
                <TabsTrigger value="files">Files ({selectedJob.files.length})</TabsTrigger>
                {selectedJob.logs && <TabsTrigger value="logs">Logs</TabsTrigger>}
                {selectedJob.output && <TabsTrigger value="output">Output</TabsTrigger>}
              </TabsList>
              
              <TabsContent value="files" className="space-y-4">
                <ScrollArea className="h-[400px]">
                  {selectedJob.files.map((file, index) => (
                    <Card key={index} className="mb-4">
                      <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-mono">{file.path}</CardTitle>
                        <CardDescription>
                          {file.type} • {file.size} bytes
                        </CardDescription>
                      </CardHeader>
                      {file.content && (
                        <CardContent>
                          <pre className="text-xs bg-muted p-3 rounded overflow-x-auto">
                            <code>{file.content}</code>
                          </pre>
                        </CardContent>
                      )}
                    </Card>
                  ))}
                </ScrollArea>
              </TabsContent>
              
              {selectedJob.logs && (
                <TabsContent value="logs">
                  <ScrollArea className="h-[400px]">
                    <pre className="text-xs bg-muted p-3 rounded">
                      <code>{selectedJob.logs}</code>
                    </pre>
                  </ScrollArea>
                </TabsContent>
              )}
              
              {selectedJob.output && (
                <TabsContent value="output">
                  <ScrollArea className="h-[400px]">
                    <pre className="text-xs bg-muted p-3 rounded">
                      <code>{selectedJob.output}</code>
                    </pre>
                  </ScrollArea>
                </TabsContent>
              )}
            </Tabs>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
