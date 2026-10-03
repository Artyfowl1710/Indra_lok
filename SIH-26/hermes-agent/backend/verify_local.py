import httpx
from pathlib import Path
from dotenv import dotenv_values
key=dotenv_values('.env')['WORKBENCH_API_KEY']
with httpx.Client(base_url='http://127.0.0.1:8000',headers={'Authorization':'Bearer '+key},timeout=180) as c:
    r=c.get('/v1/admin/keys');print('Admin authentication:',r.status_code)
    r=c.post('/v1/models',json={'name':'qwen3.5-4b','source':{'type':'local_path','path':str(Path('models/Qwen_Qwen3.5-4B-Q4_K_M.gguf').resolve())},'backend':'llamaswap','type':'text','task_tags':['chat','coding'],'pinned':True,'vram_mb':3100});print('Register:',r.status_code,r.text[:500])
    r=c.post('/v1/chat/completions',json={'model':'qwen3.5-4b','messages':[{'role':'user','content':'Reply with BACKEND_OK only.'}],'max_tokens':32,'chat_template_kwargs':{'enable_thinking':False}});print('Reply:',r.status_code,r.text[:1200])
print('Qdrant:',httpx.get('http://127.0.0.1:6333/healthz').status_code)
