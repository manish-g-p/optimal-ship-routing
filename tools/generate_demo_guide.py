from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, KeepTogether,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "Nautilus_Demo_Guide.pdf"

NAVY = colors.HexColor("#0b1a2b")
INK = colors.HexColor("#172033")
MUTED = colors.HexColor("#536579")
CYAN = colors.HexColor("#0ea5e9")
RED = colors.HexColor("#e11d48")
PALE_BLUE = colors.HexColor("#eaf7ff")
PALE_RED = colors.HexColor("#fff0f3")
PALE_GREY = colors.HexColor("#f4f7fa")


styles = getSampleStyleSheet()
styles.add(ParagraphStyle(
    name="CoverTitle", parent=styles["Title"], fontName="Helvetica-Bold",
    fontSize=31, leading=35, textColor=colors.white, alignment=TA_LEFT,
    spaceAfter=12,
))
styles.add(ParagraphStyle(
    name="CoverSub", parent=styles["Normal"], fontName="Helvetica",
    fontSize=14, leading=20, textColor=colors.HexColor("#c9e9f8"),
))
styles.add(ParagraphStyle(
    name="H1N", parent=styles["Heading1"], fontName="Helvetica-Bold",
    fontSize=20, leading=24, textColor=NAVY, spaceBefore=4, spaceAfter=10,
))
styles.add(ParagraphStyle(
    name="H2N", parent=styles["Heading2"], fontName="Helvetica-Bold",
    fontSize=13, leading=17, textColor=CYAN, spaceBefore=10, spaceAfter=5,
))
styles.add(ParagraphStyle(
    name="BodyN", parent=styles["BodyText"], fontName="Helvetica",
    fontSize=9.5, leading=14, textColor=INK, spaceAfter=6,
))
styles.add(ParagraphStyle(
    name="SmallN", parent=styles["BodyText"], fontName="Helvetica",
    fontSize=8, leading=11, textColor=MUTED, spaceAfter=4,
))
styles.add(ParagraphStyle(
    name="Callout", parent=styles["BodyText"], fontName="Helvetica-Bold",
    fontSize=10, leading=14, textColor=NAVY, backColor=PALE_BLUE,
    borderColor=CYAN, borderWidth=1, borderPadding=9, spaceBefore=5,
    spaceAfter=10,
))
styles.add(ParagraphStyle(
    name="CodeN", parent=styles["Code"], fontName="Courier",
    fontSize=8.2, leading=11, textColor=colors.HexColor("#dbeafe"),
    backColor=NAVY, borderPadding=8, spaceBefore=4, spaceAfter=8,
))
styles.add(ParagraphStyle(
    name="TableN", parent=styles["BodyText"], fontName="Helvetica",
    fontSize=7.7, leading=10, textColor=INK,
))
styles.add(ParagraphStyle(
    name="TableHead", parent=styles["BodyText"], fontName="Helvetica-Bold",
    fontSize=7.7, leading=10, textColor=colors.white,
))


def p(text, style="BodyN"):
    return Paragraph(text, styles[style])


def bullet(text):
    return p("&#8226; " + text, "BodyN")


def code(text):
    return p(text.replace("\n", "<br/>"), "CodeN")


def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#d9e2ec"))
    canvas.line(18 * mm, 14 * mm, 192 * mm, 14 * mm)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, 9 * mm, "Nautilus | Optimal Ship Routing System")
    canvas.drawRightString(192 * mm, 9 * mm, f"Demo guide | {doc.page}")
    canvas.restoreState()


class DemoDoc(BaseDocTemplate):
    def __init__(self, filename):
        super().__init__(filename, pagesize=A4, rightMargin=18 * mm,
                         leftMargin=18 * mm, topMargin=17 * mm,
                         bottomMargin=20 * mm, title="Nautilus Demo Guide",
                         author="Nautilus project")
        frame = Frame(self.leftMargin, self.bottomMargin, self.width,
                      self.height, id="normal")
        self.addPageTemplates([PageTemplate(id="main", frames=frame,
                                            onPage=footer)])


def table(data, widths, header=True):
    converted = []
    for r, row in enumerate(data):
        converted.append([p(str(cell), "TableHead" if header and r == 0 else "TableN")
                          for cell in row])
    t = Table(converted, colWidths=widths, repeatRows=1 if header else 0)
    commands = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d5dee8")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]
    if header:
        commands += [("BACKGROUND", (0, 0), (-1, 0), NAVY)]
        if len(data) > 1:
            commands += [("BACKGROUND", (0, 1), (-1, -1), colors.white),
                         ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                          [colors.white, PALE_GREY])]
    t.setStyle(TableStyle(commands))
    return t


def build_story():
    story = []
    story.append(Spacer(1, 28 * mm))
    story.append(p("NAUTILUS", "CoverTitle"))
    story.append(p("Optimal Ship Routing System", "CoverSub"))
    story.append(Spacer(1, 9 * mm))
    story.append(p("Project demonstration guide", "CoverSub"))
    story.append(Spacer(1, 55 * mm))
    story.append(p("A weather-aware routing prototype for vessels travelling around India, combining safe-water constraints, wave data, pathfinding, and an ML-based speed model.", "CoverSub"))
    story.append(Spacer(1, 20 * mm))
    story.append(p("Recommended demo: Cochin (Kerala) to Dubai / Jebel Ali (UAE)", "Callout"))
    story.append(PageBreak())

    story.append(p("1. The project in one minute", "H1N"))
    story.append(p("Nautilus answers a practical question: should a ship follow the shortest safe route, or take a slightly longer route to avoid difficult sea conditions? The system models the sea around India as a navigable grid and compares two searches on the same grid."))
    story.append(table([
        ["Component", "Role in the system"],
        ["GEBCO bathymetry", "Identifies water depth and removes shallow cells."],
        ["ERA5 wave data", "Provides significant wave height, direction, and period."],
        ["Safety mask", "Keeps routes in open water and away from the coast buffer."],
        ["Dijkstra", "Traditional baseline: minimum safe distance."],
        ["A* + ML", "Proposed method: travel-time cost adjusted for vessel speed loss in waves."],
        ["Web interfaces", "Flask + Google Maps for the polished demo; Streamlit for an offline fallback."],
    ], [42 * mm, 132 * mm]))
    story.append(Spacer(1, 6))
    story.append(p("Core message for the audience", "H2N"))
    story.append(p("The proposed route is not simply the shortest line on a map. It is a safe route whose cost reflects how waves and vessel characteristics affect achievable speed. The result is a transparent trade-off between distance, time, and sea state.", "Callout"))

    story.append(p("2. What happens inside", "H1N"))
    story.append(p("The system has an offline preparation stage and a fast demo stage."))
    story.append(table([
        ["Stage", "What happens", "Output"],
        ["Preprocess", "Extract the configured region from large NetCDF files, downsample, and aggregate wave scenarios.", "bathymetry.npz, weather.npz, weather_grid.csv"],
        ["Build grid", "Mark cells navigable only when depth and coast-distance rules are satisfied.", "grid.npz"],
        ["Train/load model", "Random Forest predicts attainable speed from waves and vessel parameters.", "speed_model.joblib"],
        ["Route request", "Snap ports to grid cells and run Dijkstra and/or A*.", "Path, distance, time, waves, explored cells"],
    ], [29 * mm, 90 * mm, 55 * mm]))
    story.append(p("Important configuration", "H2N"))
    story.append(bullet("Region: latitude 0 to 27 N, longitude 50 to 100 E."))
    story.append(bullet("Grid: 0.05 degrees, approximately 5.5 km per cell."))
    story.append(bullet("Safety: minimum depth 10 m and coast buffer 22 km."))
    story.append(bullet("A* weather cost uses wave height, head-sea direction, wave period, and the ML-predicted speed multiplier."))

    story.append(PageBreak())
    story.append(p("3. Prepare the demo", "H1N"))
    story.append(p("The repository already contains the processed artifacts needed for normal startup. For a fresh machine, install Python 3.10 or newer and the dependencies first."))
    story.append(code("python -m venv .venv\n.\\.venv\\Scripts\\Activate.ps1\npython -m pip install --upgrade pip\npip install -r requirements.txt"))
    story.append(p("Choose one interface", "H2N"))
    story.append(table([
        ["Interface", "Command", "When to use"],
        ["Flask + Google Maps", "$env:GOOGLE_MAPS_API_KEY = \"your-key\"\npython server.py", "Best visual presentation. Requires a valid Google Maps JavaScript API key."],
        ["Streamlit + Folium", "streamlit run app.py", "Best fallback when no Google Maps key is available. Works from local processed data."],
    ], [37 * mm, 67 * mm, 70 * mm]))
    story.append(p("Open the application at <b>http://localhost:8000</b> for Flask or <b>http://localhost:8501</b> for Streamlit.", "Callout"))
    story.append(p("If the processed artifacts are missing", "H2N"))
    story.append(code("python -m src.preprocess\npython -m src.ml_model"))
    story.append(p("Preprocessing reads the large raw NetCDF files and can require several GB of memory. It is normally a one-time operation; the demo itself loads the smaller files in data/processed/."))

    story.append(p("4. Recommended live demonstration", "H1N"))
    steps = [
        ("1", "Introduce the problem", "Explain that a shortest-distance route can cross rougher water, slow the vessel, and increase operational risk."),
        ("2", "Set the voyage", "Select Container Ship, Cochin (Kerala) as Origin, and Dubai / Jebel Ali (UAE) as Destination."),
        ("3", "Show the baseline", "Keep Dijkstra and Weather-aware A* enabled. Keep the Wave heatmap and ML speed model enabled."),
        ("4", "Run typical weather", "Click Find optimal route. Point out the blue traditional route, red proposed route, endpoint markers, wave colors, and comparison cards."),
        ("5", "Switch to rough weather", "Select Rough and run again. Explain that the same voyage is re-evaluated under a more difficult sea state."),
        ("6", "Inspect the evidence", "Compare distance, estimated time, maximum wave, minimum coast distance, and cells explored. Click a route waypoint to show local wave height, period, and direction."),
        ("7", "Close with the trade-off", "A* may add distance when that reduces peak waves. The correct route depends on vessel, weather scenario, and the chosen operational objective."),
    ]
    story.append(table([["Step", "Action", "What to say / show"]] + steps, [13 * mm, 43 * mm, 118 * mm]))
    story.append(p("Visual key", "H2N"))
    story.append(table([
        ["Visual", "Meaning"],
        ["Blue line", "Dijkstra: traditional shortest safe-distance route."],
        ["Red line", "Weather-aware A*: proposed route, with animated direction marker."],
        ["Wave overlay", "Color-coded significant wave height across the region."],
        ["Waypoint marker", "Click to inspect wave height, wave period, and direction."],
    ], [45 * mm, 129 * mm]))

    story.append(PageBreak())
    story.append(p("5. How to explain the algorithms", "H1N"))
    story.append(p("Dijkstra explores the 8-connected navigable grid and adds only the geographic distance of each move. It is the control route: safe according to the bathymetry/coast mask, but indifferent to weather."))
    story.append(p("A* uses the same safe grid, but adds a weather multiplier to each move and uses a distance heuristic to focus the search. With the ML model enabled, the multiplier is based on service speed divided by predicted attainable speed. A head sea, larger waves, shorter period, or a more wave-sensitive vessel increases the effective cost."))
    story.append(p("The implementation reports estimated time using the route distance and the configured service speed. The weather-aware search cost is what changes the path; the result cards additionally report the actual wave statistics sampled along each route.", "Callout"))
    story.append(p("6. Results already produced by the project", "H1N"))
    story.append(p("The included evaluation.csv compares traditional and proposed routes in rough-weather evaluation runs. These values are useful as a prepared backup when a live run is slow or unavailable."))
    story.append(table([
        ["Voyage", "Distance km\nD / A*", "Peak wave m\nD / A*", "Cells explored\nD / A*"],
        ["Mumbai -> Chennai", "2953.6 / 2954.9", "3.17 / 3.17", "249,000 / 55,321"],
        ["Kandla -> Cochin", "1780.2 / 1780.3", "3.38 / 3.38", "97,263 / 12,497"],
        ["Cochin -> Dubai", "2771.2 / 3068.9", "4.13 / 3.31", "313,745 / 83,978"],
        ["Visakhapatnam -> Colombo", "1697.0 / 1701.4", "2.44 / 2.44", "86,879 / 26,616"],
        ["Chennai -> Port Blair", "1612.2 / 1621.7", "3.00 / 3.03", "100,360 / 40,811"],
    ], [70 * mm, 36 * mm, 36 * mm, 32 * mm]))
    story.append(p("Best interpretation of the Cochin-Dubai row", "H2N"))
    story.append(bullet("A* adds 297.7 km, but reduces peak wave height by 0.82 m."))
    story.append(bullet("The proposed search explores about 73% fewer cells than Dijkstra in this evaluation."))
    story.append(bullet("This is a decision-support demonstration, not a live navigation certification."))

    story.append(p("7. Viva questions and concise answers", "H1N"))
    qa = [
        ["Question", "Answer"],
        ["Why use bathymetry?", "To prevent the route from crossing shallow water that may be unsafe for the vessel draft."],
        ["Why compare Dijkstra and A*?", "Dijkstra provides a transparent traditional baseline; A* shows the proposed weather-aware optimization."],
        ["What does the ML model predict?", "Attainable vessel speed in a given wave state, considering wave height, relative direction, period, service speed, and wave sensitivity."],
        ["Is the training data real AIS data?", "No. The current model learns from a physics-inspired synthetic dataset because per-ship speed-loss logs are not public in this project."],
        ["Why can A* be longer?", "It minimizes weather-adjusted travel cost, so avoiding rough water can justify extra distance."],
        ["What is live weather?", "An optional weather scenario fetched through the live-weather module; typical and rough scenarios are available offline."],
        ["What are the limitations?", "The region and grid resolution are fixed by configuration, weather is scenario-based, and the model should be retrained with real AIS data for production use."],
    ]
    story.append(table(qa, [51 * mm, 123 * mm]))

    story.append(p("8. Troubleshooting during the demo", "H1N"))
    story.append(bullet("Blank Flask map: check GOOGLE_MAPS_API_KEY, API restrictions, billing, and the localhost origin restriction."))
    story.append(bullet("Grid/model load error: run python run_all.py or the preprocessing and ML commands above."))
    story.append(bullet("Live weather error: switch back to Typical or Rough; the offline scenarios do not depend on an external weather request."))
    story.append(bullet("No route found: choose different ports or confirm that the selected endpoints snap to navigable cells."))
    story.append(Spacer(1, 6))
    story.append(p("One-sentence closing", "H2N"))
    story.append(p("Nautilus demonstrates how geospatial safety constraints, numerical pathfinding, marine weather, and vessel-specific machine learning can be combined into an explainable route recommendation.", "Callout"))
    return story


if __name__ == "__main__":
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    DemoDoc(str(OUTPUT)).build(build_story())
    print(f"Created {OUTPUT}")