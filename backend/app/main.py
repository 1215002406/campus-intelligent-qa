from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import auth, chat, conversations, documents, models, retrieval
from app.core.config import Settings
from app.core.database import Database
from app.llm.openai_compatible import OpenAICompatibleChatModel
from app.services.accounts import bootstrap_accounts
from app.services.ingestion import IngestionService
from app.services.llm_models import LLMModelService
from app.services.vector_index import VectorIndexService


def create_app(settings: Settings | None = None) -> FastAPI:
    configuration = settings if settings is not None else Settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        configuration.validate_runtime()
        database = Database(configuration)
        application.state.database = database
        ingestion: IngestionService | None = None
        vector_index: VectorIndexService | None = None
        try:
            database.initialize()
            with database.session_factory() as session, session.begin():
                bootstrap_accounts(session, configuration)
            if configuration.vector_index_enabled:
                vector_index = VectorIndexService(database.session_factory, configuration)
                application.state.vector_index = vector_index
            ingestion = IngestionService(database.session_factory, configuration, vector_index)
            application.state.ingestion = ingestion
            ingestion.start()
            if vector_index is not None:
                vector_index.start_backfill()
            yield
        finally:
            if ingestion is not None:
                ingestion.stop()
            if vector_index is not None:
                vector_index.stop()
            database.dispose()

    application = FastAPI(
        title="校园智能问答系统", version="0.2.0", lifespan=lifespan,
        description="账号、权限、会话、多格式文档入库、混合检索及本地/远程流式问答。",
    )
    application.state.settings = configuration
    application.state.llm_models = LLMModelService(configuration)
    application.state.llm_model = OpenAICompatibleChatModel(configuration)

    @application.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exception: RequestValidationError):
        # FastAPI's default validation response echoes rejected inputs, including passwords.
        safe_errors = [{"loc": error["loc"], "msg": error["msg"], "type": error["type"]}
                       for error in exception.errors()]
        return JSONResponse(status_code=422, content={"detail": safe_errors})

    application.add_middleware(
        CORSMiddleware, allow_origins=configuration.cors_origins,
        allow_credentials=False, allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    for router in (auth.router, conversations.router, chat.router, documents.router, retrieval.router, models.router):
        application.include_router(router, prefix="/api")

    @application.get("/api/health", tags=["health"])
    def health():
        return {
            "status": "ok",
            "stage": "rag",
            "rag_ready": getattr(application.state, "vector_index", None) is not None,
            "vector_index_enabled": configuration.vector_index_enabled,
        }

    return application


app = create_app()
