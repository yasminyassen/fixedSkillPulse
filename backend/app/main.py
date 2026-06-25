import sys
import os


_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_PROJECT_ROOT = os.path.abspath(os.path.join(_BACKEND_DIR, ".."))
_CWD = os.path.abspath(os.getcwd())

for _p in [_BACKEND_DIR, _PROJECT_ROOT, _CWD]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.api.recruiter import router as recruiter_router
from app.api import auth
from app.api import github_oauth
from app.api import analysis
from app.api import security_report
from app.api import repos
from app.api import requirements
from app.api import requirement_coverage
from app.api import github_classroom
from app.api import recruiter_bulk
from app.api import manager_dashboard
from app.api import manager_profile
from app.api import manager_security

from app.core.rate_limiter import limiter
from slowapi.middleware import SlowAPIMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

from ai_services.rag.rag_seeder import seed_standards
from ai_services.rag.learning_rag import validate_learning_rag_startup

from app.api.profile import router as profile_router
@asynccontextmanager
async def lifespan(app: FastAPI):
    seed_standards()
    validate_learning_rag_startup()
    yield


app = FastAPI(
    title="SkillPulse API",
    description="AI-assisted developer evaluation platform",
    version="0.1.0",
    lifespan=lifespan,
)

# attach limiter to app state so routers can access it
app.state.limiter = limiter

# handle rate limit exceeded errors
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    print(exc.errors())
    return JSONResponse(
        status_code=422,
        content=jsonable_encoder({"detail": exc.errors()}),
    )

# activate rate limiting middleware
app.add_middleware(SlowAPIMiddleware)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# routers
app.include_router(auth.router)
app.include_router(github_oauth.router)
app.include_router(analysis.router)
app.include_router(security_report.router)
app.include_router(repos.router)
app.include_router(profile_router)
app.include_router(github_classroom.router)
app.include_router(recruiter_bulk.router)
app.include_router(recruiter_router)
app.include_router(requirements.router)
app.include_router(requirement_coverage.router)
app.include_router(manager_dashboard.router)
app.include_router(manager_profile.router)
app.include_router(manager_security.router)
