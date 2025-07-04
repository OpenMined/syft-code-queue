"""
FastAPI backend for syft-code-queue with SyftBox integration
"""

from datetime import datetime
from pathlib import Path as PathLib
from typing import Any, Dict, Optional

from fastapi import Body, Depends, FastAPI, HTTPException, Path, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from syft_core import Client

from .models import (
    JobActionRequest,
    JobDetailsResponse,
    JobListResponse,
    JobStatsResponse,
    MessageResponse,
)

# Import syft_code_queue for job browsing
try:
    import syft_code_queue as q
    from syft_code_queue.client import MockSyftBoxClient
    from syft_code_queue.models import DataSitesCollection
except ImportError:
    logger.error("syft-code-queue not available - job browsing features will be limited")
    q = None


# Helper functions
def _get_file_type(file_path: str) -> str:
    """Determine file type based on extension."""
    file_path = str(file_path).lower()

    if file_path.endswith((".py", ".pyw")):
        return "python"
    elif file_path.endswith((".js", ".mjs")):
        return "javascript"
    elif file_path.endswith(".ts"):
        return "typescript"
    elif file_path.endswith(".sh"):
        return "shell"
    elif file_path.endswith(".md"):
        return "markdown"
    elif file_path.endswith(".json"):
        return "json"
    elif file_path.endswith((".yml", ".yaml")):
        return "yaml"
    elif file_path.endswith(".sql"):
        return "sql"
    elif file_path.endswith(".csv"):
        return "csv"
    elif file_path.endswith((".txt", ".log")):
        return "text"
    else:
        return "text"


def _format_time_ago(timestamp: datetime) -> str:
    """Format time as human-readable 'ago' string."""
    now = datetime.now()
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=None)
    if now.tzinfo is None:
        now = now.replace(tzinfo=None)

    diff = now - timestamp

    if diff.days > 0:
        return f"{diff.days}d ago"
    elif diff.seconds > 3600:
        hours = diff.seconds // 3600
        return f"{hours}h ago"
    elif diff.seconds > 60:
        minutes = diff.seconds // 60
        return f"{minutes}m ago"
    else:
        return "now"


def _get_datasites_collection() -> Optional[DataSitesCollection]:
    """Get the datasites collection for job browsing."""
    try:
        if not q:
            return None

        # Try to create a mock client for job browsing
        client = MockSyftBoxClient()
        return DataSitesCollection(client)
    except Exception as e:
        logger.error(f"Failed to create datasites collection: {e}")
        return None


# Initialize SyftBox connection
def get_client() -> Client:
    """Get SyftBox client."""
    try:
        return Client.load()
    except Exception as e:
        logger.error(f"Failed to load SyftBox client: {e}")
        raise HTTPException(status_code=500, detail="SyftBox client not available")


app = FastAPI(
    title="Syft Code Queue UI API",
    description="Browse and manage code jobs across the SyftBox network",
    version="0.1.0",
)

# Add CORS middleware for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:*",
        "http://127.0.0.1:*",
    ],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve the frontend static files
try:
    frontend_path = PathLib(__file__).parent.parent / "frontend" / "out"
    if frontend_path.exists():
        app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="static")
        logger.info(f"Serving frontend from {frontend_path}")
    else:
        logger.warning(f"Frontend build directory not found: {frontend_path}")
except Exception as e:
    logger.error(f"Failed to mount frontend static files: {e}")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.now()}


@app.get("/api/status")
async def get_status(client: Client = Depends(get_client)) -> Dict[str, Any]:
    """Get application status."""
    datasites = _get_datasites_collection()
    job_count = 0
    if datasites:
        try:
            jobs = datasites.get_all_jobs()
            job_count = len(jobs)
        except Exception as e:
            logger.error(f"Failed to count jobs: {e}")

    return {
        "app": "Syft Code Queue UI",
        "version": "0.1.0",
        "timestamp": datetime.now(),
        "syftbox": {"status": "connected", "user_email": client.email},
        "components": {
            "backend": "running",
            "job_browser": "enabled" if q else "disabled",
            "total_jobs": job_count,
        },
    }


@app.get("/api/v1/jobs", response_model=JobListResponse)
async def get_jobs(
    limit: int = Query(100, description="Maximum number of jobs to return"),
    status: Optional[str] = Query(None, description="Filter by job status"),
    sender: Optional[str] = Query(None, description="Filter by sender email"),
    client: Client = Depends(get_client),
) -> JobListResponse:
    """Get list of all jobs across the network."""
    try:
        datasites = _get_datasites_collection()
        if not datasites:
            raise HTTPException(status_code=503, detail="Job browsing not available")

        all_jobs = datasites.get_all_jobs()

        # Apply filters
        if status:
            all_jobs = [job for job in all_jobs if job.get("status", "").lower() == status.lower()]

        if sender:
            all_jobs = [job for job in all_jobs if job.get("sender", "").lower() == sender.lower()]

        # Sort by creation time (newest first)
        all_jobs.sort(key=lambda x: x.get("created_at", datetime.min), reverse=True)

        # Apply limit
        if limit > 0:
            all_jobs = all_jobs[:limit]

        # Format jobs for response
        formatted_jobs = []
        for job in all_jobs:
            formatted_job = {
                "uid": job.get("uid", ""),
                "sender": job.get("sender", ""),
                "status": job.get("status", "pending"),
                "created_at": job.get("created_at", datetime.now()),
                "time_ago": _format_time_ago(job.get("created_at", datetime.now())),
                "datasite": job.get("datasite", ""),
                "files": job.get("files", []),
                "description": job.get("description", ""),
                "is_recent": (datetime.now() - job.get("created_at", datetime.min)).total_seconds()
                < 3,
            }
            formatted_jobs.append(formatted_job)

        return JobListResponse(
            jobs=formatted_jobs,
            total=len(formatted_jobs),
            filtered=len(formatted_jobs) < len(all_jobs) if status or sender else False,
        )

    except Exception as e:
        logger.error(f"Failed to get jobs: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve jobs: {str(e)}")


@app.get("/api/v1/jobs/stats", response_model=JobStatsResponse)
async def get_job_stats(client: Client = Depends(get_client)) -> JobStatsResponse:
    """Get job statistics."""
    try:
        datasites = _get_datasites_collection()
        if not datasites:
            raise HTTPException(status_code=503, detail="Job browsing not available")

        all_jobs = datasites.get_all_jobs()

        stats = {
            "total": len(all_jobs),
            "pending": len([j for j in all_jobs if j.get("status", "").lower() == "pending"]),
            "running": len([j for j in all_jobs if j.get("status", "").lower() == "running"]),
            "completed": len([j for j in all_jobs if j.get("status", "").lower() == "completed"]),
            "failed": len([j for j in all_jobs if j.get("status", "").lower() == "failed"]),
            "recent": len(
                [
                    j
                    for j in all_jobs
                    if (datetime.now() - j.get("created_at", datetime.min)).total_seconds() < 3
                ]
            ),
        }

        return JobStatsResponse(**stats)

    except Exception as e:
        logger.error(f"Failed to get job stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve job stats: {str(e)}")


@app.get("/api/v1/jobs/{job_uid}", response_model=JobDetailsResponse)
async def get_job_details(
    job_uid: str = Path(..., description="Job UID"), client: Client = Depends(get_client)
) -> JobDetailsResponse:
    """Get detailed information about a specific job."""
    try:
        datasites = _get_datasites_collection()
        if not datasites:
            raise HTTPException(status_code=503, detail="Job browsing not available")

        all_jobs = datasites.get_all_jobs()
        job = next((j for j in all_jobs if j.get("uid") == job_uid), None)

        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        # Get detailed file information
        files_with_content = []
        for file_info in job.get("files", []):
            file_detail = {
                "path": file_info.get("path", ""),
                "type": _get_file_type(file_info.get("path", "")),
                "size": file_info.get("size", 0),
                "content": file_info.get("content", ""),
                "modified_at": file_info.get("modified_at", datetime.now()),
            }
            files_with_content.append(file_detail)

        return JobDetailsResponse(
            uid=job.get("uid", ""),
            sender=job.get("sender", ""),
            status=job.get("status", "pending"),
            created_at=job.get("created_at", datetime.now()),
            time_ago=_format_time_ago(job.get("created_at", datetime.now())),
            datasite=job.get("datasite", ""),
            description=job.get("description", ""),
            files=files_with_content,
            logs=job.get("logs", ""),
            output=job.get("output", ""),
            is_recent=(datetime.now() - job.get("created_at", datetime.min)).total_seconds() < 3,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get job details: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve job details: {str(e)}")


@app.post("/api/v1/jobs/{job_uid}/action", response_model=MessageResponse)
async def perform_job_action(
    job_uid: str = Path(..., description="Job UID"),
    action_request: JobActionRequest = Body(...),
    client: Client = Depends(get_client),
) -> MessageResponse:
    """Perform an action on a job (review, get logs, get output)."""
    try:
        datasites = _get_datasites_collection()
        if not datasites:
            raise HTTPException(status_code=503, detail="Job browsing not available")

        action = action_request.action.lower()

        if action == "review":
            code = f'q.get_job("{job_uid}").review()'
        elif action == "logs":
            code = f'q.get_job("{job_uid}").get_logs()'
        elif action == "output":
            code = f'q.get_job("{job_uid}").get_output()'
        else:
            raise HTTPException(status_code=400, detail=f"Unknown action: {action}")

        return MessageResponse(message=f"Action '{action}' prepared for job {job_uid}", code=code)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to perform job action: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to perform action: {str(e)}")


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main application page."""
    try:
        frontend_path = PathLib(__file__).parent.parent / "frontend" / "out"
        index_path = frontend_path / "index.html"

        if index_path.exists():
            return HTMLResponse(content=index_path.read_text(), status_code=200)
        else:
            return HTMLResponse(
                content="""
                <html>
                    <head><title>Syft Code Queue UI</title></head>
                    <body>
                        <h1>Syft Code Queue UI</h1>
                        <p>Frontend not built. Please run <code>cd frontend && npm run build</code></p>
                        <p>API is available at <a href="/docs">/docs</a></p>
                    </body>
                </html>
                """,
                status_code=200,
            )
    except Exception as e:
        logger.error(f"Failed to serve root page: {e}")
        return HTMLResponse(
            content=f"""
            <html>
                <head><title>Syft Code Queue UI</title></head>
                <body>
                    <h1>Syft Code Queue UI</h1>
                    <p>Error: {str(e)}</p>
                    <p>API is available at <a href="/docs">/docs</a></p>
                </body>
            </html>
            """,
            status_code=500,
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
