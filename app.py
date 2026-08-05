from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from analyzer import analyze_document
from bleed import generate_bleed
from document import read_source
from exporter import export_pdf_bytes, export_png_bytes
from models import BleedSettings, ExtensionMode
from preview import add_preview_guides


st.set_page_config(
    page_title="Print Bleed Tool",
    page_icon="🖨️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
        :root {
            --bg: #f3f4f6;
            --panel: #ffffff;
            --panel-2: #f8fafc;
            --line: #d9dee7;
            --line-strong: #c8d1df;
            --text: #111827;
            --muted: #667085;
            --soft: #8a94a6;
            --blue: #4da3ff;
            --blue-strong: #2f80ed;
            --blue-soft: #ebf5ff;
            --shadow: 0 10px 30px rgba(15, 23, 42, 0.08);
            --radius-lg: 22px;
            --radius-md: 16px;
            --radius-sm: 12px;
        }

        html, body, [class*="css"], [data-testid="stAppViewContainer"], .stApp {
            font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            color: var(--text);
        }

        .stApp {
            background: var(--bg);
        }

        [data-testid="stHeader"] {
            background: rgba(243, 244, 246, 0.85);
            backdrop-filter: blur(6px);
        }

        [data-testid="stSidebar"] {
            background: #f7f8fb;
            border-right: 1px solid var(--line);
        }

        [data-testid="stSidebar"] * {
            color: var(--text) !important;
        }

        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] div[data-baseweb="select"] *,
        [data-testid="stSidebar"] .st-bq,
        [data-testid="stSidebar"] .stCaption {
            color: var(--text) !important;
        }

        .block-container {
            max-width: 1400px;
            padding-top: 1.4rem;
            padding-bottom: 2.5rem;
        }

        .shell-card {
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: var(--radius-lg);
            box-shadow: var(--shadow);
            padding: 1.1rem 1.2rem;
        }

        .topbar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
            padding: 0.1rem 0.15rem 0.7rem 0.15rem;
            margin-bottom: 0.9rem;
        }

        .topbar-title {
            font-size: 1.55rem;
            font-weight: 700;
            letter-spacing: -0.02em;
            color: var(--text);
            margin: 0;
        }

        .topbar-subtitle {
            margin: 0.15rem 0 0 0;
            color: var(--muted);
            font-size: 0.96rem;
        }

        .topbar-badge {
            display: inline-flex;
            align-items: center;
            gap: 0.45rem;
            background: var(--blue-soft);
            color: var(--blue-strong);
            border: 1px solid #cfe6ff;
            padding: 0.6rem 0.8rem;
            border-radius: 999px;
            font-size: 0.88rem;
            font-weight: 600;
            white-space: nowrap;
        }

        .upload-card {
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: var(--radius-lg);
            box-shadow: var(--shadow);
            padding: 1rem;
            margin-bottom: 1rem;
        }

        .upload-card h3 {
            margin: 0 0 0.3rem 0;
            font-size: 1.08rem;
            color: var(--text);
        }

        .upload-card p {
            margin: 0 0 0.9rem 0;
            color: var(--muted);
            line-height: 1.45;
        }

        [data-testid="stFileUploader"] {
            background: linear-gradient(180deg, #fbfdff 0%, #f8fbff 100%);
            border: 2px dashed #9fcfff;
            border-radius: 20px;
            padding: 1rem;
        }

        [data-testid="stFileUploader"] section {
            padding: 1rem 0.25rem;
        }

        [data-testid="stFileUploader"] small,
        [data-testid="stFileUploader"] span,
        [data-testid="stFileUploader"] div {
            color: var(--text);
        }

        .metric-card {
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: var(--radius-md);
            padding: 0.95rem 1rem;
            box-shadow: 0 8px 22px rgba(15, 23, 42, 0.05);
            height: 100%;
        }

        .metric-label {
            color: var(--muted);
            font-size: 0.84rem;
            font-weight: 600;
            margin-bottom: 0.3rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        .metric-value {
            color: var(--text);
            font-size: 1.2rem;
            font-weight: 700;
            line-height: 1.15;
        }

        .section-title {
            font-size: 1.02rem;
            font-weight: 700;
            color: var(--text);
            margin: 0 0 0.8rem 0;
        }

        .status-card {
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: var(--radius-md);
            box-shadow: 0 8px 22px rgba(15, 23, 42, 0.05);
            padding: 0.9rem 1rem;
            min-height: 102px;
        }

        .status-title {
            color: var(--muted);
            font-size: 0.82rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 0.35rem;
        }

        .status-main {
            color: var(--text);
            font-size: 1.03rem;
            font-weight: 700;
            line-height: 1.25;
        }

        .status-sub {
            color: var(--muted);
            font-size: 0.9rem;
            margin-top: 0.25rem;
        }

        .info-panel {
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: var(--radius-md);
            padding: 1rem;
            box-shadow: 0 8px 22px rgba(15, 23, 42, 0.05);
        }

        .preview-frame {
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: var(--radius-md);
            padding: 0.9rem;
            box-shadow: 0 8px 22px rgba(15, 23, 42, 0.05);
        }

        .preview-caption {
            color: var(--muted);
            font-size: 0.84rem;
            margin-top: 0.45rem;
        }

        .pill-note {
            display: inline-flex;
            background: var(--blue-soft);
            border: 1px solid #d5e9ff;
            color: var(--blue-strong);
            padding: 0.35rem 0.65rem;
            border-radius: 999px;
            font-size: 0.8rem;
            font-weight: 600;
            margin-top: 0.35rem;
        }

        .warning-box, .success-box {
            border-radius: var(--radius-md);
            padding: 0.95rem 1rem;
            margin-bottom: 0.75rem;
            border: 1px solid transparent;
            font-size: 0.94rem;
            line-height: 1.45;
        }

        .warning-box {
            background: #fff7ed;
            border-color: #fed7aa;
            color: #9a3412;
        }

        .success-box {
            background: #ecfdf3;
            border-color: #a7f3d0;
            color: #166534;
        }

        .download-card {
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: var(--radius-md);
            padding: 0.85rem;
            box-shadow: 0 8px 22px rgba(15, 23, 42, 0.05);
        }

        div.stButton > button,
        div.stDownloadButton > button {
            border-radius: 14px !important;
            border: 1px solid #2f80ed !important;
            background: linear-gradient(180deg, #63b3ff 0%, #2f80ed 100%) !important;
            color: white !important;
            font-weight: 700 !important;
            min-height: 46px;
        }

        div.stButton > button:hover,
        div.stDownloadButton > button:hover {
            border-color: #1f6fdd !important;
            background: linear-gradient(180deg, #54abff 0%, #1f6fdd 100%) !important;
            color: white !important;
        }

        [data-testid="stBaseButton-secondary"] {
            border-radius: 12px !important;
        }

        .stTabs [data-baseweb="tab-list"] {
            gap: 0.4rem;
            background: #eef2f7;
            padding: 0.35rem;
            border-radius: 999px;
        }

        .stTabs [data-baseweb="tab"] {
            border-radius: 999px !important;
            padding: 0.55rem 1rem !important;
            color: var(--muted) !important;
            font-weight: 600 !important;
        }

        .stTabs [aria-selected="true"] {
            background: white !important;
            color: var(--text) !important;
            box-shadow: 0 3px 10px rgba(15, 23, 42, 0.08);
        }

        .stAlert {
            border-radius: 14px;
        }

        .stDataFrame, div[data-testid="stDataFrame"] {
            border-radius: 14px !important;
            overflow: hidden;
            border: 1px solid var(--line);
        }

        div[data-testid="stMetric"] {
            background: transparent;
        }

        .st-emotion-cache-1r4qj8v, .st-emotion-cache-1wmy9hl {
            color: var(--text) !important;
        }

        .sidebar-card {
            background: white;
            border: 1px solid var(--line);
            border-radius: 18px;
            padding: 0.9rem 1rem;
            margin-bottom: 0.9rem;
            box-shadow: 0 6px 18px rgba(15, 23, 42, 0.05);
        }

        .sidebar-card h4 {
            margin: 0 0 0.35rem 0;
            color: var(--text);
            font-size: 1rem;
        }

        .sidebar-card p {
            margin: 0;
            color: var(--muted);
            font-size: 0.9rem;
            line-height: 1.45;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="topbar">
        <div>
            <h1 class="topbar-title">Print Bleed Tool</h1>
            <p class="topbar-subtitle">Clean, readable workflow for adding bleed while preserving the original trim artwork.</p>
        </div>
        <div class="topbar-badge">● UI refreshed to a soft white + blue workspace</div>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown(
        """
        <div class="sidebar-card">
            <h4>Workspace</h4>
            <p>Use this panel to control bleed size, processing mode, and output settings.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.subheader("Document settings")
    bleed_inches = st.number_input(
        "Bleed on each side (inches)",
        min_value=0.01,
        max_value=1.0,
        value=0.125,
        step=0.005,
        format="%.3f",
    )
    dpi = st.select_slider("Processing resolution", options=[150, 200, 240, 300, 400, 600], value=300)

    mode_label = st.selectbox(
        "Extension mode",
        options=[
            "Background only",
            "Automatic",
            "Edge stretch",
            "Mirror edge",
        ],
        index=0,
    )
    mode_map = {
        "Background only": ExtensionMode.BACKGROUND_ONLY,
        "Automatic": ExtensionMode.AUTOMATIC,
        "Edge stretch": ExtensionMode.EDGE_STRETCH,
        "Mirror edge": ExtensionMode.MIRROR,
    }

    protect_foreground = st.toggle("Suppress foreground in bleed", value=True)
    protection_strength = st.slider(
        "Foreground protection",
        min_value=0,
        max_value=100,
        value=65,
        disabled=not protect_foreground,
    )
    square_corners = st.toggle("Repair rounded corners", value=True)
    source_strip = st.slider("Edge analysis depth (inches)", 0.10, 1.0, 0.35, 0.05)

    manual_color = st.toggle("Use one background color", value=False)
    color_value = st.color_picker("Background color", "#0054A6", disabled=not manual_color)

    st.markdown(
        """
        <div class="sidebar-card">
            <h4>Tip</h4>
            <p>This release uses the first page of a PDF. The original trim artwork is restored inside the final file after bleed generation.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown(
    """
    <div class="upload-card">
        <h3>Upload artwork</h3>
        <p>Drag and drop a PDF or image file to start. The layout and text colors are tuned for readability in this lighter interface style.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

uploaded = st.file_uploader(
    "Upload artwork",
    type=["pdf", "png", "jpg", "jpeg", "tif", "tiff", "webp"],
    help="Supported formats: PDF, PNG, JPG, JPEG, TIFF, or WebP",
    label_visibility="collapsed",
)

if not uploaded:
    st.markdown(
        """
        <div class="info-panel">
            <div class="section-title">Ready to start</div>
            <div style="color:#667085; line-height:1.5;">
                Upload a file to analyze the trim edges and generate a bleed preview. The app will preserve the original trim artwork and only build content outside trim.
            </div>
            <div class="pill-note">Best for bag stuffers, flyers, cards, and simple print pieces</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.stop()

try:
    source = read_source(uploaded.getvalue(), uploaded.name, dpi)
except Exception as exc:
    st.error(f"Could not open the file: {exc}")
    st.stop()

overview_cols = st.columns(4)
overview_values = [
    ("Trim width", f"{source.trim_width_inches:.3f} in"),
    ("Trim height", f"{source.trim_height_inches:.3f} in"),
    ("Pages", str(source.page_count)),
    ("Render", f"{dpi} DPI"),
]
for column, (label, value) in zip(overview_cols, overview_values):
    with column:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">{label}</div>
                <div class="metric-value">{value}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

settings = BleedSettings(
    bleed_inches=float(bleed_inches),
    dpi=int(dpi),
    extension_mode=mode_map[mode_label],
    protect_foreground=bool(protect_foreground),
    protection_strength=int(protection_strength),
    square_corners=bool(square_corners),
    manual_background_hex=color_value if manual_color else None,
    source_strip_inches=float(source_strip),
)

generate_col, note_col = st.columns([1.15, 1.85])
with generate_col:
    run_clicked = st.button("Analyze and create bleed", type="primary", use_container_width=True)
with note_col:
    st.markdown(
        """
        <div class="info-panel">
            <div class="section-title">Processing notes</div>
            <div style="color:#667085; line-height:1.5;">
                Background Only mode is best when the outside bleed should continue a matching backdrop and should not duplicate text, food, or other artwork.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

if run_clicked:
    with st.spinner("Analyzing edges and creating the bleed layer..."):
        strip_pixels = max(8, round(settings.source_strip_inches * settings.dpi))
        analysis = analyze_document(source.preview, strip_pixels)
        result = generate_bleed(source.preview, settings, analysis)
        preview = add_preview_guides(result.image, result.bleed_pixels)
        pdf_bytes = export_pdf_bytes(source, result, settings)
        png_bytes = export_png_bytes(result, settings.dpi)
        report = result.report_dict(source, settings)
        st.session_state["bleed_job"] = {
            "result": result,
            "preview": preview,
            "pdf": pdf_bytes,
            "png": png_bytes,
            "report": report,
            "source_preview": source.preview,
            "stem": Path(source.filename).stem,
        }

job = st.session_state.get("bleed_job")
if not job:
    tabs = st.tabs(["Original"])
    with tabs[0]:
        st.markdown('<div class="preview-frame">', unsafe_allow_html=True)
        st.image(source.preview, use_container_width=True)
        st.markdown(
            '<div class="preview-caption">Original artwork preview</div></div>',
            unsafe_allow_html=True,
        )
    st.stop()

result = job["result"]

status_cols = st.columns(3)
status_data = [
    ("Quality", result.quality_label, "Overall processing confidence"),
    ("Bleed", f'{settings.bleed_inches:.3f} in / {result.bleed_pixels} px', "Bleed on each side"),
    (
        "Finished size",
        f'{source.trim_width_inches + settings.bleed_inches * 2:.3f} × {source.trim_height_inches + settings.bleed_inches * 2:.3f} in',
        "Trim size plus bleed",
    ),
]
for column, (title, main, sub) in zip(status_cols, status_data):
    with column:
        st.markdown(
            f"""
            <div class="status-card">
                <div class="status-title">{title}</div>
                <div class="status-main">{main}</div>
                <div class="status-sub">{sub}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

st.markdown('<div class="section-title" style="margin-top:1.1rem;">Preview</div>', unsafe_allow_html=True)
tab_original, tab_preview = st.tabs(["Original", "Bleed preview"])

with tab_original:
    st.markdown('<div class="preview-frame">', unsafe_allow_html=True)
    st.image(job["source_preview"], use_container_width=True)
    st.markdown('<div class="preview-caption">Source artwork</div></div>', unsafe_allow_html=True)

with tab_preview:
    st.markdown('<div class="preview-frame">', unsafe_allow_html=True)
    st.image(job["preview"], use_container_width=True)
    st.markdown(
        '<div class="preview-caption">Red = trim boundary · Blue = finished bleed boundary</div></div>',
        unsafe_allow_html=True,
    )

st.markdown('<div class="section-title" style="margin-top:1.15rem;">Processing feedback</div>', unsafe_allow_html=True)
if result.warnings:
    for warning in result.warnings:
        st.markdown(f'<div class="warning-box">{warning}</div>', unsafe_allow_html=True)
else:
    st.markdown(
        '<div class="success-box">No automatic review warnings were triggered.</div>',
        unsafe_allow_html=True,
    )

st.markdown('<div class="section-title" style="margin-top:1rem;">Edge analysis</div>', unsafe_allow_html=True)
st.dataframe(
    [
        {
            "Edge": edge.title(),
            "Classification": report.kind.value.title(),
            "Confidence": f"{report.confidence:.0%}",
            "Foreground risk": f"{report.foreground_risk:.0%}",
            "Seam score": f"{result.seam_scores[edge]:.1f}/100",
        }
        for edge, report in result.edge_analysis.items()
    ],
    use_container_width=True,
    hide_index=True,
)

stem = job["stem"]
st.markdown('<div class="section-title" style="margin-top:1rem;">Downloads</div>', unsafe_allow_html=True)
download_cols = st.columns(3)
with download_cols[0]:
    st.markdown('<div class="download-card">', unsafe_allow_html=True)
    st.download_button(
        "Download print-ready PDF",
        data=job["pdf"],
        file_name=f"{stem}_bleed.pdf",
        mime="application/pdf",
        use_container_width=True,
    )
    st.markdown('</div>', unsafe_allow_html=True)
with download_cols[1]:
    st.markdown('<div class="download-card">', unsafe_allow_html=True)
    st.download_button(
        "Download PNG",
        data=job["png"],
        file_name=f"{stem}_bleed.png",
        mime="image/png",
        use_container_width=True,
    )
    st.markdown('</div>', unsafe_allow_html=True)
with download_cols[2]:
    st.markdown('<div class="download-card">', unsafe_allow_html=True)
    st.download_button(
        "Download report",
        data=json.dumps(job["report"], indent=2),
        file_name=f"{stem}_bleed_report.json",
        mime="application/json",
        use_container_width=True,
    )
    st.markdown('</div>', unsafe_allow_html=True)
