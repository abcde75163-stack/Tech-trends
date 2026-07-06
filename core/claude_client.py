# -*- coding: utf-8 -*-
"""
Claude API 호출 공통 래퍼.

MOCK 모드: ANTHROPIC_API_KEY(환경변수) 또는 st.secrets에 키가 없으면
           실제 호출 대신 미리 정의된 모의 응답을 반환한다.
           → API 키 없는 로컬 개발/UI 테스트 단계에서 비용 없이 흐름을 검증하기 위함.
           실제 배포본에서는 키가 반드시 설정되어야 하며, MOCK 모드로 운영해서는 안 된다.
"""
import os
import json

try:
    import streamlit as st
    _HAS_ST = True
except ImportError:
    _HAS_ST = False


def get_api_key():
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    if _HAS_ST:
        try:
            return st.secrets["ANTHROPIC_API_KEY"]
        except Exception:
            return None
    return None


def is_mock_mode():
    return get_api_key() is None


def call_claude(system: str, user_message: str, model: str, max_tokens: int = 2000,
                 mock_response: dict | None = None):
    """
    system/user_message로 Claude API를 호출하고 JSON을 파싱해 반환한다.
    키가 없으면 mock_response를 그대로 반환한다(테스트/개발용).
    """
    if is_mock_mode():
        if mock_response is None:
            raise RuntimeError(
                "ANTHROPIC_API_KEY가 설정되지 않았고 mock_response도 제공되지 않았습니다. "
                "실제 배포 전 반드시 API 키를 설정하세요."
            )
        return {"mock": True, **mock_response}

    import anthropic
    client = anthropic.Anthropic(api_key=get_api_key())
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        thinking={"type": "disabled"},
        messages=[{"role": "user", "content": user_message}],
    )

    if resp.stop_reason == "max_tokens":
        raise RuntimeError(
            f"응답이 max_tokens({max_tokens})에 도달해 중간에 잘렸습니다. "
            f"이 호출의 max_tokens를 더 늘려야 합니다. (stop_reason=max_tokens)"
        )

    raw_text = "".join(block.text for block in resp.content if block.type == "text")
    if not raw_text:
        raise RuntimeError(
            f"응답에서 text 블록을 찾지 못했습니다. content 블록 타입들: "
            f"{[getattr(b, 'type', '?') for b in resp.content]}"
        )

    parsed = _extract_json(raw_text)
    return {"mock": False, **parsed}


def _extract_json(raw_text: str) -> dict:
    """
    모델 응답에서 JSON 객체를 견고하게 추출한다.
    1) 그대로 파싱 시도
    2) 마크다운 코드펜스(```json ... ```) 제거 후 재시도
    3) 첫 '{'부터 괄호 깊이를 실제로 세어 정확히 매칭되는 '}'까지만 잘라 파싱
       (naive rfind('}')는 JSON 뒤에 붙은 부가설명에 '}'가 섞이면 깨지므로 사용하지 않는다)
    """
    text = raw_text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

    start = raw_text.find("{")
    if start == -1:
        raise RuntimeError(f"응답에서 JSON 시작 '{{'를 찾지 못했습니다. 응답 앞부분: {raw_text[:300]!r}")

    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(raw_text)):
        ch = raw_text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = raw_text[start:i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError as e:
                    raise RuntimeError(
                        f"괄호는 맞았지만 JSON 파싱에 실패했습니다: {e}\n"
                        f"추출한 텍스트 앞부분: {candidate[:300]!r}"
                    )
    raise RuntimeError(
        f"JSON 괄호가 끝까지 닫히지 않았습니다 (중간에 잘렸을 가능성). "
        f"응답 마지막 부분: {raw_text[-300:]!r}"
    )
