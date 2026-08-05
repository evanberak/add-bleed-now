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
    page_icon="✦",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
        :root { --gold: #d5ad52; --panel: #15171b; --soft: #20242a; }
        .stApp { background: #0c0e11; color: #f4f4f4; }
        [data-testid="stSidebar"] { background: #111318; border-right: 1px solid #292d34; }
        .hero { padding: 1.1rem 1.25rem; border: 1px solid #292d34; border-radius: 18px;
                background: linear-gradient(135deg, #171a20 0%, #0f1115 100%); margin-bottom: 1rem; }
        .hero h1 { margin: 0; letter-spacing: .02em; }
        .hero p { margin: .35rem 0 0; color: #aeb4bd; }
        .status-card { background: #15171b; border: 1px solid #292d34; border-radius: 14px;
                       padding: .8rem 1rem; height: 100%; }
        .status-card strong { color: #d5ad52; }
        div.stButton > button, div.stDownloadButton > button { border-radius: 10px; font-weight: 700; }
        div.stButton > button[kind="primary"] { background: #d5ad52; color: #111; border: none; }
        [data-testid="stFileUploader"] { border: 1px dashed #555d68; border-radius: 14px; padding: .6rem; }
        .small-note { color: #9299a4; font-size: .86rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero">
      <h1>Print Bleed Tool</h1>
      <p>Preserve the original trim artwork. Generate only the missing bleed area.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("Document settings")
    bleed_inches = st.number_input("Bleed on each side (inches)", 0.01, 1.0, 0.125, 0.005, format="%.3f")
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
    protection_strength = st.slider("Foreground protection", 0, 100, 65, disabled=not protect_foreground)
    square_corners = st.toggle("Repair rounded corners", value=True)
    source_strip = st.slider("Edge analysis depth (inches)", 0.10, 1.0, 0.35, 0.05)
    manual_color = st.toggle("Use one background color", value=False)
    color_value = st.color_picker("Background color", "#0054A6", disabled=not manual_color)
    st.caption("MVP: PDFs are processed one page at a time; the first page is used in this release.")

uploaded = st.file_uploader(
    "Upload artwork",
    type=["pdf", "png", "jpg", "jpeg", "tif", "tiff", "webp"],
    help="PDF, PNG, JPG, TIFF, or WebP",
)

if not uploaded:
    st.info("Upload a file to analyze its trim edges and build a bleed preview.")
    st.stop()

try:
    source = read_source(uploaded.getvalue(), uploaded.name, dpi)
except Exception as exc:
    st.error(f"Could not open the file: {exc}")
    st.stop()

metric_columns = st.columns(4)
metric_columns[0].metric("Trim width", f"{source.trim_width_inches:.3f} in")
metric_columns[1].metric("Trim height", f"{source.trim_height_inches:.3f} in")
metric_columns[2].metric("Pages", source.page_count)
metric_columns[3].metric("Render", f"{dpi} DPI")

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

if st.button("Analyze and create bleed", type="primary", use_container_width=True):
    with st.spinner("Analyzing edges and creating the bleed layer…"):
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
    left, right = st.columns(2)
    with left:
        st.subheader("Original")
        st.image(source.preview, use_container_width=True)
    with right:
        st.subheader("Ready to process")
        st.markdown(
            '<div class="status-card"><strong>Original trim protection</strong><br>'
            'The processing engine restores the original trim pixels after generating the outside bleed.</div>',
            unsafe_allow_html=True,
        )
    st.stop()

result = job["result"]
left, right = st.columns(2)
with left:
    st.subheader("Original")
    st.image(job["source_preview"], use_container_width=True)
with right:
    st.subheader("Bleed preview")
    st.image(job["preview"], use_container_width=True)
    st.caption("Red = trim boundary · Blue = finished bleed boundary")

status_columns = st.columns(3)
status_columns[0].markdown(
    f'<div class="status-card"><strong>Quality</strong><br>{result.quality_label}</div>',
    unsafe_allow_html=True,
)
status_columns[1].markdown(
    f'<div class="status-card"><strong>Bleed</strong><br>{settings.bleed_inches:.3f} in / {result.bleed_pixels} px</div>',
    unsafe_allow_html=True,
)
status_columns[2].markdown(
    f'<div class="status-card"><strong>Finished size</strong><br>'
    f'{source.trim_width_inches + settings.bleed_inches * 2:.3f} × '
    f'{source.trim_height_inches + settings.bleed_inches * 2:.3f} in</div>',
    unsafe_allow_html=True,
)

if result.warnings:
    for warning in result.warnings:
        st.warning(warning)
else:
    st.success("No automatic-review warnings were triggered.")

st.subheader("Edge analysis")
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
download_columns = st.columns(3)
with download_columns[0]:
    st.download_button(
        "Download print-ready PDF",
        data=job["pdf"],
        file_name=f"{stem}_bleed.pdf",
        mime="application/pdf",
        use_container_width=True,
    )
with download_columns[1]:
    st.download_button(
        "Download PNG",
        data=job["png"],
        file_name=f"{stem}_bleed.png",
        mime="image/png",
        use_container_width=True,
    )
with download_columns[2]:
    st.download_button(
        "Download report",
        data=json.dumps(job["report"], indent=2),
        file_name=f"{stem}_bleed_report.json",
        mime="application/json",
        use_container_width=True,
    )
