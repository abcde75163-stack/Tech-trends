# -*- coding: utf-8 -*-
"""
기술동향 분석 보고서 자동생성 — Streamlit 위저드 UI (뼈대)
GUIDE_v2.1 STEP1~8을 위저드 화면 흐름으로 구현한다.
현재 구현 범위: STEP1~3 (입력→시나리오 판별→분류 확정) 까지.
STEP4 이후(챕터별 본문 생성~문서 다운로드)는 다음 단계에서 구현 예정.
"""
import streamlit as st
import config
from core.scenario_engine import run_call1
from core.claude_client import is_mock_mode

st.set_page_config(page_title=config.APP_TITLE, page_icon="📊", layout="centered")

if "step" not in st.session_state:
    st.session_state.step = "input"
if "call1_result" not in st.session_state:
    st.session_state.call1_result = None
if "inputs" not in st.session_state:
    st.session_state.inputs = {}

st.title("📊 " + config.APP_TITLE)

if is_mock_mode():
    st.warning(
        "⚠️ ANTHROPIC_API_KEY가 설정되어 있지 않아 **MOCK 모드**로 동작 중입니다. "
        "실제 시나리오 판별·기술 분류 대신 자리표시자가 표시됩니다. "
        "실제 배포 전 `.streamlit/secrets.toml`에 키를 등록하세요.",
        icon="⚠️",
    )

st.progress(
    {"input": 0.15, "confirm": 0.35, "generate": 0.5}.get(st.session_state.step, 0.0)
)

# =================================================================
# STEP 1~3: 입력 화면
# =================================================================
if st.session_state.step == "input":
    st.subheader("STEP 1~3. 기본 정보 입력")

    with st.form("input_form"):
        tech_name = st.text_input("기술명 *", placeholder="예: HBM (High Bandwidth Memory)")

        st.markdown("**의뢰 기관 정보 (선택)** — 없으면 시나리오 A로 진행됩니다")
        org_name = st.text_input("의뢰 기관명", placeholder="예: OO대학교 산학협력단")

        has_capability = st.radio(
            "의뢰 기관의 보유 역량/사업 영역 정보가 있나요?",
            options=[False, True],
            format_func=lambda v: "있음" if v else "없음",
            horizontal=True,
            help="모호한 입력을 방지하기 위해 명시적으로 선택하도록 구성했습니다 "
                 "(Call 1 설계 검토에서 발견된 이슈 반영).",
        )
        org_capability = ""
        if has_capability:
            org_capability = st.text_area(
                "보유 역량/사업 영역 요약",
                placeholder="예: 광섬유 피복 소재 제조 역량 보유",
            )

        uploaded_files = st.file_uploader(
            "첨부파일 (특허 CSV/Excel, 논문 Excel, 특허 명세서 PDF 등)",
            accept_multiple_files=True,
        )

        purpose = st.selectbox(
            "분석 목적",
            ["내부 검토용", "TLO 기술이전", "외부 제출", "직접 입력"],
        )
        if purpose == "직접 입력":
            purpose = st.text_input("분석 목적 직접 입력", value="")

        submitted = st.form_submit_button("다음 단계 (시나리오 판별)", width='stretch')

    if submitted:
        attachment_summary = ", ".join(f.name for f in uploaded_files) if uploaded_files else None
        st.session_state.inputs = dict(
            tech_name=tech_name.strip(),
            org_name=org_name.strip() or None,
            has_capability=has_capability,
            org_capability=org_capability.strip() or None,
            attachment_summary=attachment_summary,
            purpose=purpose or None,
        )
        with st.spinner("시나리오 판별 및 기술 분류 제안 생성 중..."):
            try:
                result = run_call1(**st.session_state.inputs)
            except Exception as e:
                st.error(f"시나리오 판별 중 오류가 발생했습니다:\n\n{e}")
                st.stop()
        st.session_state.call1_result = result

        if result["status"] == "missing_tech_name":
            st.error(result["confirmation_message"])
        else:
            st.session_state.step = "confirm"
            st.rerun()

# =================================================================
# 확인 화면: 시나리오 + 기술분류 확정 (GUIDE 섹션 7 — 한 번만 확인)
# =================================================================
elif st.session_state.step == "confirm":
    st.subheader("시나리오 및 기술 분류 확인")
    result = st.session_state.call1_result

    if result.get("mock"):
        st.info("MOCK 응답입니다 — 실제 API 연결 전 화면 흐름 검증용입니다.", icon="🧪")

    scenario = result["scenario"]
    st.markdown(f"### {config.SCENARIO_LABELS.get(scenario, scenario)}")
    st.caption(result["scenario_reason"])

    st.markdown(f"**기술 분야 유형**: {result['field_type']}")

    st.markdown("**기술 분류 체계 (A~D) — 필요 시 직접 수정 가능**")
    edited = st.data_editor(
        result["classification"],
        column_config={
            "code": st.column_config.TextColumn("분류", disabled=True),
            "name": st.column_config.TextColumn("분류명"),
            "scope": st.column_config.TextColumn("범위"),
        },
        hide_index=True,
        width='stretch',
    )

    st.markdown("---")
    st.write(result["confirmation_message"])

    col1, col2 = st.columns(2)
    with col1:
        if st.button("← 다시 입력", width='stretch'):
            st.session_state.step = "input"
            st.rerun()
    with col2:
        if st.button("이 방향으로 확정하고 다음 단계로 →", type="primary", width='stretch'):
            st.session_state.confirmed_classification = edited
            st.session_state.step = "generate"
            st.rerun()

# =================================================================
# STEP4 이후 (본문 생성) — 플레이스홀더
# =================================================================
# =================================================================
# STEP4~5: 챕터별 본문 생성
# =================================================================
elif st.session_state.step == "generate":
    st.subheader("STEP 4~5. 챕터별 본문 생성")

    confirmed_context = dict(
        tech_name=st.session_state.inputs["tech_name"],
        scenario=st.session_state.call1_result["scenario"],
        org_name=st.session_state.inputs["org_name"],
        org_capability=st.session_state.inputs["org_capability"],
        classification=st.session_state.confirmed_classification,
        purpose=st.session_state.inputs["purpose"],
    )

    if "chapter_results" not in st.session_state:
        st.session_state.chapter_results = None

    if st.session_state.chapter_results is None:
        st.info(f"확정된 시나리오: {config.SCENARIO_LABELS[confirmed_context['scenario']]}")
        if st.button("보고서 본문 생성 시작 (Call 2~6)", type="primary", width='stretch'):
            progress_bar = st.progress(0.0)
            status_text = st.empty()

            def on_progress(idx, total, label):
                progress_bar.progress(idx / total)
                status_text.write(f"{idx}/{total} — {label} 생성 중...")

            from core.report_generator import run_all_calls
            try:
                results = run_all_calls(confirmed_context, progress_callback=on_progress)
            except Exception as e:
                st.error(f"챕터 생성 중 오류가 발생했습니다:\n\n{e}")
                st.stop()
            st.session_state.chapter_results = results
            st.rerun()
    else:
        st.success("Call 2~6 전체 완료")
        any_mock = any(v.get("mock") for v in st.session_state.chapter_results.values())
        if any_mock:
            st.info("MOCK 응답 포함 — 실제 API 연결 전 구조 검증용입니다.", icon="🧪")
        for call_id, label in [("call2", "Ⅰ·Ⅱ장"), ("call3", "Ⅲ·Ⅳ장"), ("call4", "Ⅴ장"),
                                ("call5", "Ⅵ·Ⅶ장"), ("call6", "Ⅷ·Ⅸ장")]:
            with st.expander(f"{label} 결과 보기"):
                st.json(st.session_state.chapter_results[call_id])

        st.markdown("---")
        st.subheader("STEP 6~8. 차트 생성 · 문서 조립 · 다운로드")

        if "docx_buffer" not in st.session_state:
            st.session_state.docx_buffer = None

        if st.session_state.docx_buffer is None:
            if st.button("차트 생성 및 Word 문서 조립", type="primary", width='stretch'):
                try:
                    with st.spinner("차트 6종 생성 중..."):
                        from core.chart_generator import generate_all_charts, ChartDataError
                        chart_images = generate_all_charts(st.session_state.chapter_results)
                    with st.spinner("Word 문서 조립 중..."):
                        from core.docx_builder import build_report_docx
                        import datetime
                        docx_buf = build_report_docx(
                            tech_name=confirmed_context["tech_name"],
                            purpose=confirmed_context["purpose"] or config.DEFAULT_PURPOSE,
                            scenario_label=config.SCENARIO_LABELS[confirmed_context["scenario"]],
                            date_str=datetime.date.today().strftime("%Y년 %m월"),
                            chapter_results=st.session_state.chapter_results,
                            chart_images=chart_images,
                        )
                    st.session_state.docx_buffer = docx_buf
                    st.rerun()
                except ChartDataError as e:
                    st.error(f"차트 데이터 오류: {e}\n\n"
                             f"Call2~6 응답이 기대한 스키마를 따르지 않았을 가능성이 있습니다. "
                             f"실제 API 연결 후 프롬프트 스키마 준수 여부를 재확인해야 합니다.")
                except KeyError as e:
                    st.error(f"챕터 데이터 누락: {e} 키가 없습니다. Call2~6 응답 스키마를 확인하세요.")
        else:
            st.success("문서 생성 완료")
            fname = f"{confirmed_context['tech_name'].replace(' ', '_')}_기술동향분석.docx"
            st.download_button(
                "📥 Word 문서 다운로드",
                data=st.session_state.docx_buffer,
                file_name=fname,
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                type="primary",
                width='stretch',
            )

        if st.button("← 처음부터 다시"):
            for k in ["step", "call1_result", "chapter_results", "docx_buffer"]:
                st.session_state.pop(k, None)
            st.rerun()

