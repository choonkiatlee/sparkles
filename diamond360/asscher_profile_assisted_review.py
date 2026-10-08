"""#91 assisted, target-blind profile annotation *worksheet*.

Image-only visual proposals are never human-verified physical geometry. The
worksheet lets a reviewer assess exterior/table/girdle/optical uncertainty and
optionally trace contour pixels. It cannot output facet angles or authorize
semantic facet IDs; those need a later independent geometric adjudication.
"""
from __future__ import annotations

import argparse
import base64
from copy import deepcopy
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import asscher_profile_feasibility as feasibility

SCHEMA = "diamond360-asscher-profile-assisted-review/2"
# Broad regions identified from the source photograph itself. Their names
# describe a question, not a certified feature or automatic facet boundary.
# All coordinates refer to the archived 410 x 319 source pixel grid.
REGIONS = (
    ("A", "upper pointed pavilion tip", "pavilion_culet_point_region", (145, 49, 264, 105),
     "Is the projected pointed pavilion/culet-region tip visible? It need not be a polished culet facet."),
    ("B", "left upper exterior", "silhouette_region", (43, 87, 168, 214),
     "Which visible boundary, if any, separates the LEFT exterior from background?"),
    ("C", "right upper exterior", "silhouette_region", (242, 86, 374, 214),
     "Which visible boundary, if any, separates the RIGHT exterior from background?"),
    ("D", "left widest profile", "possible_girdle_region", (35, 181, 108, 243),
     "Is an exterior girdle junction actually identifiable at the LEFT widest region?"),
    ("E", "right widest profile", "possible_girdle_region", (301, 181, 380, 243),
     "Is an exterior girdle junction actually identifiable at the RIGHT widest region?"),
    ("F", "lower crown / table vicinity", "lower_crown_table_region", (93, 225, 316, 307),
     "Is the LOWER crown and broad table-region outline recoverable despite platform shadow?"),
    ("G", "central optical bands", "interior_appearance_control", (115, 112, 295, 200),
     "Do these conspicuous straight bands look like REFLECTED/virtual features, or is physical correspondence genuinely established?"),
)
VERDICTS = (
    "unreviewed",
    "likely_external_contour",
    "possible_table_edge",
    "possible_girdle_edge",
    "optical_appearance_only",
    "ambiguous",
    "not_visible",
)
# The worksheet does not accept physically-verified or named facet categories.
PHYSICAL_REVIEW = {
    "likely_external_contour",
    "possible_table_edge",
    "possible_girdle_edge",
}


def _source(image_path):
    image_path = Path(image_path)
    with Image.open(image_path) as image:
        rgb = image.convert("RGB").copy()
    digest = feasibility._hash_file(image_path)
    if digest != feasibility.ORIGINAL_PROFILE_SHA256 or rgb.size != feasibility.ORIGINAL_PROFILE_SIZE:
        raise ValueError("assisted review is pinned to the exact archived original source")
    return digest, rgb


def make_worksheet(image_path):
    sha, source = _source(image_path)
    w, h = source.size
    regions = [{
        "region_id": key,
        "display_label": label,
        "hypothesis": kind,
        "roi_xyxy_px": list(roi),
        "review_question": question,
        "review_status": "unreviewed",
        "proposed_by": "assistant_visual_image_only",
        "reviewer_verdict": "unreviewed",
        "reviewer_note": "",
        "reviewer_trace_xy_px": [],
        "reviewer_claim_is_physical_truth": False,
        "independently_verified_physical_junction": False,
        "semantic_facet_id": None,
    } for key, label, kind, roi, question in REGIONS]
    return {
        "schema_version": SCHEMA,
        "source_orientation": "pointed_upper_pavilion_broad_lower_crown",
        "source": {
            "sha256": sha, "width_px": w, "height_px": h,
            "original_verified": True,
        },
        "region_proposals": regions,
        "target_blinding": "no_external_values_or_expert_angle_inputs",
        "comparison_targets_loaded": False,
        "status": "awaiting_image_only_review",
        "physical_facet_junctions_verified": 0,
        "physical_facet_angles_measured": 0,
        "semantic_measurements": {
            side: {
                facet: {
                    "status": "unavailable", "apparent_angle_deg": None,
                    "physical_angle_deg": None,
                    "reason": "no_verified_projected_physical_facet_correspondence",
                }
                for facet in feasibility.SLOTS
            } for side in feasibility.SIDES
        },
        "interpretation": (
            "ROI proposals and user traces are image-only hypotheses. "
            "A reviewer verdict does not establish a physical polished facet "
            "or camera geometry; every P1/P2/P3/C1 angle remains unavailable."
        ),
    }


def validate_worksheet(data):
    if data.get("schema_version") != SCHEMA:
        raise ValueError("wrong assisted review schema")
    if data.get("source_orientation") != "pointed_upper_pavilion_broad_lower_crown":
        raise ValueError("inverted source orientation")
    source = data.get("source", {})
    if source.get("sha256") != feasibility.ORIGINAL_PROFILE_SHA256 or (
        source.get("width_px"), source.get("height_px")
    ) != feasibility.ORIGINAL_PROFILE_SIZE:
        raise ValueError("wrong image, source SHA or dimensions")
    if data.get("comparison_targets_loaded") is not False:
        raise ValueError("external angle target leakage")
    if data.get("physical_facet_junctions_verified") != 0 or data.get("physical_facet_angles_measured") != 0:
        raise ValueError("assisted trace cannot certify physical geometry")
    regions = data.get("region_proposals")
    if not isinstance(regions, list) or len(regions) != len(REGIONS):
        raise ValueError("all fixed ROI prompts must be retained")
    for row, (key, name, kind, coords, question) in zip(regions, REGIONS):
        if (
            row.get("region_id") != key or row.get("hypothesis") != kind
            or row.get("roi_xyxy_px") != list(coords)
            or row.get("review_question") != question
            or row.get("display_label") != name
            or row.get("proposed_by") != "assistant_visual_image_only"
        ):
            raise ValueError("ROI identity or proposal was modified")
        if row.get("semantic_facet_id") is not None or row.get("independently_verified_physical_junction") is not False:
            raise ValueError("cannot promote unverified ROI to physical facet")
        if row.get("reviewer_claim_is_physical_truth") is not False:
            raise ValueError("image-only review cannot claim physical truth")
        verdict = row.get("reviewer_verdict")
        if verdict not in VERDICTS:
            raise ValueError("unknown reviewer verdict")
        if kind == "pavilion_culet_point_region" and verdict in {"possible_table_edge", "possible_girdle_edge"}:
            raise ValueError("pointed upper pavilion tip cannot be a table or girdle proposal")
        if kind == "interior_appearance_control" and verdict in PHYSICAL_REVIEW:
            raise ValueError("internal optical band cannot be certified as exterior contour")
        trace = row.get("reviewer_trace_xy_px")
        if not isinstance(trace, list) or len(trace) > 40 or len(trace) == 1:
            raise ValueError("reviewer trace must be empty or 2-40 source points")
        for point in trace:
            if (not isinstance(point, list) or len(point) != 2
                or any(not isinstance(v, (int, float)) or isinstance(v, bool) for v in point)
                or not all(0 <= v < bound for v, bound in zip(point, feasibility.ORIGINAL_PROFILE_SIZE))):
                raise ValueError("trace outside source-image coordinates")
            x0, y0, x1, y1 = coords
            if not x0 <= point[0] <= x1 or not y0 <= point[1] <= y1:
                raise ValueError("trace outside stated review ROI")
        if trace and verdict not in PHYSICAL_REVIEW:
            raise ValueError("traced candidate requires a relevant tentative reviewer verdict")
        note = row.get("reviewer_note")
        if not isinstance(note, str) or len(note) > 1500:
            raise ValueError("reviewer notes must be short text")
        if verdict != "unreviewed" and not note.strip():
            raise ValueError("every reviewer decision needs a short reason")
        if row.get("review_status") not in ("unreviewed", "reviewer_assessed"):
            raise ValueError("invalid review status")
        if (row.get("review_status") == "reviewer_assessed") != (verdict != "unreviewed"):
            raise ValueError("review status and verdict must agree")
    groups = data.get("semantic_measurements", {})
    if set(groups) != set(feasibility.SIDES):
        raise ValueError("missing side")
    for side in groups.values():
        if set(side) != set(feasibility.SLOTS):
            raise ValueError("missing physical facet slot")
        for record in side.values():
            if record.get("status") != "unavailable" or record.get("apparent_angle_deg") is not None or record.get("physical_angle_deg") is not None:
                raise ValueError("annotation cannot produce facet angles")
    return True


def apply_review(worksheet, review):
    """Require explicit reviewer decisions; never rewrite physical evidence."""
    result = deepcopy(worksheet)
    if review.get("schema_version") != "diamond360-asscher-profile-human-review/1":
        raise ValueError("invalid image-only reviewer submission")
    if review.get("source_sha256") != feasibility.ORIGINAL_PROFILE_SHA256:
        raise ValueError("review submitted against wrong image")
    entries = review.get("decisions", [])
    if not isinstance(entries, list) or len(entries) > len(REGIONS):
        raise ValueError("invalid decisions")
    by_id = {row["region_id"]: row for row in result["region_proposals"]}
    seen = set()
    for record in entries:
        rid = record.get("region_id")
        if rid not in by_id or rid in seen:
            raise ValueError("unknown or duplicate review region")
        seen.add(rid)
        row = by_id[rid]
        row["reviewer_verdict"] = record.get("verdict")
        row["reviewer_note"] = record.get("note", "")
        row["reviewer_trace_xy_px"] = record.get("trace_xy_px", [])
        row["review_status"] = "reviewer_assessed"
    result["status"] = (
        "image_only_review_recorded_no_physical_facet_certification"
        if seen else "awaiting_image_only_review"
    )
    validate_worksheet(result)
    return result


def draw_overview(worksheet, image):
    out = image.copy()
    draw = ImageDraw.Draw(out)
    color_map = {
        "silhouette_region": (38, 180, 70),
        "pavilion_culet_point_region": (39, 128, 224),
        "possible_girdle_region": (242, 150, 35),
        "lower_crown_table_region": (187, 83, 207),
        "interior_appearance_control": (206, 58, 70),
    }
    for item in worksheet["region_proposals"]:
        color = color_map[item["hypothesis"]]
        x0, y0, x1, y1 = item["roi_xyxy_px"]
        draw.rectangle((x0, y0, x1, y1), outline=color, width=2)
        anchor = (x0 + 2, y0 + 1)
        draw.rectangle((anchor[0], anchor[1], anchor[0] + 15, anchor[1] + 15), fill=color)
        draw.text((anchor[0] + 4, anchor[1]), item["region_id"], fill=(255, 255, 255))
        points = item["reviewer_trace_xy_px"]
        if len(points) > 1:
            draw.line([tuple(p) for p in points], fill=(255, 230, 45), width=2)
    return out


def render_html(worksheet, image):
    """Standalone offline touch-friendly image-coordinate annotation UI."""
    from io import BytesIO
    buf = BytesIO()
    image.save(buf, format="PNG")
    embedded = base64.b64encode(buf.getvalue()).decode("ascii")
    data = json.dumps(worksheet).replace("<", "\\u003c").replace("&", "\\u0026")
    return r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Asscher profile — image-only review</title>
<style>body{font:15px system-ui,sans-serif;background:#f4f5f8;color:#18202a;margin:18px auto;max-width:900px;padding:0 12px}
main{display:grid;grid-template-columns:minmax(310px,430px) 1fr;gap:16px}
@media(max-width:720px){main{display:block}}
.panel{background:white;border:1px solid #cad2da;border-radius:10px;padding:12px;margin-bottom:12px}
canvas{width:100%;height:auto;border:1px solid #adb8c1;touch-action:none}
select,button,textarea{font:inherit;padding:8px;max-width:100%} textarea{width:95%;min-height:65px}
button{margin:4px;border-radius:6px;border:1px solid #8f9fac;background:white}
button.primary{background:#155cb1;color:white}.hint{color:#526070;font-size:13px}
#status{font-weight:600}label{display:block;margin-top:9px}</style></head><body>
<h2>DiaGem profile — physical vs optical review</h2>
<p><strong>Image-only hypotheses.</strong> Inspect the original photograph. No label or trace certifies a physical facet; do not use Sergey's target numbers.</p>
<main><div class="panel"><canvas id="canvas" width="410" height="319"></canvas>
<p class="hint">Tap points on an exterior boundary to trace it. Trace points must stay inside the selected box. Choose a tentative verdict and explain why.</p>
<button id="undo">Undo point</button><button id="clear">Clear trace</button></div>
<div class="panel"><label>Region <select id="region"></select></label>
<p id="question"></p><label>Interpretation <select id="verdict"></select></label>
<label>What do you actually see?<textarea id="note" placeholder="Reason; note shadows, glare or ambiguity."></textarea></label>
<button id="save">Record this region</button><p id="status"></p>
<button class="primary" id="export">Export human review JSON</button>
<p class="hint">Send the exported JSON back for validation. All facet-angle slots remain unavailable.</p></div></main>
<script>
const doc=__DOC__;
const image = new Image(); image.src="data:image/png;base64,__IMAGE__";
const c=document.getElementById('canvas'),ctx=c.getContext('2d');
const region=document.getElementById('region'), verdict=document.getElementById('verdict'),
note=document.getElementById('note'),status=document.getElementById('status');
const classes=['unreviewed','likely_external_contour','possible_table_edge','possible_girdle_edge','optical_appearance_only','ambiguous','not_visible'];
for(const r of doc.region_proposals){const o=document.createElement('option');o.value=r.region_id;o.textContent=r.region_id+' — '+r.display_label;region.appendChild(o)}
let decisions={};let selected='A',points=[];
function draw(){
ctx.drawImage(image,0,0,410,319);
for(const r of doc.region_proposals){
const [x0,y0,x1,y1]=r.roi_xyxy_px;
ctx.strokeStyle=r.region_id===selected?'#ffdf2f':'#1683be';ctx.lineWidth=r.region_id===selected?3:1;
ctx.strokeRect(x0,y0,x1-x0,y1-y0);ctx.fillStyle='#153d78';ctx.fillRect(x0,y0,16,16);
ctx.fillStyle='white';ctx.font='13px sans-serif';ctx.fillText(r.region_id,x0+3,y0+13)}
if(points.length){ctx.strokeStyle='#f5e330';ctx.lineWidth=3;ctx.beginPath();points.forEach(([x,y],i)=>i?ctx.lineTo(x,y):ctx.moveTo(x,y));ctx.stroke();}
}
function change(){
selected=region.value;const r=doc.region_proposals.find(x=>x.region_id===selected);
document.getElementById('question').textContent=r.review_question;
verdict.replaceChildren();
for(const label of classes.filter(x=>(r.hypothesis!=='interior_appearance_control' || !['likely_external_contour','possible_table_edge','possible_girdle_edge'].includes(x)) && (r.hypothesis!=='pavilion_culet_point_region' || !['possible_table_edge','possible_girdle_edge'].includes(x)))){
const o=document.createElement('option');o.value=label;o.textContent=label.replaceAll('_',' ');verdict.appendChild(o);}
const d=decisions[selected];verdict.value=d?.verdict||'unreviewed';note.value=d?.note||'';
points=(d?.trace_xy_px||[]).map(x=>x.slice());status.textContent='Image-only proposal, not a verified facet.';draw();
}
c.addEventListener('pointerdown',e=>{
const b=c.getBoundingClientRect(),x=Math.round((e.clientX-b.left)*410/b.width),
y=Math.round((e.clientY-b.top)*319/b.height);
const r=doc.region_proposals.find(t=>t.region_id===selected),[x0,y0,x1,y1]=r.roi_xyxy_px;
if(x<x0||x>x1||y<y0||y>y1){status.textContent='Tap inside selected region only';return;}
if(points.length>=40){status.textContent='Maximum 40 points';return;}
points.push([x,y]);draw();});
document.getElementById('undo').onclick=()=>{points.pop();draw()};
document.getElementById('clear').onclick=()=>{points=[];draw()};
document.getElementById('save').onclick=()=>{
const v=verdict.value,n=note.value.trim();
if(v==='unreviewed'||!n){status.textContent='Choose a verdict and add a reason';return}
if(points.length===1){status.textContent='Use 0 or at least 2 trace points';return}
if(points.length && !['likely_external_contour','possible_table_edge','possible_girdle_edge'].includes(v)){status.textContent='Only tentative contour/edge decisions can have a trace';return}
decisions[selected]={region_id:selected,verdict:v,note:n,trace_xy_px:points.map(p=>p.slice())};
status.textContent='Recorded '+selected;draw();
};
document.getElementById('export').onclick=()=>{
const review={schema_version:'diamond360-asscher-profile-human-review/1',
source_sha256:doc.source.sha256,decisions:Object.values(decisions)};
const blob=new Blob([JSON.stringify(review,null,2)],{type:'application/json'});
const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='profile-human-review.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),2000);
};image.onload=draw;region.onchange=change;change();
</script></body></html>""".replace("__DOC__", data).replace("__IMAGE__", embedded)


def write_worksheet(image_path, output):
    worksheet = make_worksheet(image_path)
    validate_worksheet(worksheet)
    _, image = _source(image_path)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "assisted-worksheet.json").write_text(
        json.dumps(worksheet, sort_keys=True, indent=2) + "\n"
    )
    draw_overview(worksheet, image).save(output / "assisted-review-regions.png")
    (output / "assisted-review.html").write_text(render_html(worksheet, image))
    return worksheet


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--review", type=Path, help="Optional exported reviewer JSON to validate")
    args = parser.parse_args()
    result = write_worksheet(args.image, args.output)
    if args.review:
        user = json.loads(args.review.read_text())
        validated = apply_review(result, user)
        (args.output / "reviewed-annotations.json").write_text(
            json.dumps(validated, sort_keys=True, indent=2) + "\n"
        )
        print("Validated image-only annotations; still NO verified physical facets")
    print(json.dumps({"source_sha256": result["source"]["sha256"],
                      "region_count": len(result["region_proposals"]),
                      "physical_facet_angles_measured": 0}, sort_keys=True))


if __name__ == "__main__":
    main()
