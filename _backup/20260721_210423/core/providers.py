import json, os, threading, urllib.request, urllib.error

OPENAI_PROVIDERS = {
    "groq": ("GROQ", "https://api.groq.com/openai/v1", "qwen/qwen3.6-27b"),
    "nvidia": ("NVIDIA", "https://integrate.api.nvidia.com/v1", "qwen/qwen3-next-80b-a3b-instruct"),
    "fireworks": ("FIREWORKS", "https://api.fireworks.ai/inference/v1", "accounts/fireworks/models/deepseek-v4-pro"),
}

class ProviderRegistry:
    def __init__(self, env=None):
        self.env = env or os.environ
        self.cursor = 0
        self.lock = threading.Lock()
        self.stats = {}

    def slots(self):
        out = []
        # Cloud Providers
        for name, (prefix, default_url, default_model) in OPENAI_PROVIDERS.items():
            for n in (1, 2):
                key = self.env.get(f'{prefix}_API_KEY_{n}', self.env.get(f'{prefix}_API_KEY', '') if n == 1 else '')
                if key:
                    out.append({
                        'provider': name, 'slot': n, 'key': key,
                        'url': self.env.get(f'{prefix}_BASE_URL', default_url).rstrip('/'),
                        'model': self.env.get(f'{prefix}_MODEL_{n}', self.env.get(f'{prefix}_MODEL', default_model))
                    })
        
        # DEEPSEEK (Local Bridge) - Always enabled
        out.append({
            'provider': 'nemapi', 'slot': 1, 'key': self.env.get('NEMAPI_KEY', 'sk-deepseek-local'),
            'url': self.env.get('NEMAPI_BASE_URL', 'http://127.0.0.1:8080/v1').rstrip('/'),
            'model': self.env.get('NEMAPI_MODEL', 'deepseek-web')
        })
            
        # GEMINI (Local Bridge) - Always enabled
        out.append({
            'provider': 'gemini', 'slot': 1, 'key': 'sk-gemini-local',
            'url': 'http://127.0.0.1:8081/v1',
            'model': self.env.get('GEMINI_MODEL_1', 'gemini-3.1-pro')
        })

        # Cohere
        for n in (1, 2):
            key = self.env.get(f'COHERE_API_KEY_{n}', self.env.get(f'COHERE_API_KEY', '') if n == 1 else '')
            if key:
                out.append({'provider': 'cohere', 'slot': n, 'key': key, 'model': self.env.get(f'COHERE_MODEL_{n}', 'command-a-03-2025'), 'url': 'https://api.cohere.com/v2/chat'})
        
        return out

    def public_status(self):
        return [{'provider': x['provider'], 'slot': x['slot'], 'model': x['model'], 'configured': True, **self.stats.get((x['provider'], x['slot']), {})} for x in self.slots()]

    def ordered(self, preferred=None, preferred_slot=None):
        items = self.slots()
        if preferred:
            items.sort(key=lambda x: (0 if x['provider'] == preferred else 1, 0 if str(x['slot']) == str(preferred_slot) else 1))
        return items

    def call(self, messages, preferred=None, preferred_slot=None):
        errors = []
        for slot in self.ordered(preferred, preferred_slot):
            try:
                text = self._call_slot(slot, messages)
                self.stats[(slot['provider'], slot['slot'])] = {'state': 'ok'}
                return text, slot, None
            except Exception as e:
                self.stats[(slot['provider'], slot['slot'])] = {'state': 'error', 'error': str(e)[:160]}
                errors.append('%s/%s: %s' % (slot['provider'], slot['slot'], e))
        return None, None, ' | '.join(errors) or 'Aucun fournisseur configuré'

    def _call_slot(self, s, messages):
        url, key = s['url'], s['key']
        headers = {'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json', 'User-Agent': 'AstarteBam/6.0'}
        
        if s['provider'] in ('nemapi', 'gemini'):
            try:
                h_url = url.rsplit('/v1', 1)[0] + '/v1/health'
                req_h = urllib.request.Request(h_url, headers={'Authorization': 'Bearer ' + key})
                urllib.request.urlopen(req_h, timeout=2)
            except Exception as e:
                raise RuntimeError(f"Bridge {s['provider']} hors ligne. ({e})")

        if s['provider'] == 'cohere':
            body, target_url = {'model': s['model'], 'messages': [{'role': m['role'], 'content': m['content']} for m in messages]}, url
        else:
            body = {'model': s['model'], 'messages': messages, 'temperature': 0.7}
            target_url = url + '/chat/completions'

        req = urllib.request.Request(target_url, data=json.dumps(body).encode(), headers=headers)
        with urllib.request.urlopen(req, timeout=150) as response:
            data = json.loads(response.read().decode())
            if s['provider'] == 'cohere':
                return ''.join(x.get('text', '') for x in data.get('message', {}).get('content', []))
            return data['choices'][0]['message']['content']

    def nemapi_request(self, path, method="GET"):
        slot = next((x for x in self.slots() if x["provider"] == "nemapi"), None)
        if not slot: raise RuntimeError("NEMAPI désactivé")
        url = slot["url"].rstrip("/") + ("/" + path.lstrip("/") if path else "")
        req = urllib.request.Request(url, method=method, headers={"Authorization": "Bearer " + slot['key']})
        return json.loads(urllib.request.urlopen(req, timeout=10).read().decode())

    def reset_nemapi_session(self):
        return self.nemapi_request("/sessions/reset", method="POST")

    def nemapi_status(self):
        try:
            return {"session": self.nemapi_request("/session"), "models": self.nemapi_request("/models")}
        except:
            return {"session": {}, "models": []}
