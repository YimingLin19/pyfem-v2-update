"""定义 GUI 统一命令注册层。"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QAction, QColor, QIcon, QKeySequence, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QStyle

from pyfem.gui.model_edit_capabilities import collect_export_capability_issues, collect_run_capability_issues, normalize_object_kind
from pyfem.gui.module_toolbox import ToolboxButtonSpec
from pyfem.modeldb import ModelDB, RawKeywordBlockDef

if TYPE_CHECKING:
    from pyfem.gui.main_window import PyFEMMainWindow


CommandHandler = Callable[["PyFEMMainWindow"], None]
CapabilityPredicate = Callable[["PyFEMMainWindow"], "GuiCommandAvailability"]


@dataclass(slots=True, frozen=True)
class GuiCommandAvailability:
    """描述一个命令当前是否可用。"""

    enabled: bool
    unavailable_reason: str | None = None


@dataclass(slots=True, frozen=True)
class GuiCommandDefinition:
    """描述一个统一注册的 GUI 命令。"""

    command_id: str
    display_name: str
    module_name: str
    button_label: str
    tooltip: str
    is_placeholder: bool
    uses_dialog: bool
    icon_key: str
    trigger: CommandHandler
    capability: CapabilityPredicate
    unavailable_reason: str | None = None
    shortcut: str | None = None


MODULE_COMMAND_IDS: dict[str, tuple[str, ...]] = {
    "Part": ("edit_selected", "selection_details", "refresh_geometry", "part_summary", "create_part_placeholder", "import_part_placeholder", "partition_placeholder", "mesh_seed_placeholder"),
    "Property": ("open_material_manager", "open_section_manager", "assign_section", "validate_property_data"),
    "Assembly": ("edit_instance_transform", "selection_details", "save_as_derived_case", "assembly_summary", "duplicate_instance_placeholder", "suppress_resume_instance_placeholder", "create_assembly_set_placeholder", "create_surface_placeholder"),
    "Step": ("open_step_manager", "open_step_output_controls", "open_step_diagnostics_placeholder", "validate_and_run_step_tools"),
    "Interaction": ("interaction_summary", "edit_raw_keyword_block", "unsupported_interaction_info", "create_contact_placeholder", "create_constraint_placeholder", "create_coupling_placeholder", "create_tie_placeholder", "validate_interaction_support"),
    "Load": ("open_load_manager", "open_boundary_manager", "open_amplitude_manager_placeholder", "validate_load_support"),
    "Mesh": ("mesh_summary", "verify_mesh", "refresh_geometry", "element_quality_placeholder", "mesh_statistics", "export_mesh_placeholder", "seed_controls_placeholder", "generate_mesh_placeholder"),
    "Optimization": ("save_as_derived_case", "write_inp", "run_current_model", "parameter_variant_placeholder", "batch_case_placeholder", "design_variable_placeholder", "response_placeholder", "optimization_info"),
    "Job": ("open_job_center", "open_current_job_monitor", "open_job_diagnostics", "open_results_output"),
    "Visualization": ("open_results", "export_vtk", "probe", "legend_settings", "selection_details", "result_field_selector_placeholder", "result_measure_info", "screenshot_export_figure_placeholder"),
}

MODEL_CONTEXT_COMMAND_IDS: dict[str, tuple[str, ...]] = {
    "material": ("edit_material", "selection_details"),
    "section": ("edit_section", "selection_details"),
    "step": ("edit_step", "selection_details"),
    "nodal_load": ("edit_load", "selection_details"),
    "distributed_load": ("edit_load", "selection_details"),
    "boundary": ("edit_boundary", "selection_details"),
    "output_request": ("edit_output_request", "selection_details"),
    "instance": ("edit_instance_transform", "selection_details"),
}


def _build_toolbox_icon(command_id: str) -> QIcon | None:
    """为窄栏 toolbox 构建更紧凑的专用图标。"""

    palette = {
        "stroke": QColor("#526273"),
        "fill": QColor("#dce5ee"),
        "accent": QColor("#27425c"),
        "ok": QColor("#6b7c8d"),
    }
    size = 16
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(palette["stroke"])
    pen.setWidthF(1.2)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)

    if command_id == "open_material_manager":
        painter.setBrush(palette["fill"])
        painter.drawRoundedRect(QRectF(3.0, 2.5, 9.0, 11.0), 1.4, 1.4)
        painter.drawLine(QPointF(5.0, 5.3), QPointF(10.2, 5.3))
        painter.drawLine(QPointF(5.0, 7.8), QPointF(10.2, 7.8))
        painter.drawLine(QPointF(5.0, 10.3), QPointF(9.0, 10.3))
    elif command_id == "open_section_manager":
        painter.setBrush(palette["fill"])
        painter.drawRoundedRect(QRectF(2.5, 3.0, 11.0, 10.0), 1.4, 1.4)
        painter.drawLine(QPointF(8.0, 4.2), QPointF(8.0, 11.8))
        painter.drawLine(QPointF(4.3, 6.2), QPointF(11.7, 6.2))
        painter.drawLine(QPointF(4.3, 9.8), QPointF(11.7, 9.8))
    elif command_id == "assign_section":
        painter.setBrush(palette["fill"])
        painter.drawRoundedRect(QRectF(2.2, 5.2, 4.0, 4.0), 0.8, 0.8)
        painter.drawRoundedRect(QRectF(9.8, 5.2, 4.0, 4.0), 0.8, 0.8)
        arrow = QPainterPath()
        arrow.moveTo(6.8, 7.2)
        arrow.lineTo(10.2, 7.2)
        arrow.moveTo(8.8, 5.9)
        arrow.lineTo(10.2, 7.2)
        arrow.lineTo(8.8, 8.5)
        painter.drawPath(arrow)
    elif command_id == "validate_property_data":
        painter.setPen(QPen(palette["ok"], 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawLine(QPointF(3.4, 8.6), QPointF(6.7, 11.8))
        painter.drawLine(QPointF(6.7, 11.8), QPointF(12.8, 4.0))
    elif command_id == "open_step_manager":
        painter.setBrush(palette["fill"])
        painter.drawRoundedRect(QRectF(2.6, 2.8, 10.8, 10.2), 1.4, 1.4)
        painter.drawLine(QPointF(4.5, 5.5), QPointF(11.5, 5.5))
        painter.drawLine(QPointF(4.5, 8.0), QPointF(10.0, 8.0))
        painter.drawLine(QPointF(4.5, 10.5), QPointF(9.0, 10.5))
    elif command_id == "open_step_output_controls":
        painter.setBrush(palette["fill"])
        painter.drawRoundedRect(QRectF(2.5, 4.0, 4.2, 7.2), 0.9, 0.9)
        painter.drawRoundedRect(QRectF(9.3, 4.0, 4.2, 7.2), 0.9, 0.9)
        painter.drawLine(QPointF(6.8, 7.6), QPointF(9.2, 7.6))
        painter.drawLine(QPointF(8.0, 6.4), QPointF(9.2, 7.6))
        painter.drawLine(QPointF(8.0, 8.8), QPointF(9.2, 7.6))
    elif command_id == "open_step_diagnostics_placeholder":
        painter.drawEllipse(QRectF(3.0, 3.0, 10.0, 10.0))
        painter.drawLine(QPointF(8.0, 5.2), QPointF(8.0, 8.8))
        painter.drawPoint(QPointF(8.0, 10.9))
    elif command_id == "validate_and_run_step_tools":
        painter.setPen(QPen(palette["ok"], 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawLine(QPointF(2.9, 8.9), QPointF(5.8, 11.3))
        painter.drawLine(QPointF(5.8, 11.3), QPointF(10.2, 5.2))
        painter.setBrush(palette["accent"])
        play_path = QPainterPath()
        play_path.moveTo(10.2, 4.4)
        play_path.lineTo(13.0, 6.2)
        play_path.lineTo(10.2, 8.0)
        play_path.closeSubpath()
        painter.drawPath(play_path)
    elif command_id == "open_load_manager":
        painter.setBrush(palette["fill"])
        painter.drawRoundedRect(QRectF(2.4, 3.0, 11.2, 9.8), 1.4, 1.4)
        painter.drawLine(QPointF(4.2, 6.0), QPointF(11.8, 6.0))
        painter.drawLine(QPointF(4.2, 8.4), QPointF(10.5, 8.4))
        painter.drawEllipse(QRectF(10.7, 3.5, 2.0, 2.0))
    elif command_id == "open_boundary_manager":
        painter.setBrush(palette["fill"])
        painter.drawRoundedRect(QRectF(2.6, 3.0, 10.8, 9.8), 1.4, 1.4)
        painter.drawLine(QPointF(5.0, 5.4), QPointF(5.0, 10.9))
        painter.drawLine(QPointF(8.0, 5.4), QPointF(8.0, 10.9))
        painter.drawLine(QPointF(10.9, 5.4), QPointF(10.9, 10.9))
    elif command_id == "open_amplitude_manager_placeholder":
        wave = QPainterPath()
        wave.moveTo(2.5, 8.6)
        wave.cubicTo(4.4, 2.5, 6.1, 2.5, 8.0, 8.6)
        wave.cubicTo(9.6, 13.0, 11.2, 13.0, 13.5, 6.2)
        painter.drawPath(wave)
    elif command_id == "validate_load_support":
        painter.setPen(QPen(palette["ok"], 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawLine(QPointF(3.4, 8.8), QPointF(6.6, 11.7))
        painter.drawLine(QPointF(6.6, 11.7), QPointF(12.8, 4.2))
    else:
        painter.end()
        return None

    painter.end()
    return QIcon(pixmap)


def _enabled() -> GuiCommandAvailability:
    return GuiCommandAvailability(enabled=True)


def _disabled(reason: str) -> GuiCommandAvailability:
    return GuiCommandAvailability(enabled=False, unavailable_reason=reason)


def _require_model(window: PyFEMMainWindow) -> GuiCommandAvailability:
    if window.shell.state.opened_model is None:
        return _disabled("Load a model first.")
    if window._active_task is not None or window._is_busy:
        return _disabled("Wait for the current background task to finish.")
    return _enabled()


def _require_results(window: PyFEMMainWindow) -> GuiCommandAvailability:
    model_status = _require_model(window)
    if not model_status.enabled:
        return model_status
    if window._current_view_context is None:
        return _disabled("Open results first.")
    return _enabled()


def _selected_model_entry(window: PyFEMMainWindow) -> tuple[str, str] | None:
    entry = window.navigation_panel.current_model_entry()
    if entry is None:
        return None
    kind, name = entry
    if name in {None, ""}:
        return None
    return normalize_object_kind(kind), str(name)


def _require_selected_kind(window: PyFEMMainWindow, *allowed_kinds: str) -> GuiCommandAvailability:
    model_status = _require_model(window)
    if not model_status.enabled:
        return model_status
    selected_entry = _selected_model_entry(window)
    if selected_entry is None:
        return _disabled("Select an object in the model tree first.")
    if selected_entry[0] not in allowed_kinds:
        return _disabled(f"Current selection is not a supported {', '.join(allowed_kinds)} entry.")
    return _enabled()


def _latest_snapshot(window: PyFEMMainWindow):
    candidates = [snapshot for snapshot in (window.shell.state.last_export_snapshot, window.shell.state.last_run_snapshot) if snapshot is not None]
    if not candidates:
        return None
    return max(candidates, key=lambda snapshot: snapshot.created_at)


def _require_last_snapshot(window: PyFEMMainWindow) -> GuiCommandAvailability:
    model_status = _require_model(window)
    if not model_status.enabled:
        return model_status
    if _latest_snapshot(window) is None:
        return _disabled("Create or run a snapshot first.")
    return _enabled()


def _require_results_or_model_selection(window: PyFEMMainWindow) -> GuiCommandAvailability:
    if window._active_task is not None or window._is_busy:
        return _disabled("Wait for the current background task to finish.")
    if window._current_view_context is not None:
        return _enabled()
    if window.shell.state.opened_model is None:
        return _disabled("Load a model or open results first.")
    if _selected_model_entry(window) is None:
        return _disabled("Select an object in the model tree first.")
    return _enabled()


def _detail_block(title: str, rows: Sequence[tuple[str, object]]) -> str:
    return "\n".join([title, "-" * len(title), *(f"{label}: {value}" for label, value in rows)])


def _pretty_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _join(values: Sequence[str]) -> str:
    return ", ".join(values) or "-"


def _issues_text(issues: Sequence[object]) -> str:
    if not issues:
        return "No issues found."
    return "\n".join(f"{index}. [{issue.severity}] {issue.code}: {issue.message}" for index, issue in enumerate(issues, start=1))


def _loaded_model(window: PyFEMMainWindow) -> ModelDB:
    return window.shell.clone_loaded_model()


def _show_text(window: PyFEMMainWindow, title: str, text: str) -> None:
    window._show_text_details(title=title, text=text)


def _selected_details(window: PyFEMMainWindow) -> tuple[str, str]:
    if window._current_view_context is not None and window.module_combo.currentData() == "Visualization":
        detail_text = window.navigation_panel.current_results_details_text()
        title = detail_text.splitlines()[0].strip() or "Selection Details"
        return title, detail_text
    model = _loaded_model(window)
    entry = _selected_model_entry(window)
    if entry is None:
        return "Selection Details", "Nothing is currently selected."
    kind, name = entry
    payload: object = {"kind": kind, "name": name}
    if kind == "material":
        payload = model.materials[name].to_dict()
    elif kind == "section":
        payload = model.sections[name].to_dict()
    elif kind == "step":
        payload = model.steps[name].to_dict()
    elif kind == "nodal_load":
        payload = model.nodal_loads[name].to_dict()
    elif kind == "distributed_load":
        payload = model.distributed_loads[name].to_dict()
    elif kind == "boundary":
        payload = model.boundaries[name].to_dict()
    elif kind == "output_request":
        payload = model.output_requests[name].to_dict()
    elif kind == "instance" and model.assembly is not None:
        payload = model.assembly.instances[name].to_dict()
    elif kind == "part":
        payload = model.parts[name].to_dict()
    return f"{kind} {name}", _pretty_json(payload)


def _part_summary(model: ModelDB, selected_name: str | None) -> str:
    rows: list[tuple[str, object]] = [
        ("model", model.name),
        ("parts", len(model.parts)),
        ("total_nodes", sum(len(part.mesh.nodes) for part in model.parts.values())),
        ("total_elements", sum(len(part.mesh.elements) for part in model.parts.values())),
        ("part_names", _join(tuple(model.parts.keys()))),
    ]
    if selected_name is not None and selected_name in model.parts:
        part = model.parts[selected_name]
        rows.extend(
            [
                ("selected_part", selected_name),
                ("nodes", len(part.mesh.nodes)),
                ("elements", len(part.mesh.elements)),
                ("node_sets", _join(tuple(part.mesh.node_sets.keys()))),
                ("element_sets", _join(tuple(part.mesh.element_sets.keys()))),
                ("surfaces", _join(tuple(part.mesh.surfaces.keys()))),
            ]
        )
    return _detail_block("Part Summary", rows)


def _property_summary(model: ModelDB, entry: tuple[str, str] | None) -> str:
    rows: list[tuple[str, object]] = [
        ("model", model.name),
        ("materials", len(model.materials)),
        ("sections", len(model.sections)),
        ("output_requests", len(model.output_requests)),
        ("material_names", _join(tuple(model.materials.keys()))),
        ("section_names", _join(tuple(model.sections.keys()))),
        ("output_request_names", _join(tuple(model.output_requests.keys()))),
    ]
    if entry is not None:
        rows.append(("selection", f"{entry[0]}:{entry[1]}"))
    return _detail_block("Property Summary", rows)


def _assembly_summary(model: ModelDB, selected_name: str | None) -> str:
    rows: list[tuple[str, object]] = [("model", model.name)]
    if model.assembly is None:
        rows.append(("assembly", "No assembly instances are available."))
        return _detail_block("Assembly Summary", rows)
    rows.extend([("assembly_name", model.assembly.name), ("instances", len(model.assembly.instances)), ("instance_names", _join(tuple(model.assembly.instances.keys())))])
    if selected_name is not None and selected_name in model.assembly.instances:
        instance = model.assembly.instances[selected_name]
        rows.extend([("selected_instance", selected_name), ("part_name", instance.part_name), ("translation", instance.transform.translation or (0.0, 0.0, 0.0)), ("rotation", instance.transform.rotation or "identity")])
    return _detail_block("Assembly Summary", rows)


def _step_summary(model: ModelDB, selected_name: str | None) -> str:
    rows: list[tuple[str, object]] = [("model", model.name), ("steps", len(model.steps)), ("step_names", _join(tuple(model.steps.keys())))]
    if selected_name is not None and selected_name in model.steps:
        step = model.steps[selected_name]
        rows.extend([("selected_step", step.name), ("procedure_type", step.procedure_type), ("boundaries", _join(step.boundary_names)), ("nodal_loads", _join(step.nodal_load_names)), ("distributed_loads", _join(step.distributed_load_names)), ("output_requests", _join(step.output_request_names)), ("parameters", _pretty_json(step.parameters))])
    return _detail_block("Step Summary", rows)


def _mesh_statistics(model: ModelDB) -> dict[str, object]:
    counter: Counter[str] = Counter()
    parts: dict[str, object] = {}
    for part_name, part in model.parts.items():
        part_counter = Counter(element.type_key for element in part.mesh.elements.values())
        counter.update(part_counter)
        parts[part_name] = {"nodes": len(part.mesh.nodes), "elements": len(part.mesh.elements), "node_sets": list(part.mesh.node_sets.keys()), "element_sets": list(part.mesh.element_sets.keys()), "surfaces": list(part.mesh.surfaces.keys()), "element_types": dict(part_counter)}
    return {"model_name": model.name, "part_count": len(model.parts), "total_nodes": sum(len(part.mesh.nodes) for part in model.parts.values()), "total_elements": sum(len(part.mesh.elements) for part in model.parts.values()), "element_types": dict(counter), "parts": parts}


def _interaction_issues(model: ModelDB) -> tuple[object, ...]:
    return tuple(issue for issue in collect_export_capability_issues(model) if issue.object_kind in {"interaction", "raw_keyword_block"})


def _property_issues(model: ModelDB) -> tuple[object, ...]:
    return tuple(issue for issue in collect_export_capability_issues(model) if issue.object_kind in {"material", "section", "output_request"})


def _load_issues(model: ModelDB) -> tuple[object, ...]:
    return tuple(issue for issue in collect_run_capability_issues(model) if issue.object_kind in {"boundary", "nodal_load", "distributed_load"})


def _result_measure_text(window: PyFEMMainWindow) -> str:
    if window._current_view_context is None:
        return "No active result field is available."
    step_name = window.results_browser.current_step_name
    frame_id = window.results_browser.current_frame_id
    field_name = window.results_browser.current_field_name
    if step_name is None or frame_id is None or field_name is None:
        return "No active result field is available."
    overview = next((item for item in window._current_view_context.results_facade.fields(step_name=step_name, frame_id=frame_id) if item.field_name == field_name), None)
    if overview is None:
        return "Current result overview is unavailable."
    return _detail_block("Result Measure Info", (("step", step_name), ("frame", frame_id), ("field", overview.field_name), ("source", overview.source_type), ("position", overview.position), ("components", _join(overview.component_names)), ("targets", overview.target_count), ("min", "-" if overview.min_value is None else f"{overview.min_value:.6g}"), ("max", "-" if overview.max_value is None else f"{overview.max_value:.6g}"), ("metadata", _pretty_json(overview.metadata))))


def _job_diagnostics_text(window: PyFEMMainWindow) -> str:
    snapshot = _latest_snapshot(window)
    report = window.shell.state.last_job_report
    rows: list[tuple[str, object]] = [("model", "-" if window.shell.state.opened_model is None else window.shell.state.opened_model.model_name), ("snapshot", "-" if snapshot is None else snapshot.snapshot_path), ("manifest", "-" if snapshot is None else snapshot.manifest_path), ("results_path", "-" if snapshot is None else snapshot.results_path)]
    if report is not None:
        rows.extend([("last_step", report.step_name), ("procedure_type", report.procedure_type), ("frames", report.frame_count), ("histories", report.history_count), ("summaries", report.summary_count), ("results_file", report.results_path or "-")])
    return _detail_block("Job Diagnostics", rows)


def _edit_selected(window: PyFEMMainWindow) -> None:
    window._edit_selected_model_object()


def _open_material_manager(window: PyFEMMainWindow) -> None:
    window._open_material_manager()


def _open_section_manager(window: PyFEMMainWindow) -> None:
    window._open_section_manager()


def _open_step_manager(window: PyFEMMainWindow) -> None:
    window._open_step_manager()


def _open_step_output_controls(window: PyFEMMainWindow) -> None:
    window._open_step_output_controls()


def _assign_section(window: PyFEMMainWindow) -> None:
    window._open_assign_section_dialog()


def _open_load_manager(window: PyFEMMainWindow) -> None:
    window._open_load_manager()


def _open_boundary_manager(window: PyFEMMainWindow) -> None:
    window._open_boundary_manager()


def _edit_material(window: PyFEMMainWindow) -> None:
    window._trigger_model_edit_for_kind("material")


def _edit_section(window: PyFEMMainWindow) -> None:
    window._trigger_model_edit_for_kind("section")


def _edit_output_request(window: PyFEMMainWindow) -> None:
    window._trigger_model_edit_for_kind("output_request")


def _edit_instance_transform(window: PyFEMMainWindow) -> None:
    window._trigger_model_edit_for_kind("instance")


def _edit_step(window: PyFEMMainWindow) -> None:
    window._trigger_model_edit_for_kind("step")


def _edit_nonlinear_controls(window: PyFEMMainWindow) -> None:
    window._open_step_edit_dialog(focus_nonlinear=True)


def _output_controls_shortcut(window: PyFEMMainWindow) -> None:
    window._open_output_controls_shortcut()


def _validate_and_run_step_tools(window: PyFEMMainWindow) -> None:
    model = _loaded_model(window)
    entry = _selected_model_entry(window)
    selected_step = entry[1] if entry is not None and entry[0] == "step" else None
    issues = collect_run_capability_issues(model)
    rows: list[tuple[str, object]] = [
        ("model", model.name),
        ("steps", _join(tuple(model.steps.keys()))),
        ("selected_step", selected_step or "-"),
        ("run_issues", "none" if not issues else len(issues)),
        ("write_inp", "Use Write INP... from the formal snapshot path."),
        ("run_model", "Use Run Current Model from the formal Job Snapshot path."),
    ]
    detail_text = _detail_block("Validate / Run", rows)
    if issues:
        detail_text = f"{detail_text}\n\nIssues\n------\n{_issues_text(issues)}"
    else:
        detail_text = f"{detail_text}\n\nIssues\n------\nNo run capability issues found."
    _show_text(window, "Validate / Run", detail_text)


def _edit_load(window: PyFEMMainWindow) -> None:
    window._trigger_model_edit_for_kind("load")


def _edit_boundary(window: PyFEMMainWindow) -> None:
    window._trigger_model_edit_for_kind("boundary")


def _selection_details(window: PyFEMMainWindow) -> None:
    title, text = _selected_details(window)
    _show_text(window, title, text)


def _refresh_geometry(window: PyFEMMainWindow) -> None:
    window._refresh_geometry_from_shell()


def _part_summary_action(window: PyFEMMainWindow) -> None:
    entry = _selected_model_entry(window)
    _show_text(window, "Part Summary", _part_summary(_loaded_model(window), None if entry is None or entry[0] != "part" else entry[1]))


def _property_summary_action(window: PyFEMMainWindow) -> None:
    _show_text(window, "Property Summary", _property_summary(_loaded_model(window), _selected_model_entry(window)))


def _assembly_summary_action(window: PyFEMMainWindow) -> None:
    entry = _selected_model_entry(window)
    _show_text(window, "Assembly Summary", _assembly_summary(_loaded_model(window), None if entry is None or entry[0] != "instance" else entry[1]))


def _step_summary_action(window: PyFEMMainWindow) -> None:
    entry = _selected_model_entry(window)
    _show_text(window, "Step Summary", _step_summary(_loaded_model(window), None if entry is None or entry[0] != "step" else entry[1]))


def _mesh_summary_action(window: PyFEMMainWindow) -> None:
    stats = _mesh_statistics(_loaded_model(window))
    _show_text(window, "Mesh Summary", _detail_block("Mesh Summary", (("model", stats["model_name"]), ("parts", stats["part_count"]), ("total_nodes", stats["total_nodes"]), ("total_elements", stats["total_elements"]), ("element_types", _pretty_json(stats["element_types"])))))


def _verify_mesh(window: PyFEMMainWindow) -> None:
    model = _loaded_model(window)
    model.validate()
    geometry = window.shell.build_viewport_geometry()
    _show_text(window, "Verify Mesh", _detail_block("Verify Mesh", (("model", model.name), ("nodes", len(geometry.points)), ("elements", len(geometry.cell_connectivities)), ("status", "Mesh verification passed."))))


def _mesh_statistics_action(window: PyFEMMainWindow) -> None:
    _show_text(window, "Mesh Statistics", _pretty_json(_mesh_statistics(_loaded_model(window))))


def _noop(window: PyFEMMainWindow) -> None:
    del window


def _command(command_id: str, display_name: str, module_name: str, button_label: str, tooltip: str, icon_key: str, trigger: CommandHandler, capability: CapabilityPredicate, *, uses_dialog: bool = True, shortcut: str | None = None) -> GuiCommandDefinition:
    return GuiCommandDefinition(command_id=command_id, display_name=display_name, module_name=module_name, button_label=button_label, tooltip=tooltip, is_placeholder=False, uses_dialog=uses_dialog, icon_key=icon_key, trigger=trigger, capability=capability, shortcut=shortcut)


def _placeholder(command_id: str, display_name: str, module_name: str, button_label: str, tooltip: str, unavailable_reason: str, capability: CapabilityPredicate) -> GuiCommandDefinition:
    return GuiCommandDefinition(command_id=command_id, display_name=display_name, module_name=module_name, button_label=button_label, tooltip=tooltip, is_placeholder=True, uses_dialog=True, icon_key="placeholder", trigger=_noop, capability=capability, unavailable_reason=unavailable_reason)


def _interaction_summary_action(window: PyFEMMainWindow) -> None:
    model = _loaded_model(window)
    _show_text(window, "Interaction Summary", _detail_block("Interaction Summary", (("model", model.name), ("interactions", len(model.interactions)), ("interaction_names", _join(tuple(model.interactions.keys()))), ("raw_keyword_blocks", len(model.raw_keyword_blocks)), ("raw_keyword_names", _join(tuple(model.raw_keyword_blocks.keys()))))))


def _raw_keyword_action(window: PyFEMMainWindow) -> None:
    model = _loaded_model(window)
    payload = {"raw_keyword_blocks": [_raw_keyword_summary(block) for block in model.raw_keyword_blocks.values()], "message": "Formal edit UI is not ready yet; this entry keeps the official access point and explanation path."}
    _show_text(window, "Raw Keyword Blocks", _pretty_json(payload))


def _unsupported_interaction_action(window: PyFEMMainWindow) -> None:
    _show_text(window, "Unsupported Interaction Info", _issues_text(_interaction_issues(_loaded_model(window))))


def _validate_interaction_action(window: PyFEMMainWindow) -> None:
    issues = _interaction_issues(_loaded_model(window))
    _show_text(window, "Validate Interaction Support", "Interaction support checks passed." if not issues else _issues_text(issues))


def _load_summary_action(window: PyFEMMainWindow) -> None:
    model = _loaded_model(window)
    entry = _selected_model_entry(window)
    _show_text(window, "Load Summary", _detail_block("Load Summary", (("model", model.name), ("boundaries", len(model.boundaries)), ("nodal_loads", len(model.nodal_loads)), ("distributed_loads", len(model.distributed_loads)), ("boundary_names", _join(tuple(model.boundaries.keys()))), ("nodal_load_names", _join(tuple(model.nodal_loads.keys()))), ("distributed_load_names", _join(tuple(model.distributed_loads.keys()))), ("selection", "-" if entry is None else f"{entry[0]}:{entry[1]}"))))


def _unsupported_nlgeom_load_action(window: PyFEMMainWindow) -> None:
    issues = tuple(issue for issue in _load_issues(_loaded_model(window)) if "nlgeom" in issue.code or "nlgeom" in issue.message.lower())
    _show_text(window, "Unsupported Nlgeom Load Info", _issues_text(issues))


def _validate_load_action(window: PyFEMMainWindow) -> None:
    issues = _load_issues(_loaded_model(window))
    _show_text(window, "Validate Load Support", "Load and boundary checks passed." if not issues else _issues_text(issues))


def _validate_property_action(window: PyFEMMainWindow) -> None:
    model = _loaded_model(window)
    model.validate()
    issues = _property_issues(model)
    _show_text(window, "Validate Property Data", "Property checks passed." if not issues else _issues_text(issues))


def _optimization_info_action(window: PyFEMMainWindow) -> None:
    model = _loaded_model(window)
    _show_text(window, "Optimization Info", _detail_block("Optimization Info", (("model", model.name), ("formal_entries", "Save As Derived Case / Write INP / Run Current Model"), ("positioning", "Reuse the existing snapshot and run path instead of adding a GUI side-channel."), ("future_hooks", "Parameter Variant / Batch Case / Design Variable / Response"))))


def _run_last_snapshot(window: PyFEMMainWindow) -> None:
    window._run_last_snapshot()


def _open_snapshot_manifest(window: PyFEMMainWindow) -> None:
    window._open_snapshot_manifest()


def _job_diagnostics_action(window: PyFEMMainWindow) -> None:
    window._open_job_diagnostics_dialog()


def _open_job_center(window: PyFEMMainWindow) -> None:
    window._open_job_center_dialog()


def _open_current_job_monitor(window: PyFEMMainWindow) -> None:
    window._open_job_monitor_dialog()


def _open_results_output(window: PyFEMMainWindow) -> None:
    window._open_results_output_entry()


def _open_results(window: PyFEMMainWindow) -> None:
    window._browse_and_open_results()


def _export_vtk(window: PyFEMMainWindow) -> None:
    window._browse_and_export_vtk()


def _probe(window: PyFEMMainWindow) -> None:
    window._focus_probe_panel()


def _legend_settings(window: PyFEMMainWindow) -> None:
    window._show_legend_settings_dialog()


def _result_measure_action(window: PyFEMMainWindow) -> None:
    _show_text(window, "Result Measure Info", _result_measure_text(window))


COMMAND_DEFINITIONS: tuple[GuiCommandDefinition, ...] = (
    _command("edit_selected", "Edit Selected...", "Part", "Edit", "Open the formal editor for the current model-tree selection.", "edit", _edit_selected, lambda window: _require_selected_kind(window, "material", "section", "step", "nodal_load", "distributed_load", "boundary", "output_request", "instance"), shortcut="Ctrl+Return"),
    _command("selection_details", "Selection Details...", "Part", "Details", "Show the formal details dialog for the current model or result selection.", "details", _selection_details, _require_results_or_model_selection),
    _command("refresh_geometry", "Refresh Geometry", "Part", "Refresh", "Rebuild viewport geometry from the current formal model state.", "refresh", _refresh_geometry, _require_model, uses_dialog=False),
    _command("part_summary", "Part Summary", "Part", "Summary", "Show the Part module summary.", "summary", _part_summary_action, _require_model),
    _placeholder("create_part_placeholder", "Create Part", "Part", "Create", "Reserved formal entry for future Part creation.", "Formal Part creation is not supported yet.", _require_model),
    _placeholder("import_part_placeholder", "Import Part", "Part", "Import", "Reserved formal entry for future Part import.", "Formal Part import is not supported yet.", _require_model),
    _placeholder("partition_placeholder", "Partition", "Part", "Partition", "Reserved formal entry for future partitioning.", "Formal partition tools are not supported yet.", _require_model),
    _placeholder("mesh_seed_placeholder", "Mesh Seed", "Part", "Seed", "Reserved formal entry for future mesh seeding.", "Formal mesh seed controls are not supported yet.", _require_model),
    _command("open_material_manager", "Materials...", "Property", "Materials...", "Open the formal Materials manager.", "edit", _open_material_manager, _require_model),
    _command("open_section_manager", "Sections...", "Property", "Sections...", "Open the formal Sections manager.", "edit", _open_section_manager, _require_model),
    _command("assign_section", "Assign Section...", "Property", "Assign Section...", "Open the formal section-assignment dialog.", "edit", _assign_section, _require_model),
    _command("validate_property_data", "Validate Property Data", "Property", "Validate", "Validate current materials, sections and output requests.", "validate", _validate_property_action, _require_model),
    _command("edit_material", "Edit Material...", "Property", "Material", "Open the formal Material editor.", "edit", _edit_material, lambda window: _require_selected_kind(window, "material")),
    _command("edit_section", "Edit Section...", "Property", "Section", "Open the formal Section editor.", "edit", _edit_section, lambda window: _require_selected_kind(window, "section")),
    _command("edit_output_request", "Edit Output Request...", "Property", "Output", "Open the formal Output Request editor.", "edit", _edit_output_request, lambda window: _require_selected_kind(window, "output_request")),
    _command("property_summary", "Property Summary", "Property", "Summary", "Show the Property module summary.", "summary", _property_summary_action, _require_model),
    _placeholder("assign_section_placeholder", "Assign Section", "Property", "Assign", "Reserved formal entry for future section assignment.", "Formal section assignment is not supported yet.", _require_model),
    _placeholder("material_library_placeholder", "Material Library", "Property", "Library", "Reserved formal entry for a future material library.", "A formal material library is not supported yet.", _require_model),
    _placeholder("raw_property_extension_placeholder", "Raw Property Extension", "Property", "Raw Ext", "Reserved formal entry for future raw property extensions.", "Raw property extensions are not supported yet.", _require_model),
    _command("edit_instance_transform", "Edit Instance Transform...", "Assembly", "Transform", "Open the formal instance transform editor.", "edit", _edit_instance_transform, lambda window: _require_selected_kind(window, "instance")),
    _command("save_as_derived_case", "Save As Derived Case...", "Assembly", "Save Case", "Save the current model through the formal derived-case path.", "save", lambda window: window._save_as_derived_case(), _require_model),
    _command("assembly_summary", "Assembly Summary", "Assembly", "Summary", "Show the Assembly module summary.", "summary", _assembly_summary_action, _require_model),
    _placeholder("duplicate_instance_placeholder", "Duplicate Instance", "Assembly", "Duplicate", "Reserved formal entry for future instance duplication.", "Formal instance duplication is not supported yet.", _require_model),
    _placeholder("suppress_resume_instance_placeholder", "Suppress/Resume Instance", "Assembly", "Suppress", "Reserved formal entry for future suppress/resume workflows.", "Suppress/resume instance workflows are not supported yet.", _require_model),
    _placeholder("create_assembly_set_placeholder", "Create Assembly Set", "Assembly", "Asm Set", "Reserved formal entry for future assembly sets.", "Formal assembly-set creation is not supported yet.", _require_model),
    _placeholder("create_surface_placeholder", "Create Surface", "Assembly", "Surface", "Reserved formal entry for future surfaces.", "Formal surface creation is not supported yet.", _require_model),
    _command("open_step_manager", "Steps...", "Step", "Steps...", "Open the formal Step manager.", "edit", _open_step_manager, _require_model),
    _command("open_step_output_controls", "Output Controls...", "Step", "Output\nControls...", "Open step-related output controls from the current step or output_request context.", "edit", _open_step_output_controls, _require_model),
    _placeholder("open_step_diagnostics_placeholder", "Diagnostics...", "Step", "Diagnostics...", "Reserved utility entry for future step diagnostics.", "Formal step diagnostics are not supported yet.", _require_model),
    _command("validate_and_run_step_tools", "Validate / Run", "Step", "Validate /\nRun", "Review current step/run readiness and the formal write/run path.", "validate", _validate_and_run_step_tools, _require_model),
    _command("edit_step", "Edit Step...", "Step", "Edit", "Open the formal Step editor.", "edit", _edit_step, lambda window: _require_selected_kind(window, "step")),
    _command("step_summary", "Step Summary", "Step", "Summary", "Show the Step module summary.", "summary", _step_summary_action, _require_model),
    _command("edit_nonlinear_controls", "Edit Nonlinear Controls...", "Step", "Nlgeom", "Open nonlinear controls through the same formal Step editor.", "edit", _edit_nonlinear_controls, lambda window: _require_selected_kind(window, "step")),
    _command("output_controls_shortcut", "Output Controls Shortcut...", "Step", "Outputs", "Jump into the formal output-request editor from Step context.", "edit", _output_controls_shortcut, _require_model),
    _command("write_inp", "Write INP...", "Step", "Write", "Write INP through the formal snapshot/export path.", "save", lambda window: window._write_inp_snapshot(), _require_model, shortcut="Ctrl+Shift+S"),
    _command("run_current_model", "Run Current Model", "Step", "Run", "Run the current model through the formal Job Snapshot path.", "run", lambda window: window.run_job(), _require_model, uses_dialog=False),
    _command("interaction_summary", "Interaction Summary", "Interaction", "Summary", "Show the Interaction module summary.", "summary", _interaction_summary_action, _require_model),
    _command("edit_raw_keyword_block", "Edit Raw Keyword Block", "Interaction", "Raw KW", "Show the current raw keyword blocks and the formal extension point.", "details", _raw_keyword_action, _require_model),
    _command("unsupported_interaction_info", "Unsupported Interaction Info", "Interaction", "Info", "Show current unsupported interaction boundaries.", "details", _unsupported_interaction_action, _require_model),
    _placeholder("create_contact_placeholder", "Create Contact", "Interaction", "Contact", "Reserved formal entry for future contact creation.", "Formal contact creation is not supported yet.", _require_model),
    _placeholder("create_constraint_placeholder", "Create Constraint", "Interaction", "Constr", "Reserved formal entry for future constraint creation.", "Formal constraint creation is not supported yet.", _require_model),
    _placeholder("create_coupling_placeholder", "Create Coupling", "Interaction", "Couple", "Reserved formal entry for future coupling creation.", "Formal coupling creation is not supported yet.", _require_model),
    _placeholder("create_tie_placeholder", "Create Tie", "Interaction", "Tie", "Reserved formal entry for future tie creation.", "Formal tie creation is not supported yet.", _require_model),
    _command("validate_interaction_support", "Validate Interaction Support", "Interaction", "Validate", "Validate current interaction-related support boundaries.", "validate", _validate_interaction_action, _require_model),
    _command("open_load_manager", "Loads...", "Load", "Loads...", "Open the formal load manager for nodal and distributed loads.", "edit", _open_load_manager, _require_model),
    _command("open_boundary_manager", "Boundaries...", "Load", "Boundaries...", "Open the formal boundary manager.", "edit", _open_boundary_manager, _require_model),
    _placeholder("open_amplitude_manager_placeholder", "Amplitudes...", "Load", "Amplitudes...", "Reserved formal manager entry for future amplitudes.", "Formal amplitude management is not supported yet.", _require_model),
    _command("validate_load_support", "Validate Load Support", "Load", "Validate", "Validate current loads and boundaries against the formal run path.", "validate", _validate_load_action, _require_model),
    _command("edit_load", "Edit Load...", "Load", "Load", "Open the formal load editor.", "edit", _edit_load, lambda window: _require_selected_kind(window, "nodal_load", "distributed_load")),
    _command("edit_boundary", "Edit Boundary...", "Load", "Boundary", "Open the formal boundary editor.", "edit", _edit_boundary, lambda window: _require_selected_kind(window, "boundary")),
    _command("load_summary", "Load Summary", "Load", "Summary", "Show the Load module summary.", "summary", _load_summary_action, _require_model),
    _command("unsupported_nlgeom_load_info", "Unsupported Nlgeom Load Info", "Load", "Nlgeom", "Show unsupported load boundaries under nlgeom-related scenarios.", "details", _unsupported_nlgeom_load_action, _require_model),
    _command("mesh_summary", "Mesh Summary", "Mesh", "Summary", "Show the Mesh module summary.", "summary", _mesh_summary_action, _require_model),
    _command("verify_mesh", "Verify Mesh", "Mesh", "Verify", "Run the formal mesh verification path.", "validate", _verify_mesh, _require_model),
    _command("mesh_statistics", "Mesh Statistics", "Mesh", "Stats", "Show mesh statistics for the current model.", "details", _mesh_statistics_action, _require_model),
    _placeholder("element_quality_placeholder", "Element Quality", "Mesh", "Quality", "Reserved formal entry for future element-quality checks.", "Formal element-quality checks are not supported yet.", _require_model),
    _placeholder("export_mesh_placeholder", "Export Mesh", "Mesh", "Export", "Reserved formal entry for future mesh export.", "Formal mesh export is not supported yet.", _require_model),
    _placeholder("seed_controls_placeholder", "Seed Controls", "Mesh", "Seed", "Reserved formal entry for future seed controls.", "Formal seed controls are not supported yet.", _require_model),
    _placeholder("generate_mesh_placeholder", "Generate Mesh", "Mesh", "Generate", "Reserved formal entry for future mesh generation.", "Formal mesh generation is not supported yet.", _require_model),
    _placeholder("parameter_variant_placeholder", "Parameter Variant", "Optimization", "Variant", "Reserved formal entry for future parameter variants.", "Formal parameter variants are not supported yet.", _require_model),
    _placeholder("batch_case_placeholder", "Batch Case", "Optimization", "Batch", "Reserved formal entry for future batch cases.", "Formal batch-case workflows are not supported yet.", _require_model),
    _placeholder("design_variable_placeholder", "Design Variable", "Optimization", "Design", "Reserved formal entry for future design variables.", "Formal design variables are not supported yet.", _require_model),
    _placeholder("response_placeholder", "Response", "Optimization", "Response", "Reserved formal entry for future responses.", "Formal response definitions are not supported yet.", _require_model),
    _command("optimization_info", "Optimization Info", "Optimization", "Info", "Explain the current Optimization entry strategy and future hooks.", "details", _optimization_info_action, _require_model),
    _command("open_job_center", "Job Center...", "Job", "Job\nCenter...", "Open the formal Job Center for run records and execution actions.", "open", _open_job_center, lambda window: _enabled()),
    _command("open_current_job_monitor", "Monitor Current Run...", "Job", "Monitor\nCurrent\nRun...", "Open the formal Job Monitor for the active or latest run record.", "details", _open_current_job_monitor, lambda window: _enabled()),
    _command("open_job_diagnostics", "Diagnostics...", "Job", "Diagnostics...", "Open the formal Job Diagnostics summary dialog.", "details", _job_diagnostics_action, lambda window: _enabled()),
    _command("open_results_output", "Results / Output...", "Job", "Results /\nOutput...", "Open the latest results, report or snapshot manifest through the formal job output entry.", "open", _open_results_output, lambda window: _enabled()),
    _command("run_last_snapshot", "Run Last Snapshot", "Job", "Run Last", "Re-run the latest snapshot through the formal snapshot path.", "run", _run_last_snapshot, _require_last_snapshot, uses_dialog=False),
    _command("open_snapshot_manifest", "Open Snapshot Manifest", "Job", "Manifest", "Open the manifest of the latest snapshot.", "details", _open_snapshot_manifest, _require_last_snapshot),
    _placeholder("job_history_placeholder", "Job History", "Job", "History", "Reserved formal entry for future job history.", "Formal job history is not supported yet.", _require_model),
    _command("open_results", "Open Results...", "Job", "Results", "Open results through the formal ResultsFacade path.", "open", _open_results, _require_model, shortcut="Ctrl+Shift+O"),
    _command("job_diagnostics", "Job Diagnostics", "Job", "Diag", "Show current job and snapshot diagnostics.", "details", _job_diagnostics_action, _require_model),
    _command("export_vtk", "Export VTK...", "Visualization", "VTK", "Export the currently opened results to VTK through the formal exporter.", "save", _export_vtk, _require_results, shortcut="Ctrl+E"),
    _command("probe", "Probe", "Visualization", "Probe", "Open the formal probe dialog.", "details", _probe, _require_results),
    _command("legend_settings", "Legend Settings...", "Visualization", "Legend", "Open the formal legend settings dialog.", "details", _legend_settings, _require_results),
    _placeholder("result_field_selector_placeholder", "Result Field Selector", "Visualization", "Field", "Reserved formal entry for a richer result-field selector.", "A richer result-field selector is not supported yet.", _require_results),
    _command("result_measure_info", "Result Measure Info", "Visualization", "Measure", "Show current result field metadata and measure information.", "details", _result_measure_action, _require_results),
    _placeholder("screenshot_export_figure_placeholder", "Screenshot/Export Figure", "Visualization", "Figure", "Reserved formal entry for future screenshot/export workflows.", "Formal screenshot/export workflows are not supported yet.", _require_results),
)


class GuiCommandRegistry:
    """负责创建、缓存并刷新统一命令对象。"""

    def __init__(self, window: PyFEMMainWindow, style: QStyle) -> None:
        self._window = window
        self._definitions = {definition.command_id: definition for definition in COMMAND_DEFINITIONS}
        self._icons = {
            "open": style.standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton),
            "save": style.standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton),
            "run": style.standardIcon(QStyle.StandardPixmap.SP_MediaPlay),
            "refresh": style.standardIcon(QStyle.StandardPixmap.SP_BrowserReload),
            "edit": style.standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView),
            "details": style.standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation),
            "summary": style.standardIcon(QStyle.StandardPixmap.SP_FileIcon),
            "validate": style.standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton),
            "placeholder": style.standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning),
        }
        self._toolbox_icons = {
            command_id: icon
            for command_id in (
                "open_material_manager",
                "open_section_manager",
                "assign_section",
                "validate_property_data",
                "open_step_manager",
                "open_step_output_controls",
                "open_step_diagnostics_placeholder",
                "validate_and_run_step_tools",
                "open_load_manager",
                "open_boundary_manager",
                "open_amplitude_manager_placeholder",
                "validate_load_support",
            )
            if (icon := _build_toolbox_icon(command_id)) is not None
        }
        self._actions = self._build_actions()

    def action(self, command_id: str) -> QAction:
        """按命令标识返回共享 QAction。"""

        return self._actions[command_id]

    def definitions_for_module(self, module_name: str) -> tuple[GuiCommandDefinition, ...]:
        """返回指定模块的命令定义序列。"""

        return tuple(self._definitions[command_id] for command_id in MODULE_COMMAND_IDS[module_name])

    def toolbox_specs_for_module(self, module_name: str) -> tuple[ToolboxButtonSpec, ...]:
        """返回指定模块的 toolbox 按钮描述。"""

        return tuple(
            ToolboxButtonSpec(
                key=definition.command_id,
                label=definition.button_label,
                action=self.action(definition.command_id),
                icon=self._toolbox_icons.get(definition.command_id, self.action(definition.command_id).icon()),
                tooltip=self.action(definition.command_id).toolTip() or definition.tooltip,
            )
            for definition in self.definitions_for_module(module_name)
        )

    def model_context_actions_for_entry(self, kind: str, name: object) -> tuple[QAction, ...]:
        """为模型树右键菜单返回共享命令动作。"""

        if name in {None, ""}:
            return ()
        return tuple(self.action(command_id) for command_id in MODEL_CONTEXT_COMMAND_IDS.get(normalize_object_kind(kind), ()))

    def refresh(self) -> None:
        """按当前主窗口上下文刷新全部命令状态。"""

        for definition in COMMAND_DEFINITIONS:
            action = self._actions[definition.command_id]
            availability = definition.capability(self._window)
            tooltip_parts = [definition.tooltip]
            if definition.is_placeholder and definition.unavailable_reason:
                tooltip_parts.append(f"Planned: {definition.unavailable_reason}")
            if availability.unavailable_reason:
                tooltip_parts.append(f"Unavailable: {availability.unavailable_reason}")
            action.setEnabled(availability.enabled)
            action.setToolTip("\n\n".join(part for part in tooltip_parts if part))
            action.setStatusTip(action.toolTip())

    def trigger(self, command_id: str) -> None:
        """按统一规则触发命令。"""

        definition = self._definitions[command_id]
        availability = definition.capability(self._window)
        if not availability.enabled:
            self._window._show_command_unavailable(definition.display_name, availability.unavailable_reason or "This command is unavailable.")
            return
        if definition.is_placeholder:
            self._window._show_placeholder_command(definition.display_name, definition.unavailable_reason or "This formal capability is not available yet.")
            return
        try:
            definition.trigger(self._window)
        except Exception as error:  # noqa: BLE001
            self._window._handle_error(definition.display_name, error)

    def _build_actions(self) -> dict[str, QAction]:
        actions: dict[str, QAction] = {}
        for definition in COMMAND_DEFINITIONS:
            action = QAction(self._icons[definition.icon_key], definition.display_name, self._window)
            action.setObjectName(f"GuiCommand.{definition.command_id}")
            action.setProperty("command_id", definition.command_id)
            action.setData(definition.command_id)
            if definition.shortcut is not None:
                action.setShortcut(QKeySequence(definition.shortcut))
            action.triggered.connect(lambda _checked=False, command_id=definition.command_id: self.trigger(command_id))
            actions[definition.command_id] = action
        return actions
