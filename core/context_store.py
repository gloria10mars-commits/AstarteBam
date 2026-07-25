"""Contexte en mémoire, isolé par tâche parent."""
import threading, time
class SharedContextStore:
    def __init__(self): self._data, self._lock = {}, threading.Lock()
    def create(self, task_id, prompt, decision):
        with self._lock:
            self._data[task_id] = {"prompt": prompt, "decision": decision, "created_at": time.time(), "agents": {}, "results": []}
    def add_agent(self, task_id, role, provider, result):
        with self._lock: self._data.get(task_id, {}).get("agents", {})[role] = {"provider": provider, "result": result}
    def get(self, task_id):
        with self._lock: return dict(self._data.get(task_id, {}))
