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
            --line: #d8dee8;
            --text: #111827;
            --muted: #667085;
            --blue: #2f80ed;
            --shadow: 0 8px 24px rgba(15, 23, 42, 0.07);
        }

        html, body, [class*="css"], [data-testid="stAppViewContainer"], .stApp {
            font-family: Inter, ui-sans-serif, system-ui, -apple-system,
                         BlinkMacSystemFont, "Segoe UI", sans-serif;
            color: var(--text);
        }

        .stApp {
            background: var(--bg);
        }

        [data-testid="stHeader"] {
            background: rgba(243, 244, 246, 0.94);
        }

        [data-testid="stSidebar"] {
            background: #f8fafc;
            border-right: 1px solid var(--line);
        }

        [data-testid="stSidebar"] * {
            color: var(--text) !important;
        }

        .block-container {
            max-width: 1400px;
            padding-top: 1.4rem;
            padding-bottom: 2.5rem;
        }

        h1, h2, h3 {
            color: var(--text);
            letter-spacing: -0.02em;
        }

        h1 {
            font-size: 1.7rem !important;
            font-weight: 750 !important;
            margin-bottom: 1rem !important;
        }

        h2 {
            font-size: 1.15rem !important;
            font-weight: 700 !important;
            margin-top: 1.25rem !important;
            margin-bottom: 0.8rem !important;
        }

        [data-testid="stFileUploader"] {
            background: var(--panel);
            border: 2px dashed #8fc5ff;
            border-radius: 18px;
            padding: 0.9rem;
            box-shadow: var(--shadow);
        }

        [data-testid="stFileUploader"] section {
            padding: 0.8rem 0.25rem;
        }

        [data-testid="stFileUploader"] * {
            color: var(--text) !important;
        }

        .metric-card,
        .status-card,
        .preview-card,
        .download-card {
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 16px;
            box-shadow: var(--shadow);
        }

        .metric-card,
        .status-card {
            padding: 0.95rem 1rem;
            height: 100%;
        }

        .metric-label,
        .status-label {
            color: var(--muted);
            font-size: 0.78rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            margin-bottom: 0.3rem;
        }

        .metric-value,
        .status-value {
            color: var(--text);
            font-size: 1.08rem;
            font-weight: 700;
            line-height: 1.25;
        }

        .preview-card {
            padding: 0.85rem;
        }

        .download-card {
            padding: 0.75rem;
        }

        div.stButton > button,
        div.stDownloadButton > button {
            border-radius: 12px !important;
            border: 1px solid var(--blue) !important;
            background: var(--blue) !important;
            color: #ffffff !important;
            font-weight: 700 !important;
            min-height: 44px;
        }

        div.stButton > button:hover,
        div.stDownloadButton > button:hover {
            background: #1f6fdd !important;
            border-color: #1f6fdd !important;
            color: #ffffff !important;
        }

        .stTabs [data-baseweb="tab-list"] {
            gap: 0.35rem;
            background: #e9edf3;
            padding: 0.3rem;
            border-radius: 999px;
        }

        .stTabs [data-baseweb="tab"] {
            border-radius: 999px !important;
            padding: 0.5rem 0.95rem !important;
            color: var(--muted) !important;
            font-weight: 650 !important;
        }

        .stTabs [aria-selected="true"] {
            background: #ffffff !important;
            color: var(--text) !important;
            box-shadow: 0 2px 8px rgba(15, 23, 42, 0.08);
        }

        .stAlert {
            border-radius: 14px;
        }

        div[data-testid="stDataFrame"] {
            border: 1px solid var(--line);
            border-radius: 14px;
            overflow: hidden;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Print Bleed Tool")

with st.sidebar:
    st.header("Settings")

    bleed_inches = st.number_input(
        "Bleed",
        min_value=0.01,
        max_value=1.0,
        value=0.125,
        step=0.005,
        format="%.3f",
    )

    dpi = st.select_slider(
        "Resolution",
        options=[150, 200, 240, 300, 400, 600],
        value=300,
    )

    mode_label = st.selectbox(
        "Extension Mode",
        options=[
            "Background Only",
            "Automatic",
            "Edge Stretch",
            "Mirror Edge",
        ],
        index=0,
    )

    mode_map = {
        "Background Only": ExtensionMode.BACKGROUND_ONLY,
        "Automatic": ExtensionMode.AUTOMATIC,
        "Edge Stretch": ExtensionMode.EDGE_STRETCH,
        "Mirror Edge": ExtensionMode.MIRROR,
    }

    protect_foreground = st.toggle("Foreground Protection", value=True)

    protection_strength = st.slider(
        "Protection Strength",
        min_value=0,
        max_value=100,
        value=65,
        disabled=not protect_foreground,
    )

    square_corners = st.toggle("Square Corners", value=True)

    source_strip = st.slider(
        "Analysis Depth",
        min_value=0.10,
        max_value=1.0,
        value=0.35,
        step=0.05,
    )

    manual_color = st.toggle("Solid Background", value=False)

    color_value = st.color_picker(
        "Background Color",
        "#0054A6",
        disabled=not manual_color,
    )

st.header("Upload Artwork")

uploaded = st.file_uploader(
    "Upload Artwork",
    type=["pdf", "png", "jpg", "jpeg", "tif", "tiff", "webp"],
    label_visibility="collapsed",
)

if not uploaded:
    st.stop()

try:
    source = read_source(uploaded.getvalue(), uploaded.name, dpi)
except Exception as exc:
    st.error(str(exc))
    st.stop()

st.header("Document")

overview_cols = st.columns(4)
overview_values = [
    ("Trim Width", f"{source.trim_width_inches:.3f} in"),
    ("Trim Height", f"{source.trim_height_inches:.3f} in"),
    ("Pages", str(source.page_count)),
    ("Resolution", f"{dpi} DPI"),
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

if st.button("Create Bleed", type="primary", use_container_width=True):
    with st.spinner("Processing"):
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
    st.header("Preview")
    st.markdown('<div class="preview-card">', unsafe_allow_html=True)
    st.image(source.preview, use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)
    st.stop()

result = job["result"]

st.header("Processing")

status_cols = st.columns(3)
status_data = [
    ("Quality", result.quality_label),
    ("Bleed", f"{settings.bleed_inches:.3f} in"),
    (
        "Finished Size",
        f"{source.trim_width_inches + settings.bleed_inches * 2:.3f} × "
        f"{source.trim_height_inches + settings.bleed_inches * 2:.3f} in",
    ),
]

for column, (label, value) in zip(status_cols, status_data):
    with column:
        st.markdown(
            f"""
            <div class="status-card">
                <div class="status-label">{label}</div>
                <div class="status-value">{value}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

for warning in result.warnings:
    st.warning(warning)

st.header("Preview")

original_tab, bleed_tab = st.tabs(["Original", "Bleed"])

with original_tab:
    st.markdown('<div class="preview-card">', unsafe_allow_html=True)
    st.image(job["source_preview"], use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

with bleed_tab:
    st.markdown('<div class="preview-card">', unsafe_allow_html=True)
    st.image(job["preview"], use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

st.header("Edge Analysis")

st.dataframe(
    [
        {
            "Edge": edge.title(),
            "Classification": report.kind.value.title(),
            "Confidence": f"{report.confidence:.0%}",
            "Foreground Risk": f"{report.foreground_risk:.0%}",
            "Seam Score": f"{result.seam_scores[edge]:.1f}/100",
        }
        for edge, report in result.edge_analysis.items()
    ],
    use_container_width=True,
    hide_index=True,
)

st.header("Downloads")

stem = job["stem"]
download_cols = st.columns(3)

with download_cols[0]:
    st.markdown('<div class="download-card">', unsafe_allow_html=True)
    st.download_button(
        "Print-Ready PDF",
        data=job["pdf"],
        file_name=f"{stem}_bleed.pdf",
        mime="application/pdf",
        use_container_width=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)

with download_cols[1]:
    st.markdown('<div class="download-card">', unsafe_allow_html=True)
    st.download_button(
        "PNG",
        data=job["png"],
        file_name=f"{stem}_bleed.png",
        mime="image/png",
        use_container_width=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)

with download_cols[2]:
    st.markdown('<div class="download-card">', unsafe_allow_html=True)
    st.download_button(
        "Report",
        data=json.dumps(job["report"], indent=2),
        file_name=f"{stem}_bleed_report.json",
        mime="application/json",
        use_container_width=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)
