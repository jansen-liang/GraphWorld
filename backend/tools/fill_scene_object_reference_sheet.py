"""Fill the scene/object dataset survey sheet in the reference workbook."""

from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
WORKBOOK = ROOT / "docs/related_works/reference_table_graphworld_related_work.xlsx"
TMP = WORKBOOK.with_suffix(".tmp.xlsx")
NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
ET.register_namespace("", NS)

# These styles already exist in the workbook.  The original cells in the
# target sheet were created without an explicit style, so long values did not
# wrap even though the workbook's other survey sheets do.
HEADER_STYLE = "1"
DATA_STYLE = "6"


ROWS = {
    2: ["2018", "bathroom, bedroom, kitchen, living room (4; local extractor)", "116 labels; furniture, appliances, containers, food, tools (local extractor)", "Room-family metadata only; no multi-room adjacency in extracted source", "https://ai2thor.allenai.org/", "AI2-THOR object metadata / room annotations", "本地已统计：4 类房间、116 个对象标签；可直接作为 Home 房间和物体 ontology 先验。"],
    3: ["2022", "bathroom, bedroom, kitchen, living room (4; local extractor)", "108 labels; furniture, appliances, containers, food, tools (local extractor)", "Placement database has no multi-room house adjacency; topology需由 ProcTHOR house JSON/生成器补充", "https://github.com/allenai/procthor", "ProcTHOR placement annotations and receptacle database", "本地已统计：4 类房间、108 个对象标签、对象 parent/receptacle 关系；当前输出是放置先验，不是房间图。"],
    4: ["2019", "indoor apartments / houses; room taxonomy follows AI2-THOR scenes", "AI2-THOR object taxonomy: furniture, appliances, receptacles, interactable objects", "Multi-room navigation layouts; topology is scene-specific and not represented by the current extractor", "https://ai2thor.allenai.org/robothor/", "RoboTHOR benchmark scenes", "机器人导航和交互环境；适合作为空间可达性和导航场景参考，尚未纳入本地对象统计链路。"],
    5: ["2021", "living room, bedroom, dining room, kitchen, bathroom, study, entrance, balcony, corridor", "Furniture/object instances: bed, sofa, table, chair, cabinet, shelf, lamp, appliance and decorations", "Explicit room layouts with room adjacency and object placement; suitable for room graph extraction", "https://tianchi.aliyun.com/specials/promotion/alibaba-3d-scene-dataset", "3D-FRONT paper and dataset", "大规模室内房间和家具布局数据；适合补充 Home/Office 房间图、对象共现和 parent 放置先验，当前未接入仓库 extractor。"],
    6: ["2020", "Rooms are inherited from synthetic indoor scenes; no single canonical room taxonomy", "Large furniture/object model taxonomy with category and bounding-box metadata", "Scene/layout topology depends on the source synthetic scenes; object-level layout is available", "https://tianchi.aliyun.com/specials/promotion/alibaba-3d-future", "3D-FUTURE model dataset", "主要是物体模型和家具类别库，不应直接当作 GraphWorld 房间图数据；适合补充 ObjectFamily/variant 先验。"],
    7: ["2018", "indoor residential and commercial rooms; taxonomy varies by scene", "RGB-D reconstructed object instances and room surfaces; category coverage is scene-dependent", "Reconstructed indoor layouts with spatial geometry; room adjacency requires scene parsing", "https://interiornet.org/", "InteriorNet dataset", "适合未来 3D 和真实室内几何研究；当前 GraphWorld 暂不接入，不能直接提供统一 ontology 统计。"],
    8: ["2017", "kitchen, living room, bedroom, bathroom, office, hallway, stairs and other Matterport room labels", "40-class semantic benchmark categories including wall, floor, chair, table, sofa, bed, cabinet, door", "Scanned multi-room building topology; connectivity can be extracted from scans", "https://niessner.github.io/Matterport/", "Matterport3D paper and dataset", "真实扫描室内数据，适合房间拓扑和语义对象校验；物体类别偏感知 benchmark，不等同于可交互模板。"],
    9: ["2021", "residential, office, hotel, educational and other indoor spaces; no fixed room list", "Semantic/instance categories available through Habitat scene annotations; coverage varies by scene", "Multi-room scanned environments with navigation connectivity", "https://aihabitat.org/datasets/hm3d/", "Habitat-Matterport 3D (HM3D)", "适合 Habitat 导航和多房间空间先验；需要单独下载/解析标注后才能统计 GraphWorld 对象类别。"],
    10: ["2017", "apartments, offices, conference rooms, kitchens, bedrooms, bathrooms and other scanned rooms", "20-class benchmark object categories: chair, table, sofa, bed, cabinet, desk, door, window, etc.", "Scanned multi-room scenes; connectivity inferred from reconstructed geometry", "http://www.scan-net.org/", "ScanNet paper and benchmark", "适合作为真实室内语义类别和房间拓扑的校验集；其 20 类 benchmark ontology 需要与 GraphWorld ontology 映射。"],
    11: ["2019", "apartments, offices, hotel rooms, kitchens, living rooms and synthetic indoor scenes", "Semantic mesh categories for furniture, appliances, fixtures and structural surfaces", "Complete reconstructed scene layouts with room/area structure", "https://github.com/facebookresearch/Replica-Dataset", "Replica Dataset", "高质量重建场景，适合后续环境系统和空间拓扑验证；当前不作为第一批统计源。"],
    12: ["2020", "living room, bedroom, kitchen, bathroom, dining room, corridor, balcony and other structured rooms", "Walls, floors, doors, windows, furniture and common household objects", "Explicit synthetic floor plans and room adjacency; highly suitable for room graph generation", "https://structured3d-dataset.org/", "Structured3D dataset", "与 GraphWorld 的房间图生成最接近的外部参考之一；可用于校验 RoomTypeSpec、邻接规则和结构对象。"],
}


def text_value(root: ET.Element, shared: list[str], value: str) -> int:
    try:
        return shared.index(value)
    except ValueError:
        shared.append(value)
        return len(shared) - 1


def load_shared(z: ZipFile) -> tuple[ET.Element, list[str]]:
    root = ET.fromstring(z.read("xl/sharedStrings.xml"))
    values = ["".join(t.text or "" for t in item.iter(f"{{{NS}}}t")) for item in root.findall(f"{{{NS}}}si")]
    return root, values


def set_cell(sheet: ET.Element, shared: list[str], ref: str, value: str) -> None:
    cell = sheet.find(f".//{{{NS}}}c[@r='{ref}']")
    if cell is None:
        row_ref = ''.join(ch for ch in ref if ch.isdigit())
        row = sheet.find(f".//{{{NS}}}row[@r='{row_ref}']")
        if row is None:
            raise ValueError(f"missing row for {ref}")
        cell = ET.SubElement(row, f"{{{NS}}}c", {"r": ref})
    cell.attrib["t"] = "s"
    cell.attrib["s"] = DATA_STYLE
    for child in list(cell):
        cell.remove(child)
    ET.SubElement(cell, f"{{{NS}}}v").text = str(text_value(sheet, shared, value))


def main() -> None:
    with ZipFile(WORKBOOK, "r") as source:
        workbook = ET.fromstring(source.read("xl/workbook.xml"))
        rels = ET.fromstring(source.read("xl/_rels/workbook.xml.rels"))
        relmap = {item.attrib["Id"]: item.attrib["Target"] for item in rels}
        target = None
        for sheet in workbook.find(f"{{{NS}}}sheets"):
            if sheet.attrib["name"] == "场景与物体":
                target = "xl/" + relmap[sheet.attrib[f"{{{REL_NS}}}id"]]
                break
        if target is None:
            raise ValueError("scene/object worksheet not found")
        shared_root, shared = load_shared(source)
        scene_sheet = ET.fromstring(source.read(target))
        header_row = scene_sheet.find(f".//{{{NS}}}row[@r='1']")
        if header_row is not None:
            for cell in header_row.findall(f"{{{NS}}}c"):
                cell.attrib["s"] = HEADER_STYLE
        for row_number, values in ROWS.items():
            for column, value in zip("BCDEFGH", values):
                set_cell(scene_sheet, shared, f"{column}{row_number}", value)
            row = scene_sheet.find(f".//{{{NS}}}row[@r='{row_number}']")
            if row is not None:
                # Let spreadsheet applications calculate the final height from
                # the wrapped content when the workbook is opened.
                row.attrib.pop("ht", None)
                row.attrib["customHeight"] = "false"
        shared_root[:] = []
        shared_root.attrib["count"] = str(len(shared))
        shared_root.attrib["uniqueCount"] = str(len(shared))
        for value in shared:
            si = ET.SubElement(shared_root, f"{{{NS}}}si")
            ET.SubElement(si, f"{{{NS}}}t").text = value
        with ZipFile(TMP, "w", ZIP_DEFLATED) as output:
            for item in source.infolist():
                data = ET.tostring(shared_root, encoding="utf-8", xml_declaration=True) if item.filename == "xl/sharedStrings.xml" else ET.tostring(scene_sheet, encoding="utf-8", xml_declaration=True) if item.filename == target else source.read(item.filename)
                output.writestr(item, data)
    TMP.replace(WORKBOOK)
    print(f"updated {WORKBOOK}")


if __name__ == "__main__":
    main()
