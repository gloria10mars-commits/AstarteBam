"""Rapport compact d'une exécution collaborative."""
def make_report(task_id, decision, agents, actions_count, errors):
    return {"task_id": task_id, "mode": "collaborative", "category": decision.category,
            "agents": agents, "actions_planned": actions_count, "errors": errors,
            "summary": "{} agent(s), catégorie {}, {} action(s) agrégée(s).".format(len(agents), decision.category, actions_count)}
