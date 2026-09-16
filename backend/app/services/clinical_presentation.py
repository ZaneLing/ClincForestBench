from __future__ import annotations

from typing import Any

from backend.app.domain.temporal import CanonicalTemporalEvent


_EMPTY_MARKERS = {"", "none", "null", "nan", "unknown", "not available", "n/a"}
_WORKFLOW_MARKERS = {
    "performed",
    "performed - structured",
    "scored",
    "completed",
    "obtained",
}

_FIELD_LABELS = {
    "age": "年龄",
    "sex": "性别",
    "gender": "性别",
    "ethnicity": "族裔",
    "race": "种族",
    "chief_complaint": "主诉",
    "presentation": "就诊经过",
    "presentation_hpi": "现病史",
    "article_title": "病例来源",
    "admission_source": "入院来源",
    "arrival_transport": "到院方式",
    "means_of_arrival": "到院方式",
    "icu_unit": "收治单元",
    "unit_stay_type": "ICU 入住类型",
    "triage_acuity": "分诊等级",
    "time_semantics": "时间说明",
    "heart_rate": "心率",
    "respiratory_rate": "呼吸频率",
    "spo2": "血氧饱和度",
    "temperature": "体温",
    "temperature_c": "体温",
    "temperature_f": "体温",
    "sbp": "收缩压",
    "dbp": "舒张压",
    "pain": "疼痛评分",
}

_UNITS = {
    "heart_rate": "次/分",
    "respiratory_rate": "次/分",
    "spo2": "%",
    "temperature": "°C",
    "temperature_c": "°C",
    "temperature_f": "°F",
    "sbp": "mmHg",
    "dbp": "mmHg",
}

_CONTEXT_FIELDS = {
    "admission_source",
    "arrival_transport",
    "means_of_arrival",
    "icu_unit",
    "unit_stay_type",
    "triage_acuity",
    "time_semantics",
}

_CLINICAL_LABELS = {
    "Delta": "体重变化",
    "ionized calcium": "离子钙",
    "lactate": "乳酸",
    "triglycerides": "甘油三酯",
}


def is_meaningful_event(event: CanonicalTemporalEvent) -> bool:
    """Reject source workflow markers that do not carry a clinical finding."""
    display = _text(event.clinical_concept.display).casefold()
    value = _text(event.result.get("value")).casefold()
    path = _text(event.result.get("path")).casefold()
    if display in _WORKFLOW_MARKERS or value in _WORKFLOW_MARKERS:
        return False
    if "obtain options" in path:
        return False
    if event.clinical_concept.modality in {"HISTORY", "EXAM"}:
        return bool(display and display not in _EMPTY_MARKERS)
    return True


def initial_state_presentation(
    initial_state: dict[str, Any], dataset_name: str
) -> dict[str, Any]:
    age = _format_age(initial_state.get("age"))
    sex = _format_sex(initial_state.get("sex") or initial_state.get("gender"))
    chief = _text(
        initial_state.get("chief_complaint")
        or initial_state.get("presentation")
    )
    subject = "一名患者"
    if age and sex:
        subject = f"一名{age}{sex}患者"
    elif age:
        subject = f"一名{age}患者"
    elif sex:
        subject = f"一名{sex}患者"
    if chief:
        headline = f"{subject}因{_sentence_fragment(chief)}就诊。"
    else:
        route_key = next(
            (
                key
                for key in ("admission_source", "means_of_arrival", "arrival_transport")
                if _has_value(initial_state.get(key))
            ),
            "",
        )
        route = _context_value(
            route_key,
            initial_state.get("admission_source")
            or initial_state.get("means_of_arrival")
            or initial_state.get("arrival_transport")
        )
        unit = _context_value("icu_unit", initial_state.get("icu_unit"))
        destination = f"收入{unit}" if unit else "进入本次诊疗"
        headline = f"{subject}{f'经{route}' if route else ''}{destination}。"

    narrative_rows = []
    for key in ("chief_complaint", "presentation", "presentation_hpi", "article_title"):
        value = initial_state.get(key)
        if _has_value(value):
            narrative_rows.append(
                {"label": _FIELD_LABELS[key], "value": _format_value(value)}
            )

    demographic_rows = []
    for key in ("age", "sex", "gender", "ethnicity", "race"):
        value = initial_state.get(key)
        if not _has_value(value) or (key == "gender" and _has_value(initial_state.get("sex"))):
            continue
        formatted = age if key == "age" else sex if key in {"sex", "gender"} else _format_value(value)
        demographic_rows.append({"label": _FIELD_LABELS[key], "value": formatted})

    context_rows = []
    for key in _CONTEXT_FIELDS:
        value = initial_state.get(key)
        if _has_value(value):
            context_rows.append(
                {"label": _FIELD_LABELS[key], "value": _context_value(key, value)}
            )

    vital_rows = []
    for container_key in ("triage_vitals", "first_15_min_vitals"):
        container = initial_state.get(container_key)
        if not isinstance(container, dict):
            continue
        for key, value in container.items():
            if isinstance(value, dict):
                observed = [
                    f"{_FIELD_LABELS.get(metric, metric)} {_format_value(item)}"
                    for metric, item in value.items()
                    if _has_value(item)
                ]
                if not observed:
                    continue
                rendered = "；".join(observed)
            elif _has_value(value):
                rendered = _format_value(value)
            else:
                continue
            vital_rows.append(
                {
                    "label": _FIELD_LABELS.get(key, _humanize_key(key)),
                    "value": rendered,
                    "unit": _UNITS.get(key),
                }
            )

    known_keys = {
        "chief_complaint",
        "presentation",
        "presentation_hpi",
        "article_title",
        "age",
        "sex",
        "gender",
        "ethnicity",
        "race",
        "triage_vitals",
        "first_15_min_vitals",
        *_CONTEXT_FIELDS,
    }
    other_rows = [
        {"label": _humanize_key(key), "value": _format_value(value)}
        for key, value in initial_state.items()
        if key not in known_keys and _has_value(value)
    ]
    sections = []
    for title, rows in (
        ("本次就诊", narrative_rows),
        ("患者概况", demographic_rows),
        ("入院信息", context_rows),
        ("初始生命体征", vital_rows),
        ("其他已知信息", other_rows),
    ):
        if rows:
            sections.append({"title": title, "kind": "ROWS", "rows": rows})
    if not vital_rows and "first_15_min_vitals" in initial_state:
        sections.append(
            {
                "title": "初始生命体征",
                "kind": "NARRATIVE",
                "text": "入院后最初 15 分钟内没有可用的连续生命体征记录。",
            }
        )
    return {
        "title": "初始病情",
        "headline": headline,
        "dataset": dataset_name,
        "sections": sections,
    }


def event_presentation(event: CanonicalTemporalEvent) -> dict[str, Any]:
    result = event.result
    blocks: list[dict[str, Any]] = []
    patient_answer = result.get("patient_answer")
    if _has_value(patient_answer):
        blocks.append(
            {
                "title": "患者回答",
                "kind": "NARRATIVE",
                "text": _format_value(patient_answer),
            }
        )
    components = result.get("components")
    if isinstance(components, list):
        rows = []
        abnormal_count = 0
        for component in components:
            if not isinstance(component, dict):
                continue
            label = _text(component.get("label") or component.get("name")) or "检验项目"
            value = component.get("text")
            if not _has_value(value):
                value = component.get("value")
            if not _has_value(value):
                value = component.get("number_value")
            flag = _text(component.get("flag"))
            if flag and flag.casefold() not in {"normal", "n", "none"}:
                abnormal_count += 1
            rows.append(
                {
                    "label": label,
                    "value": _format_value(value) if _has_value(value) else "未报告",
                    "unit": _text(component.get("unit")) or None,
                    "flag": _format_flag(flag),
                }
            )
        if rows:
            blocks.append({"title": "检验结果", "kind": "ROWS", "rows": rows})
            summary = f"本次共返回 {len(rows)} 项结果"
            if abnormal_count:
                summary += f"，其中 {abnormal_count} 项标记异常"
            summary += "。"
        else:
            summary = "本次记录未包含可展示的分项结果。"
    else:
        summary = "结果已返回。"

    narrative_keys = (
        ("impression", "影像学印象"),
        ("findings", "影像所见"),
        ("report", "检查报告"),
        ("narrative_text", "临床记录"),
        ("text", "结果描述"),
    )
    for key, label in narrative_keys:
        value = result.get(key)
        if _has_value(value):
            blocks.append(
                {"title": label, "kind": "NARRATIVE", "text": _format_value(value)}
            )

    if not blocks and (_has_value(result.get("finding")) or _has_value(result.get("value"))):
        finding_row = {
            "label": _format_value(
                result.get("finding")
                or _path_leaf(result.get("path"))
                or event.clinical_concept.display
            ),
            "value": _format_value(result.get("value") or "已记录"),
        }
        unit = _text(result.get("unit"))
        if unit:
            finding_row["unit"] = unit
        blocks.append(
            {
                "title": "临床发现",
                "kind": "ROWS",
                "rows": [finding_row],
            }
        )

    ignored = {
        "components",
        "impression",
        "findings",
        "report",
        "narrative_text",
        "text",
        "finding",
        "value",
        "path",
        "source_path",
        "source_value",
        "unit",
        "source_sentence_index",
        "time_is_sequence_proxy",
        "specimen_id",
        "panel_abnormal",
        "patient_answer",
        "media_asset",
        "media_type",
        "caption",
    }
    generic_rows = [
        {"label": _humanize_key(key), "value": _format_value(value)}
        for key, value in result.items()
        if key not in ignored and _has_value(value)
    ]
    if generic_rows:
        blocks.append({"title": "补充结果", "kind": "ROWS", "rows": generic_rows})
    if not blocks:
        blocks.append(
            {
                "title": "结果说明",
                "kind": "NARRATIVE",
                "text": "源病例仅记录了该项目完成，未提供具有临床解释价值的结果；该条目不应进入医生可选动作。",
            }
        )
    media = []
    if _has_value(result.get("media_asset")):
        media.append(
            {
                "asset": _text(result.get("media_asset")),
                "media_type": _text(result.get("media_type")) or "image/jpeg",
                "caption": _text(result.get("caption")) or "源病例影像",
            }
        )
    return {
        "title": _clinical_label(event.clinical_concept.display),
        "summary": summary,
        "modality_label": modality_label(event.clinical_concept.modality),
        "blocks": blocks,
        "media": media,
    }


def action_presentation(event: CanonicalTemporalEvent) -> dict[str, str]:
    modality = event.clinical_concept.modality
    label = _strip_action_prefix(event.clinical_concept.display)
    if modality == "HISTORY":
        display = f"问询病史：{label}"
        interaction = "QUESTION"
    elif modality == "EXAM":
        display = f"进行查体：{label}"
        interaction = "EXAM"
    elif modality == "LAB":
        display = f"开具检验：{label}"
        interaction = "ORDER"
    elif modality == "IMAGING":
        display = f"申请影像：{label}"
        interaction = "ORDER"
    elif modality == "ECG":
        display = f"开具检查：{label}"
        interaction = "ORDER"
    elif modality == "VITALS":
        if any(
            token in label
            for token in (
                "体重",
                "入量",
                "出量",
                "净平衡",
                "透析",
                "呼气末正压",
                "吸入氧浓度",
                "呼吸机",
            )
        ):
            display = f"调阅床旁监测：{label}"
            interaction = "REVIEW"
        else:
            display = f"复测生命体征：{label}"
            interaction = "EXAM"
    else:
        display = f"调阅临床记录：{label}"
        interaction = "REVIEW"
    return {
        "display": display,
        "modality": modality,
        "modality_label": modality_label(modality),
        "interaction_type": interaction,
        "interaction_label": {
            "QUESTION": "问询",
            "EXAM": "查体",
            "ORDER": "检查",
            "REVIEW": "调阅",
        }[interaction],
    }


def modality_label(modality: str) -> str:
    return {
        "LAB": "实验室检验",
        "IMAGING": "影像检查",
        "ECG": "心电检查",
        "HISTORY": "病史问询",
        "EXAM": "体格检查",
        "VITALS": "生命体征",
        "INTERVENTION": "治疗干预",
    }.get(modality, "临床资料")


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().casefold() not in _EMPTY_MARKERS
    if isinstance(value, dict):
        return any(_has_value(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_has_value(item) for item in value)
    return True


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _format_sex(value: Any) -> str:
    text = _text(value)
    return {"m": "男性", "male": "男性", "f": "女性", "female": "女性"}.get(
        text.casefold(), text
    )


def _format_age(value: Any) -> str:
    if not _has_value(value):
        return ""
    if isinstance(value, list):
        first = value[0] if value else None
        if isinstance(first, list) and first:
            return f"{_format_value(first[0])}岁"
    text = _format_value(value)
    return text if any(unit in text for unit in ("岁", "月", "天")) else f"{text}岁"


def _format_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, float):
        return f"{value:g}"
    if isinstance(value, list):
        return "；".join(_format_value(item) for item in value if _has_value(item))
    if isinstance(value, dict):
        return "；".join(
            f"{_humanize_key(key)} {_format_value(item)}"
            for key, item in value.items()
            if _has_value(item)
        )
    return str(value).strip()


def _format_flag(value: str) -> str | None:
    if not value or value.casefold() in {"none", "null"}:
        return None
    return {"normal": "正常", "abnormal": "异常", "high": "偏高", "low": "偏低"}.get(
        value.casefold(), value
    )


def _context_value(key: str, value: Any) -> str:
    text = _format_value(value)
    translations = {
        "emergency department": "急诊",
        "med-surg icu": "内外科重症监护病房",
        "admit": "首次入住",
        "readmit": "再次入住",
        "self": "自行到院",
        "ambulance": "救护车送达",
    }
    return translations.get(text.casefold(), text)


def _humanize_key(value: str) -> str:
    return _FIELD_LABELS.get(value, value.replace("_", " ").strip().capitalize())


def _path_leaf(value: Any) -> str:
    parts = [item.strip() for item in _text(value).split("/") if item.strip()]
    return parts[-1] if parts else ""


def _strip_action_prefix(value: str) -> str:
    text = _text(value)
    if "·" in text and text.casefold().startswith("review "):
        text = text.split("·", 1)[1].strip()
    return _clinical_label(text)


def _clinical_label(value: str) -> str:
    text = _text(value)
    return _CLINICAL_LABELS.get(text, text)


def _sentence_fragment(value: str) -> str:
    return value.strip().rstrip("。.!；; ")
