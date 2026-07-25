import sys, os, re
path = "/home/leon/AstarteBam/core/providers.py"
with open(path, "r", encoding="utf-8") as f:
    text = f.read()

# We replace the call method to BE STRICT
new_call = """
    def call(self, messages, preferred=None, preferred_slot=None):
        errors = []
        slots = self.ordered(preferred, preferred_slot)
        if preferred:
            slots = [s for s in slots if s['provider'] == preferred]
            if not slots: return None, None, f"Fournisseur {preferred} absent."
            
        for slot in slots:
            try:
                text = self._call_slot(slot, messages)
                self.stats[(slot['provider'], slot['slot'])] = {'state': 'ok'}
                return text, slot, None
            except Exception as e:
                self.stats[(slot['provider'], slot['slot'])] = {'state': 'error', 'error': str(e)[:160]}
                errors.append('%s/%s: %s' % (slot['provider'], slot['slot'], e))
        return None, None, ' | '.join(errors) or 'Aucun fournisseur configuré'
"""

text = re.sub(r'def call\(self,messages,preferred=None,preferred_slot=None\):.*?Aucun fournisseur configuré\'', new_call, text, flags=re.DOTALL)
with open(path, "w", encoding="utf-8") as f:
    f.write(text)
