"""定义 pyFEM 正式主线使用的 INP exporter。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pyfem.foundation.errors import ModelValidationError
from pyfem.gui.model_edit_capabilities import (
    collect_export_capability_issues,
    normalize_load_type,
    normalize_material_type,
    normalize_step_type,
)
from pyfem.mesh import Mesh, Part, RigidTransform
from pyfem.modeldb import (
    BoundaryDef,
    DistributedLoadDef,
    MaterialDef,
    ModelDB,
    NodalLoadDef,
    OutputRequest,
    RawKeywordBlockDef,
    SectionDef,
    StepDef,
)


@dataclass(slots=True, frozen=True)
class InpExportResult:
    """描述一次 INP 导出的结果。"""

    path: Path | None
    model_name: str
    line_count: int
    text: str


class InpExporter:
    """负责将正式支持子集的 ModelDB 稳定导出为 INP。"""

    def export(self, model: ModelDB, path: str | Path) -> Path:
        """导出模型到指定路径。"""

        result = self.export_text(model)
        resolved_path = Path(path)
        resolved_path.parent.mkdir(parents=True, exist_ok=True)
        resolved_path.write_text(result.text, encoding="utf-8")
        return resolved_path

    def export_text(self, model: ModelDB) -> InpExportResult:
        """导出模型为 INP 文本。"""

        model.validate()
        issues = collect_export_capability_issues(model)
        fail_fast_messages = [issue.message for issue in issues if issue.severity == "fail_fast"]
        if fail_fast_messages:
            raise ModelValidationError("\n".join(fail_fast_messages))

        lines: list[str] = []
        self._emit_heading(model, lines)
        self._emit_raw_blocks(model, lines, placement="before_parts")
        for part in model.parts.values():
            self._emit_part(part, lines)
        self._emit_raw_blocks(model, lines, placement="before_materials")
        for material in model.materials.values():
            self._emit_material(material, lines)
        for section in model.sections.values():
            self._emit_section(section, lines)
        for boundary in model.boundaries.values():
            self._emit_boundary_definition(boundary, lines)
        for load in model.nodal_loads.values():
            self._emit_nodal_load_definition(load, lines)
        for load in model.distributed_loads.values():
            self._emit_distributed_load_definition(load, lines)
        for request in model.output_requests.values():
            self._emit_output_request_definition(request, lines)
        self._emit_raw_blocks(model, lines, placement="before_steps")
        if model.assembly is not None:
            self._emit_assembly(model, lines)
        for step in model.steps.values():
            self._emit_step(step, model, lines)
        if model.job is not None:
            self._emit_job(model, lines)
        self._emit_raw_blocks(model, lines, placement="after_model")
        text = "\n".join(lines).rstrip() + "\n"
        return InpExportResult(path=None, model_name=model.name, line_count=len(lines), text=text)

    def _emit_heading(self, model: ModelDB, lines: list[str]) -> None:
        lines.append("*Heading")
        description = model.metadata.description.strip()
        if description:
            lines.extend(description.splitlines())
        else:
            lines.append(f"pyFEM exported model: {model.name}")

    def _emit_part(self, part: Part, lines: list[str]) -> None:
        lines.append(f"*Part, name={part.name}")
        self._emit_mesh(part.mesh, lines)
        lines.append("*End Part")

    def _emit_mesh(self, mesh: Mesh, lines: list[str]) -> None:
        lines.append("*Node")
        for node in mesh.nodes.values():
            coordinate_text = ", ".join(self._format_number(value) for value in node.coordinates)
            lines.append(f"{node.name}, {coordinate_text}")

        for element in mesh.elements.values():
            options = [f"type={element.type_key}"]
            if element.orientation_name:
                options.append(f"orientation={element.orientation_name}")
            lines.append(f"*Element, {', '.join(options)}")
            lines.append(f"{element.name}, {', '.join(element.node_names)}")

        for set_name, node_names in mesh.node_sets.items():
            lines.append(f"*Nset, nset={set_name}")
            lines.extend(self._chunk_csv(node_names))

        for set_name, element_names in mesh.element_sets.items():
            lines.append(f"*Elset, elset={set_name}")
            lines.extend(self._chunk_csv(element_names))

        for orientation in mesh.orientations.values():
            lines.append(f"*Orientation, name={orientation.name}, system={orientation.system}")
            values = tuple(orientation.axis_1) + tuple(orientation.axis_2)
            lines.append(", ".join(self._format_number(value) for value in values))

        for surface in mesh.surfaces.values():
            lines.append(f"*Surface, type=ELEMENT, name={surface.name}")
            for facet in surface.facets:
                lines.append(f"{facet.element_name}, {facet.local_face}")

    def _emit_material(self, material: MaterialDef, lines: list[str]) -> None:
        normalized_material_type = normalize_material_type(material.material_type)
        parameters = material.parameters
        lines.append(f"*Material, name={material.name}")
        lines.append("*Elastic")
        lines.append(
            f"{self._format_number(float(parameters['young_modulus']))}, "
            f"{self._format_number(float(parameters['poisson_ratio']))}"
        )
        if "density" in parameters:
            lines.append("*Density")
            lines.append(self._format_number(float(parameters["density"])))
        if normalized_material_type == "j2_plasticity":
            tangent_mode = str(parameters.get("tangent_mode", "consistent")).strip().lower()
            lines.append(f"*Plastic, model=J2, tangent_mode={tangent_mode}")
            lines.append(
                f"{self._format_number(float(parameters['yield_stress']))}, "
                f"{self._format_number(float(parameters.get('hardening_modulus', 0.0)))}"
            )

    def _emit_section(self, section: SectionDef, lines: list[str]) -> None:
        normalized_section_type = str(section.section_type).strip().lower()
        if normalized_section_type == "beam":
            option_items = [
                f"name={section.name}",
                f"elset={section.region_name}",
                f"material={section.material_name}",
            ]
            if section.scope_name is not None:
                option_items.append(f"scope={section.scope_name}")
            lines.append(f"*Beam Section, {', '.join(option_items)}")
            lines.append(
                ", ".join(
                    (
                        self._format_number(float(section.parameters["area"])),
                        self._format_number(float(section.parameters["moment_inertia_z"])),
                        self._format_number(float(section.parameters.get("shear_factor", 1.0))),
                    )
                )
            )
            return

        option_items = [
            f"name={section.name}",
            f"elset={section.region_name}",
            f"material={section.material_name}",
            f"formulation={normalized_section_type}",
        ]
        if section.scope_name is not None:
            option_items.append(f"scope={section.scope_name}")
        lines.append(f"*Solid Section, {', '.join(option_items)}")
        if "thickness" in section.parameters:
            lines.append(self._format_number(float(section.parameters["thickness"])))
        else:
            lines.append(",")

    def _emit_boundary_definition(self, boundary: BoundaryDef, lines: list[str]) -> None:
        option_items = [
            f"name={boundary.name}",
            f"target={boundary.target_name}",
            f"target_type={boundary.target_type}",
            f"boundary_type={boundary.boundary_type}",
        ]
        if boundary.scope_name is not None:
            option_items.append(f"scope={boundary.scope_name}")
        lines.append(f"*Boundary, {', '.join(option_items)}")
        for dof_name, value in boundary.dof_values.items():
            lines.append(f"{dof_name}, {self._format_number(value)}")

    def _emit_nodal_load_definition(self, load: NodalLoadDef, lines: list[str]) -> None:
        option_items = [
            f"name={load.name}",
            f"target={load.target_name}",
            f"target_type={load.target_type}",
        ]
        if load.scope_name is not None:
            option_items.append(f"scope={load.scope_name}")
        lines.append(f"*Cload, {', '.join(option_items)}")
        for component_name, value in load.components.items():
            lines.append(f"{component_name}, {self._format_number(value)}")

    def _emit_distributed_load_definition(self, load: DistributedLoadDef, lines: list[str]) -> None:
        option_items = [
            f"name={load.name}",
            f"target={load.target_name}",
            f"target_type={load.target_type}",
            f"load_type={normalize_load_type(load.load_type)}",
        ]
        if load.scope_name is not None:
            option_items.append(f"scope={load.scope_name}")
        lines.append(f"*Dsload, {', '.join(option_items)}")
        for component_name, value in load.components.items():
            lines.append(f"{component_name}, {self._format_number(value)}")

    def _emit_output_request_definition(self, request: OutputRequest, lines: list[str]) -> None:
        request_mode = str(request.parameters.get("request_mode", self._infer_request_mode(request.position))).strip().lower()
        option_items = [
            f"name={request.name}",
            f"request_mode={request_mode}",
            f"target_type={request.target_type}",
            f"position={str(request.position).strip().upper()}",
            f"frequency={int(request.frequency)}",
        ]
        if request.target_name is not None:
            option_items.append(f"target={request.target_name}")
        if request.scope_name is not None:
            option_items.append(f"scope={request.scope_name}")
        lines.append(f"*Output Request, {', '.join(option_items)}")
        lines.append(", ".join(str(variable).upper() for variable in request.variables))

    def _emit_assembly(self, model: ModelDB, lines: list[str]) -> None:
        assembly = model.assembly
        if assembly is None:
            return
        lines.append(f"*Assembly, name={assembly.name}")
        for instance in assembly.instances.values():
            lines.append(f"*Instance, name={instance.name}, part={instance.part_name}")
            self._emit_transform(instance.transform, model.parts[instance.part_name], lines)
            lines.append("*End Instance")
        self._emit_assembly_overlays(model, lines)
        lines.append("*End Assembly")

    def _emit_assembly_overlays(self, model: ModelDB, lines: list[str]) -> None:
        assembly = model.assembly
        if assembly is None:
            return

        for instance_name in assembly.instances:
            for set_name, node_names in assembly.node_sets_for_instance(instance_name).items():
                lines.append(f"*Nset, nset={set_name}, instance={instance_name}")
                lines.extend(self._chunk_csv(node_names))

            for set_name, element_names in assembly.element_sets_for_instance(instance_name).items():
                lines.append(f"*Elset, elset={set_name}, instance={instance_name}")
                lines.extend(self._chunk_csv(element_names))

            for surface in assembly.surfaces_for_instance(instance_name).values():
                lines.append(f"*Surface, type=ELEMENT, name={surface.name}")
                for facet in surface.facets:
                    lines.append(f"{instance_name}.{facet.element_name}, {facet.local_face}")

    def _emit_transform(self, transform: RigidTransform, part: Part, lines: list[str]) -> None:
        dimension = part.spatial_dimension()
        resolved_rotation, resolved_translation = transform.resolve_components(dimension)
        is_identity_rotation = all(
            abs(value - (1.0 if row_index == column_index else 0.0)) <= 1.0e-12
            for row_index, row in enumerate(resolved_rotation)
            for column_index, value in enumerate(row)
        )
        is_zero_translation = all(abs(value) <= 1.0e-12 for value in resolved_translation)
        if is_identity_rotation and is_zero_translation:
            return
        if is_identity_rotation:
            lines.append(", ".join(self._format_number(value) for value in resolved_translation))
            return
        for row in resolved_rotation:
            lines.append(", ".join(self._format_number(value) for value in row))
        lines.append(", ".join(self._format_number(value) for value in resolved_translation))

    def _emit_step(self, step: StepDef, model: ModelDB, lines: list[str]) -> None:
        lines.append(f"*Step, name={step.name}")
        normalized_step_type = normalize_step_type(step.procedure_type)
        if normalized_step_type == "static_linear":
            lines.append("*Static")
            consumed_parameter_names: set[str] = set()
        elif normalized_step_type == "static_nonlinear":
            option_items = []
            consumed_parameter_names = set()
            for key in (
                "nlgeom",
                "initial_increment",
                "max_increments",
                "min_increment",
                "max_iterations",
                "residual_tolerance",
                "displacement_tolerance",
                "allow_cutback",
                "line_search",
            ):
                if key in step.parameters:
                    option_items.append(f"{key}={self._format_option_value(step.parameters[key])}")
                    consumed_parameter_names.add(key)
            option_suffix = "" if not option_items else f", {', '.join(option_items)}"
            lines.append(f"*Static Nonlinear{option_suffix}")
        elif normalized_step_type == "modal":
            option_suffix = ""
            consumed_parameter_names = set()
            if "num_modes" in step.parameters:
                option_suffix = f", num_modes={int(step.parameters['num_modes'])}"
                consumed_parameter_names.add("num_modes")
            lines.append(f"*Frequency{option_suffix}")
        elif normalized_step_type == "implicit_dynamic":
            option_items = []
            consumed_parameter_names = set()
            for key in ("time_step", "total_time", "beta", "gamma"):
                if key in step.parameters:
                    option_items.append(f"{key}={self._format_option_value(step.parameters[key])}")
                    consumed_parameter_names.add(key)
            option_suffix = "" if not option_items else f", {', '.join(option_items)}"
            lines.append(f"*Dynamic{option_suffix}")
        else:
            raise ModelValidationError(f"分析步骤 {step.name} 的 procedure_type={step.procedure_type} 当前无法导出。")

        self._emit_raw_blocks(model, lines, placement="step_start", step_name=step.name)
        self._emit_step_parameter_blocks(step, lines, consumed_parameter_names=consumed_parameter_names)
        self._emit_step_references("Boundary Ref", step.boundary_names, lines)
        self._emit_step_references("Cload Ref", step.nodal_load_names, lines)
        self._emit_step_references("Dsload Ref", step.distributed_load_names, lines)
        self._emit_step_references("Output Request Ref", step.output_request_names, lines)
        self._emit_raw_blocks(model, lines, placement="step_end", step_name=step.name)
        lines.append("*End Step")

    def _emit_job(self, model: ModelDB, lines: list[str]) -> None:
        if model.job is None:
            return
        lines.append(f"*Job, name={model.job.name}")
        lines.extend(model.job.step_names)

    def _emit_step_references(self, keyword_name: str, names: tuple[str, ...], lines: list[str]) -> None:
        if not names:
            return
        lines.append(f"*{keyword_name}")
        lines.extend(names)

    def _emit_step_parameter_blocks(
        self,
        step: StepDef,
        lines: list[str],
        *,
        consumed_parameter_names: set[str],
    ) -> None:
        for parameter_name, parameter_value in step.parameters.items():
            if parameter_name in consumed_parameter_names:
                continue
            value_kind, text_value = self._serialize_step_parameter_value(parameter_value)
            lines.append(f"*Step Parameter, key={parameter_name}, value_kind={value_kind}")
            lines.extend(text_value.splitlines() or ("",))

    def _emit_raw_blocks(
        self,
        model: ModelDB,
        lines: list[str],
        *,
        placement: str,
        step_name: str | None = None,
    ) -> None:
        blocks = [
            block
            for block in model.raw_keyword_blocks.values()
            if block.placement == placement and block.step_name == step_name
        ]
        for block in sorted(blocks, key=lambda item: (item.order, item.name)):
            self._emit_raw_block(block, lines)

    def _emit_raw_block(self, block: RawKeywordBlockDef, lines: list[str]) -> None:
        option_items = [
            f"name={block.name}",
            f"keyword={block.keyword}",
            f"placement={block.placement}",
            f"order={block.order}",
        ]
        if block.step_name is not None:
            option_items.append(f"step={block.step_name}")
        if block.description:
            option_items.append(f"description={block.description}")
        for option_name, option_value in block.options.items():
            option_items.append(f"raw_{option_name}={option_value}")
        lines.append(f"*Raw Keyword, {', '.join(option_items)}")
        lines.extend(block.data_lines)

    def _chunk_csv(self, values: tuple[str, ...], chunk_size: int = 16) -> tuple[str, ...]:
        rows: list[str] = []
        for start in range(0, len(values), chunk_size):
            rows.append(", ".join(values[start : start + chunk_size]))
        return tuple(rows)

    def _format_option_value(self, value: object) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return self._format_number(float(value))
        return str(value)

    def _format_number(self, value: float) -> str:
        return f"{float(value):.12g}"

    def _infer_request_mode(self, position: str) -> str:
        return "history" if str(position).strip().upper() == "GLOBAL_HISTORY" else "field"

    def _serialize_step_parameter_value(self, value: object) -> tuple[str, str]:
        if isinstance(value, bool):
            return "boolean", "true" if value else "false"
        if isinstance(value, int):
            return "integer", str(value)
        if isinstance(value, float):
            return "number", self._format_number(value)
        if isinstance(value, (dict, list, tuple)):
            return "json", json.dumps(value, ensure_ascii=False, indent=2)
        return "text", str(value)
