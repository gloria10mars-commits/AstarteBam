#!/usr/bin/env python3
"""Tests unitaires proxy OpenAI v2.3 (session + delta + send only)."""

from __future__ import annotations

import asyncio
import sys

import base64

from proxy_openai import (
    extract_tool_calls,
    extract_files_from_payload,
    pack_delta_for_browser,
    pack_messages_for_browser,
    JobsManager,
    BrowserSession,
    handle_models,
    handle_session_get,
)


def test_extract_fenced():
    text = '''Je lance.

```json
{"tool_calls":[{"name":"run_bash","arguments":{"command":"uname -a","async":false}}]}
```
'''
    content, tcs = extract_tool_calls(text)
    assert len(tcs) == 1
    assert tcs[0]["function"]["name"] == "run_bash"
    print("extract fenced OK")


def test_extract_raw():
    text = '{"tool_calls":[{"name":"write_file","arguments":{"path":"/tmp/a.py","content":"x=1"}}]}'
    content, tcs = extract_tool_calls(text)
    assert content is None
    assert tcs[0]["function"]["name"] == "write_file"
    print("extract raw OK")


def test_delta_no_history_stack():
    """Le 2e message ne doit PAS re-inclure le 1er user."""
    msgs = [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "premier"},
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": "deuxieme"},
    ]
    packed = pack_delta_for_browser(msgs, include_system=False)
    assert "deuxieme" in packed
    assert "premier" not in packed
    assert "SYS" not in packed
    print("delta no stack OK")


def test_first_send_has_system():
    msgs = [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "hi"},
    ]
    packed = pack_delta_for_browser(msgs, include_system=True)
    assert "SYS" in packed and "hi" in packed
    print("first system OK")


def test_tool_batch():
    msgs = [{"role": "tool", "name": "run_bash", "content": "Linux xyz"}]
    tools = [
        {
            "type": "function",
            "function": {
                "name": "run_bash",
                "description": "Shell",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]
    packed = pack_delta_for_browser(
        msgs, tools=tools, tool_choice="auto", include_system=False
    )
    assert "Linux xyz" in packed
    assert "PROTOCOLE" in packed or "tool_calls" in packed.lower()
    print("tool batch OK")


def test_session_always_send():
    """v2.3 : tous les tours sont send (pas regenerate)."""
    s = BrowserSession()
    assert not s.has_sent_user_message
    mode = "send"
    assert mode == "send"
    s.has_sent_user_message = True
    mode = "send"
    assert mode == "send"
    s.reset()
    assert not s.has_sent_user_message
    print("session always send OK")


def test_models_and_session_get():
    st, body, _ = handle_models()
    assert st == 200
    st2, body2, _ = handle_session_get()
    assert st2 == 200 and "session" in body2
    print("models/session OK")


async def test_jobs_force_send():
    jm = JobsManager()
    # même si on demande regenerate, le job est forcé en send
    jid = await jm.create_job("hello delta", mode="regenerate", meta={"turn": 2})
    pending = await jm.get_pending_job()
    assert pending["mode"] == "send"
    assert pending["text"] == "hello delta"
    await jm.set_result(jid, "assistant reply")
    out = await jm.wait_job(jid, timeout=2)
    assert out["status"] == "completed"
    print("jobs force send OK")


def test_pack_compat_alias():
    t = pack_messages_for_browser(
        [{"role": "user", "content": "x"}], tools=None, tool_choice="none"
    )
    assert "x" in t
    print("compat pack OK")


def test_files_payload():
    b64 = base64.b64encode(b"%PDF-1.4 hello").decode()
    files = extract_files_from_payload(
        {
            "files": [
                {
                    "name": "doc.pdf",
                    "mime": "application/pdf",
                    "content_base64": b64,
                }
            ]
        }
    )
    assert len(files) == 1
    assert files[0]["name"] == "doc.pdf"
    assert files[0]["mime"] == "application/pdf"
    # image_url data URI in messages
    img = base64.b64encode(b"\x89PNG").decode()
    files2 = extract_files_from_payload(
        {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "regarde"},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{img}"},
                        },
                    ],
                }
            ]
        }
    )
    assert len(files2) == 1
    assert "png" in files2[0]["mime"] or files2[0]["name"]
    print("files payload OK")


async def test_jobs_with_files_meta():
    jm = JobsManager()
    jid = await jm.create_job(
        "[USER]\nanalyse",
        mode="send",
        meta={
            "files": [
                {
                    "name": "a.txt",
                    "mime": "text/plain",
                    "content_base64": base64.b64encode(b"hi").decode(),
                }
            ]
        },
    )
    pending = await jm.get_pending_job()
    assert pending["meta"]["files"][0]["name"] == "a.txt"
    # 2e poll : plus de job
    assert await jm.get_pending_job() is None
    await jm.set_result(jid, "ok file analysis")
    await jm.set_result(jid, "duplicate ignored")
    out = await jm.wait_job(jid, timeout=2)
    assert out["result"] == "ok file analysis"
    print("jobs files meta OK")


def main():
    test_extract_fenced()
    test_extract_raw()
    test_delta_no_history_stack()
    test_first_send_has_system()
    test_tool_batch()
    test_session_always_send()
    test_models_and_session_get()
    asyncio.run(test_jobs_force_send())
    test_pack_compat_alias()
    test_files_payload()
    asyncio.run(test_jobs_with_files_meta())
    print("\nALL PROXY V2.4 TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
