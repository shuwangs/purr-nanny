"""Local chat facade; model credentials and MCP bearer remain server-side."""
import hashlib
import hmac
import json
import os
import secrets
from contextvars import ContextVar
from pathlib import Path
from urllib.parse import urlsplit

import anyio
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.applications import Starlette
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse, HTMLResponse
from starlette.routing import Route, Mount
from starlette.staticfiles import StaticFiles

from web.cards.resources import resource_html
import web
from server.mcp.contracts import AddCat
from server.agent import Agent
from server.backend import DomainError
from storage.conversations import Conversations
from server.identity import BearerMapping, identity
from server.mcp.client import MCPGateway
from server.models import BedrockModel, UnconfiguredModel
from server.models.demo import DemoModel
from server.models.openai import OpenAIModel

bearer_context = ContextVar('chat_mcp_bearer')


class Message(BaseModel):
    model_config = ConfigDict(extra='forbid')
    message_id: str = Field(min_length=8,max_length=128)
    text: str = Field(min_length=1,max_length=6000)
    cat_id: str | None = Field(default=None,max_length=128)
    recorded_by: str | None = Field(default=None,min_length=1,max_length=80)


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: str = Field(min_length=8,max_length=128)
    message: str = Field(min_length=1,max_length=6000)
    cat_id: str | None = Field(default=None,max_length=128)
    recorded_by: str | None = Field(default=None,min_length=1,max_length=80)
    conversation_id: str | None = Field(default=None,max_length=128)


class NewPet(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    request_id: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=80)
    meals_per_day: int | None = Field(default=None, strict=True, ge=1, le=12)


def build_chat_app(*, agent, mapping, chat_password, mcp_token, allowed_hosts=None, recorders=None):
    recorders = recorders if recorders is not None else ["Shu","Alex","Yuan"]
    if not recorders or len(recorders)!=len(set(recorders)) or any(not isinstance(name,str) or not name.strip() or len(name)>80 for name in recorders):
        raise ValueError("Configure nonempty unique household recorder names")
    if not chat_password or chat_password == mcp_token:
        raise ValueError("Configure a separate chat password")
    principal = mapping.resolve("Bearer " + mcp_token)
    if principal is None:
        raise ValueError("Configured chat MCP token must match the server token mapping")
    cookie_sessions = {}
    root = Path(web.__file__).resolve().parent / 'chat'

    def error(code, message, status=400):
        return JSONResponse({'error':{'code':code,'message':message}},status_code=status)

    async def login(request):
        try:
            data = await request.json()
            password = data['password']
            if not isinstance(password,str) or not hmac.compare_digest(password.encode(),chat_password.encode()):
                return error('unauthorized','Invalid chat password',401)
        except (ValueError,KeyError,TypeError):
            return error('invalid_arguments','Supply a chat password')
        handle = secrets.token_urlsafe(32)
        # Bounded local login cache; existing cookie stays valid until logout/restart.
        if len(cookie_sessions) >= 1000:
            return error('login_capacity','Restart the local chat server to clear unused logins',503)
        cookie_sessions[handle] = True
        response = JSONResponse({'authenticated':True})
        response.set_cookie('cat_nanny_chat',handle,httponly=True,samesite='strict',secure=request.url.scheme=='https')
        return response

    async def logout(request):
        cookie_sessions.pop(request.cookies.get('cat_nanny_chat'),None)
        response = JSONResponse({'authenticated':False})
        response.delete_cookie('cat_nanny_chat')
        return response

    async def homepage(request):
        path = root / 'chat.html'
        return HTMLResponse(path.read_text() if path.exists() else '<h1>Purr Nanny chat API</h1><p>Chat UI integration is pending.</p>')

    async def card(request):
        try:
            return HTMLResponse(resource_html('ui://cat-nanny/'+request.path_params['view']+'.html'))
        except ValueError:
            return error('not_found','View not found',404)

    async def create_session(request):
        session = await anyio.to_thread.run_sync(agent.store.create,identity.get().household_id)
        return JSONResponse({'schema_version':'1.0','conversation_id':session})

    async def get_session(request):
        try:
            result = await anyio.to_thread.run_sync(agent.store.get,identity.get().household_id,request.path_params['conversation'])
            return JSONResponse(result)
        except DomainError:
            return error('not_found','Conversation not found',404)

    async def bootstrap(request):
        try:
            result = await agent.gateway.call(bearer_context.get(),'list_cats',{})
            if result['is_error']:
                return error('discovery_failed','Unable to load cats',503)
            session = await anyio.to_thread.run_sync(agent.store.create,identity.get().household_id)
            mode = 'OpenAI · ' + agent.model.model_id if isinstance(agent.model,OpenAIModel) else 'DEMO · Fixed rules / No AI model · Saves real local records' if isinstance(agent.model,DemoModel) else 'Bedrock model' if isinstance(agent.model,BedrockModel) else 'Model not configured' if isinstance(agent.model,UnconfiguredModel) else 'Configured model adapter'
            return JSONResponse({'cats':result['structuredContent']['cats'],'conversation_id':session,'session_id':session,'mode_label':mode,'recorders':recorders})
        except Exception:
            return error('mcp_unavailable','Start the MCP service and check its configured URL',503)

    async def add_pet(request):
        try:
            parsed = NewPet.model_validate(await request.json())
            key = 'pet-form:' + hashlib.sha256(parsed.request_id.encode()).hexdigest()
            args = AddCat(name=parsed.name, meals_per_day=parsed.meals_per_day,
                          idempotency_key=key).model_dump(mode='json', exclude_none=True)
        except (ValueError, ValidationError):
            return error('invalid_arguments', 'Enter a pet name (up to 80 characters) and optional meals per day (1–12).')
        try:
            result = await agent.gateway.call(bearer_context.get(), 'add_cat', args)
            content = result['structuredContent']
            if result['is_error']:
                code = content.get('error', {}).get('code', 'save_failed')
                return error(code, content.get('error', {}).get('message', 'Unable to save pet'),
                             409 if code == 'idempotency_conflict' else 503 if code == 'internal_error' else 400)
            return JSONResponse({'cat': content['cat']})
        except Exception:
            return error('mcp_unavailable', 'Could not confirm the save. Retry to check without adding a duplicate pet.', 503)

    async def respond(request, alias=False):
        try:
            raw = await request.json()
            if alias:
                parsed = ChatMessage.model_validate(raw)
                message,text,cat = parsed.request_id,parsed.message,parsed.cat_id
                session = parsed.conversation_id or await anyio.to_thread.run_sync(agent.store.session_for_message,identity.get().household_id,message)
            else:
                parsed = Message.model_validate(raw)
                message,text,cat = parsed.message_id,parsed.text,parsed.cat_id
                session = request.path_params['conversation']
            if parsed.recorded_by is not None and parsed.recorded_by not in recorders:
                return error('invalid_recorder','Select a configured household recording person')
            if not text.strip():
                return error('invalid_arguments','Enter a message')
            result = await agent.chat(identity.get(),bearer_context.get(),session,message,text,cat,recorded_by=parsed.recorded_by,require_recorder=True,recorders=recorders)
            if alias:
                result = {**result,'results':[dict(tool=item['name'],structuredContent=item['structuredContent'],is_error=item['is_error']) for item in result['tool_results']], 'follow_up':result['pending_follow_up']}
            return JSONResponse(result,status_code=503 if result['status']=='retry_required' else 200)
        except (ValueError,ValidationError):
            return error('invalid_arguments','Message does not match the chat schema')
        except DomainError as exc:
            return error(exc.code,exc.message,404 if exc.code=='not_found' else 409)

    async def alias_chat(request):
        return await respond(request,True)

    app = Starlette(routes=[Route('/',homepage),Mount('/chat-assets',StaticFiles(directory=root)),
        Route('/apps/{view}.html',card),Route('/api/chat/login',login,methods=['POST']),Route('/api/chat/logout',logout,methods=['POST']),
        Route('/api/pets',add_pet,methods=['POST']),Route('/api/chat/session',bootstrap),Route('/api/chat',alias_chat,methods=['POST']),
        Route('/api/chat/sessions',create_session,methods=['POST']),Route('/api/chat/sessions/{conversation}',get_session),
        Route('/api/chat/sessions/{conversation}/messages',respond,methods=['POST'])])

    class ChatAuth:
        def __init__(self, app):
            self.app = app
        async def __call__(self,scope,receive,send):
            if scope['type'] != 'http':
                return await self.app(scope,receive,send)
            from starlette.requests import Request
            request = Request(scope,receive)
            if scope['path'].startswith('/api/'):
                # Reject cross-site browser writes; bearer API clients need no Origin header.
                origin = request.headers.get('origin')
                if origin and origin != f'{request.url.scheme}://{request.url.netloc}':
                    return await error('invalid_origin','Cross-origin chat requests are disabled',403)(scope,receive,send)
                length = request.headers.get('content-length','0')
                if not length.isdigit() or int(length) > 32768:
                    return await error('request_too_large','Chat request is too large',413)(scope,receive,send)
                if scope['path'] == '/api/chat/login':
                    return await self.app(scope,receive,send)
                if not cookie_sessions.get(request.cookies.get('cat_nanny_chat')):
                    return await error('unauthorized','Sign in with the chat password',401)(scope,receive,send)
                identity_token = identity.set(principal)
                bearer_token = bearer_context.set(mcp_token)
                try:
                    return await self.app(scope,receive,send)
                finally:
                    identity.reset(identity_token)
                    bearer_context.reset(bearer_token)
            return await self.app(scope,receive,send)

    app.add_middleware(ChatAuth)
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=allowed_hosts or ['localhost','127.0.0.1','testserver'])
    return app


def create_app():
    if os.getenv('CAT_NANNY_MODE','local') != 'local':
        raise RuntimeError('Chat production mode requires production identity and shared session storage')
    mapping = BearerMapping(json.loads(os.environ.get('CAT_NANNY_TOKEN_MAP','{}')))
    model_id = os.getenv('CAT_NANNY_BEDROCK_MODEL_ID')
    model = UnconfiguredModel()
    if os.getenv('CAT_NANNY_CHAT_MODE') == 'demo':
        model = DemoModel()
    elif os.getenv('CAT_NANNY_CHAT_MODE') == 'openai':
        model = OpenAIModel(os.getenv('OPENAI_API_KEY'), os.getenv('CAT_NANNY_OPENAI_MODEL', 'gpt-4.1-mini'))
    elif model_id:
        import boto3
        from botocore.config import Config
        model = BedrockModel(boto3.client('bedrock-runtime',config=Config(connect_timeout=3,read_timeout=45,retries={'total_max_attempts':1})),model_id)
    store = Conversations(os.getenv('CAT_NANNY_CHAT_DB','cat_nanny_chat.sqlite3'))
    gateway = MCPGateway(os.getenv('CAT_NANNY_MCP_URL','http://127.0.0.1:8000/mcp/'))
    return build_chat_app(agent=Agent(store,model,gateway),mapping=mapping, chat_password=os.environ['CAT_NANNY_CHAT_PASSWORD'],
        mcp_token=os.environ['CAT_NANNY_CHAT_MCP_TOKEN'], recorders=json.loads(os.getenv('CAT_NANNY_CHAT_RECORDERS','["Shu","Alex","Yuan"]')), allowed_hosts=json.loads(os.getenv('CAT_NANNY_CHAT_ALLOWED_HOSTS','["localhost","127.0.0.1"]')))
