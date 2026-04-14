"""Abaqus 风格 INP 的基础解析与翻译。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pyfem.foundation.errors import ModelValidationError
from pyfem.mesh import Assembly, ElementRecord, Mesh, NodeRecord, Orientation, Part, PartInstance, RigidTransform, Surface, SurfaceFacet
from pyfem.modeldb import (
    BoundaryDef,
    CompilationScope,
    DistributedLoadDef,
    JobDef,
    MaterialDef,
    ModelDB,
    NodalLoadDef,
    OutputRequest,
    RawKeywordBlockDef,
    SectionDef,
    StepDef,
)


@dataclass(slots=True, frozen=True)
class InpKeyword:
    """定义一个 INP 关键字块。"""

    name: str
    options: dict[str, str] = field(default_factory=dict)
    data_lines: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class InpDocument:
    """定义解析后的 INP 文档。"""

    keywords: tuple[InpKeyword, ...]
    source_name: str = "<memory>"


class InpParser:
    """负责将 INP 文本解析为关键字文档。"""

    def parse_text(self, text: str, source_name: str = "<memory>") -> InpDocument:
        """从文本解析 INP 文档。"""

        keywords: list[InpKeyword] = []
        current_name: str | None = None
        current_options: dict[str, str] = {}
        current_data_lines: list[str] = []

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("**"):
                continue
            if line.startswith("*"):
                if current_name is not None:
                    keywords.append(
                        InpKeyword(name=current_name, options=dict(current_options), data_lines=tuple(current_data_lines))
                    )
                current_name, current_options = self._parse_keyword_line(line)
                current_data_lines = []
                continue
            current_data_lines.append(line)

        if current_name is not None:
            keywords.append(InpKeyword(name=current_name, options=dict(current_options), data_lines=tuple(current_data_lines)))
        return InpDocument(keywords=tuple(keywords), source_name=source_name)

    def parse_file(self, path: str | Path) -> InpDocument:
        """从文件解析 INP 文档。"""

        target_path = Path(path)
        return self.parse_text(target_path.read_text(encoding="utf-8"), source_name=target_path.name)

    def _parse_keyword_line(self, line: str) -> tuple[str, dict[str, str]]:
        parts = [item.strip() for item in line[1:].split(",")]
        name = parts[0].upper()
        options: dict[str, str] = {}
        for option in parts[1:]:
            if not option:
                continue
            if "=" in option:
                key, value = option.split("=", 1)
                options[key.strip().lower()] = value.strip()
            else:
                options[option.strip().lower()] = "true"
        return name, options


class InpTranslator:
    """负责将 INP 文档翻译为 ModelDB。"""

    def translate(self, document: InpDocument, model_name: str | None = None) -> ModelDB:
        """将 INP 文档翻译为模型数据库。"""

        model = ModelDB(name=document.source_name if model_name is None else model_name)
        current_material: MaterialDef | None = None
        default_part: Part | None = None
        translated_section_names: list[str] = []
        global_boundary_names: list[str] = []
        global_load_names: list[str] = []
        step_count = 0
        boundary_count = 0
        load_count = 0
        output_count = 0
        keyword_index = 0

        while keyword_index < len(document.keywords):
            keyword = document.keywords[keyword_index]
            if keyword.name == "HEADING":
                model.metadata.description = "\n".join(keyword.data_lines)
            elif keyword.name == "PREPRINT":
                pass
            elif keyword.name == "SYSTEM":
                self._translate_system_keyword(keyword)
            elif keyword.name == "PART":
                section_names, next_index = self._translate_part_block(document=document, start_index=keyword_index, model=model)
                translated_section_names.extend(section_names)
                keyword_index = next_index
                continue
            elif keyword.name == "ASSEMBLY":
                next_index = self._translate_assembly_block(document=document, start_index=keyword_index, model=model)
                for section_name in translated_section_names:
                    model.sections[section_name].scope_name = None
                keyword_index = next_index
                continue
            elif keyword.name == "NODE":
                default_part = self._ensure_legacy_part(model, default_part)
                self._translate_nodes(keyword, default_part)
            elif keyword.name == "ELEMENT":
                default_part = self._ensure_legacy_part(model, default_part)
                self._translate_elements(keyword, default_part)
            elif keyword.name == "NSET":
                default_part = self._ensure_legacy_part(model, default_part)
                self._translate_node_set(keyword, default_part)
            elif keyword.name == "ELSET":
                default_part = self._ensure_legacy_part(model, default_part)
                self._translate_element_set(keyword, default_part)
            elif keyword.name == "MATERIAL":
                current_material = MaterialDef(name=keyword.options["name"], material_type="linear_elastic")
                model.add_material(current_material)
            elif keyword.name == "ELASTIC":
                if current_material is None:
                    raise ModelValidationError("ELASTIC 关键字缺少前置 MATERIAL 定义。")
                values = self._parse_float_line(keyword.data_lines[0])
                current_material.parameters["young_modulus"] = values[0]
                current_material.parameters["poisson_ratio"] = values[1]
            elif keyword.name == "PLASTIC":
                if current_material is None:
                    raise ModelValidationError("PLASTIC 关键字缺少前置 MATERIAL 定义。")
                current_material.material_type = "j2_plasticity"
                values = self._parse_float_line(keyword.data_lines[0])
                current_material.parameters["yield_stress"] = values[0]
                current_material.parameters["hardening_modulus"] = 0.0 if len(values) < 2 else values[1]
                if "tangent_mode" in keyword.options:
                    current_material.parameters["tangent_mode"] = keyword.options["tangent_mode"]
            elif keyword.name == "DENSITY":
                if current_material is None:
                    raise ModelValidationError("DENSITY 关键字缺少前置 MATERIAL 定义。")
                current_material.parameters["density"] = self._parse_float_line(keyword.data_lines[0])[0]
            elif keyword.name == "SOLID SECTION":
                default_part = self._ensure_legacy_part(
                    model,
                    default_part,
                    preferred_part_name=self._read_optional_text(keyword.options.get("scope")),
                )
                section = self._translate_solid_section(
                    keyword,
                    default_part,
                    scope_name=None if model.assembly is not None else default_part.name,
                    section_name=f"section-{keyword.options['elset']}",
                )
                model.add_section(section)
                translated_section_names.append(section.name)
            elif keyword.name == "BEAM SECTION":
                default_part = self._ensure_legacy_part(
                    model,
                    default_part,
                    preferred_part_name=self._read_optional_text(keyword.options.get("scope")),
                )
                section = self._translate_beam_section(
                    keyword,
                    scope_name=None if model.assembly is not None else default_part.name,
                    section_name=f"section-{keyword.options['elset']}",
                )
                model.add_section(section)
                translated_section_names.append(section.name)
            elif keyword.name == "SURFACE":
                default_part = self._ensure_legacy_part(model, default_part)
                self._translate_surface(keyword, default_part)
            elif keyword.name == "ORIENTATION":
                default_part = self._ensure_legacy_part(model, default_part)
                self._translate_orientation(keyword, default_part)
            elif keyword.name == "BOUNDARY":
                if self._is_structured_definition(keyword):
                    boundary = self._translate_named_boundary_definition(keyword)
                    model.add_boundary(boundary)
                else:
                    generated_names = self._translate_boundary_block(model, default_part, keyword, prefix="global", start_index=boundary_count)
                    global_boundary_names.extend(generated_names)
                    boundary_count += len(generated_names)
            elif keyword.name == "CLOAD":
                if self._is_structured_definition(keyword):
                    load = self._translate_named_nodal_load_definition(keyword)
                    model.add_nodal_load(load)
                else:
                    generated_names = self._translate_cload_block(model, default_part, keyword, prefix="global", start_index=load_count)
                    global_load_names.extend(generated_names)
                    load_count += len(generated_names)
            elif keyword.name == "DSLOAD":
                if self._is_structured_definition(keyword):
                    load = self._translate_named_distributed_load_definition(keyword)
                    model.add_distributed_load(load)
                else:
                    raise ModelValidationError("顶层 DSLOAD 当前仅支持结构化定义形式。")
            elif keyword.name == "OUTPUT REQUEST":
                model.add_output_request(self._translate_output_request_definition(keyword))
            elif keyword.name == "RAW KEYWORD":
                model.add_raw_keyword_block(self._translate_raw_keyword_block(keyword))
            elif keyword.name == "JOB":
                model.set_job(self._translate_job_definition(keyword))
            elif keyword.name == "STEP":
                step_count += 1
                step_definition, next_index, boundary_count, load_count, output_count = self._translate_step_block(
                    document=document,
                    start_index=keyword_index,
                    model=model,
                    default_part=default_part,
                    step_index=step_count,
                    boundary_start=boundary_count,
                    load_start=load_count,
                    output_start=output_count,
                    inherited_boundary_names=tuple(global_boundary_names),
                    inherited_load_names=tuple(global_load_names),
                )
                model.add_step(step_definition)
                keyword_index = next_index
                continue
            elif keyword.name in {"END PART", "END ASSEMBLY", "END INSTANCE"}:
                raise ModelValidationError(f"关键字 {keyword.name} 出现在非法位置。")
            else:
                raise ModelValidationError(f"当前不支持顶层关键字 {keyword.name}。")
            keyword_index += 1

        if model_name is None:
            exported_model_name = self._read_exported_model_name(model.metadata.description)
            if exported_model_name is not None:
                model.name = exported_model_name

        if model.job is None and model.steps:
            model.set_job(JobDef(name=f"{model.name}-job", step_names=tuple(model.steps.keys())))
        model.validate()
        return model

    def _ensure_legacy_part(
        self,
        model: ModelDB,
        default_part: Part | None,
        *,
        preferred_part_name: str | None = None,
    ) -> Part:
        if default_part is not None:
            return default_part
        if preferred_part_name is not None:
            preferred_part = model.parts.get(preferred_part_name)
            if preferred_part is not None:
                return preferred_part
        if len(model.parts) == 1:
            return next(iter(model.parts.values()))
        if model.parts:
            raise ModelValidationError("当前输入同时包含多个部件，旧式关键字缺少明确 scope，无法安全推断所属部件。")
        part = Part(name="part-1", mesh=Mesh())
        model.add_part(part)
        return part

    def _translate_part_block(
        self,
        document: InpDocument,
        start_index: int,
        model: ModelDB,
    ) -> tuple[tuple[str, ...], int]:
        part_keyword = document.keywords[start_index]
        part = Part(name=part_keyword.options["name"], mesh=Mesh())
        model.add_part(part)
        translated_section_names: list[str] = []
        keyword_index = start_index + 1

        while keyword_index < len(document.keywords):
            keyword = document.keywords[keyword_index]
            if keyword.name == "END PART":
                return tuple(translated_section_names), keyword_index + 1
            if keyword.name == "NODE":
                self._translate_nodes(keyword, part)
            elif keyword.name == "SYSTEM":
                self._translate_system_keyword(keyword)
            elif keyword.name == "ELEMENT":
                self._translate_elements(keyword, part)
            elif keyword.name == "NSET":
                self._translate_node_set(keyword, part)
            elif keyword.name == "ELSET":
                self._translate_element_set(keyword, part)
            elif keyword.name == "SURFACE":
                self._translate_surface(keyword, part)
            elif keyword.name == "ORIENTATION":
                self._translate_orientation(keyword, part)
            elif keyword.name == "SOLID SECTION":
                section = self._translate_solid_section(
                    keyword,
                    part,
                    scope_name=part.name,
                    section_name=f"section-{part.name}-{keyword.options['elset']}",
                )
                model.add_section(section)
                translated_section_names.append(section.name)
            elif keyword.name == "BEAM SECTION":
                section = self._translate_beam_section(
                    keyword,
                    scope_name=part.name,
                    section_name=f"section-{part.name}-{keyword.options['elset']}",
                )
                model.add_section(section)
                translated_section_names.append(section.name)
            else:
                raise ModelValidationError(f"PART 块当前不支持关键字 {keyword.name}。")
            keyword_index += 1

        raise ModelValidationError(f"部件 {part.name} 缺少 END PART。")

    def _translate_system_keyword(self, keyword: InpKeyword) -> None:
        """处理 SYSTEM 控制关键字。"""

        if not keyword.data_lines:
            return
        raise ModelValidationError("当前仅支持空的 SYSTEM 关键字；带坐标变换定义的 SYSTEM 尚未纳入正式 importer 主线。")

    def _translate_restart_keyword(self, keyword: InpKeyword) -> None:
        """处理 RESTART 控制关键字。"""

        if keyword.data_lines:
            raise ModelValidationError("当前仅支持不带数据行的 RESTART 控制关键字。")

    def _translate_abaqus_output_keyword(self, keyword: InpKeyword) -> None:
        """处理 Abaqus 风格 OUTPUT 控制关键字。"""

        variable_name = str(keyword.options.get("variable", "")).strip().upper()
        if variable_name == "PRESELECT" and not keyword.data_lines:
            return
        raise ModelValidationError("当前仅支持 variable=PRESELECT 且不带数据行的 Abaqus OUTPUT 控制关键字。")

    def _translate_assembly_block(
        self,
        document: InpDocument,
        start_index: int,
        model: ModelDB,
    ) -> int:
        if model.assembly is not None:
            raise ModelValidationError("当前一个模型仅支持一个 ASSEMBLY 块。")

        assembly_keyword = document.keywords[start_index]
        assembly = Assembly(name=assembly_keyword.options.get("name", "assembly-1"))
        keyword_index = start_index + 1

        while keyword_index < len(document.keywords):
            keyword = document.keywords[keyword_index]
            if keyword.name == "END ASSEMBLY":
                model.set_assembly(assembly)
                return keyword_index + 1
            if keyword.name == "INSTANCE":
                assembly.add_instance(self._translate_instance(keyword, model))
                keyword_index += 1
                if keyword_index >= len(document.keywords) or document.keywords[keyword_index].name != "END INSTANCE":
                    raise ModelValidationError(f"实例 {keyword.options.get('name', '<unknown>')} 缺少 END INSTANCE。")
                keyword_index += 1
                continue
            if keyword.name == "NSET":
                self._translate_assembly_node_set(keyword, assembly, model)
            elif keyword.name == "ELSET":
                self._translate_assembly_element_set(keyword, assembly, model)
            elif keyword.name == "SURFACE":
                self._translate_assembly_surface(keyword, assembly, model)
            else:
                raise ModelValidationError(f"ASSEMBLY 块当前仅支持 INSTANCE/NSET/ELSET/SURFACE，收到 {keyword.name}。")
            keyword_index += 1

        raise ModelValidationError(f"装配 {assembly.name} 缺少 END ASSEMBLY。")

    def _translate_instance(self, keyword: InpKeyword, model: ModelDB) -> PartInstance:
        part_name = keyword.options["part"]
        instance_name = keyword.options["name"]
        part = model.get_part(part_name)
        transform = self._parse_instance_transform(keyword.data_lines, part.spatial_dimension())
        return PartInstance(name=instance_name, part_name=part_name, transform=transform)

    def _translate_assembly_node_set(self, keyword: InpKeyword, assembly: Assembly, model: ModelDB) -> None:
        instance_name, _part = self._resolve_assembly_instance(keyword, assembly, model)
        assembly.add_instance_node_set(instance_name, keyword.options["nset"], self._parse_set_members(keyword))

    def _translate_assembly_element_set(self, keyword: InpKeyword, assembly: Assembly, model: ModelDB) -> None:
        instance_name, _part = self._resolve_assembly_instance(keyword, assembly, model)
        assembly.add_instance_element_set(instance_name, keyword.options["elset"], self._parse_set_members(keyword))

    def _translate_assembly_surface(self, keyword: InpKeyword, assembly: Assembly, model: ModelDB) -> None:
        surface_type = keyword.options.get("type", "ELEMENT").upper()
        if surface_type != "ELEMENT":
            raise ModelValidationError(f"当前仅支持 ELEMENT 类型装配表面，收到 {surface_type}。")

        surface_name = keyword.options["name"]
        resolved_instance_name: str | None = None
        facets: list[SurfaceFacet] = []
        for data_line in keyword.data_lines:
            items = [item.strip() for item in data_line.split(",") if item.strip()]
            if len(items) < 2:
                raise ModelValidationError(f"装配表面 {surface_name} 的定义行至少需要给出区域名和局部面标签。")
            instance_name, element_names = self._resolve_assembly_surface_region(
                assembly=assembly,
                model=model,
                region_name=items[0],
            )
            if resolved_instance_name is None:
                resolved_instance_name = instance_name
            elif resolved_instance_name != instance_name:
                raise ModelValidationError(
                    f"装配表面 {surface_name} 当前仅支持绑定单个实例，收到 {resolved_instance_name} 与 {instance_name}。"
                )
            local_face = items[1].upper()
            facets.extend(SurfaceFacet(element_name=element_name, local_face=local_face) for element_name in element_names)

        if resolved_instance_name is None:
            raise ModelValidationError(f"装配表面 {surface_name} 缺少有效定义行。")
        assembly.add_instance_surface(resolved_instance_name, Surface(name=surface_name, facets=tuple(facets)))

    def _resolve_assembly_instance(self, keyword: InpKeyword, assembly: Assembly, model: ModelDB) -> tuple[str, Part]:
        instance_name = self._read_optional_text(keyword.options.get("instance"))
        if instance_name is None:
            raise ModelValidationError(f"ASSEMBLY 中的 {keyword.name} 当前必须显式给出 instance=。")
        try:
            instance = assembly.instances[instance_name]
        except KeyError as error:
            raise ModelValidationError(f"装配 {assembly.name} 中不存在实例 {instance_name}。") from error
        return instance_name, model.get_part(instance.part_name)

    def _resolve_assembly_surface_region(
        self,
        *,
        assembly: Assembly,
        model: ModelDB,
        region_name: str,
    ) -> tuple[str, tuple[str, ...]]:
        normalized_name = region_name.strip()
        if "." in normalized_name:
            scope_name, target_name = normalized_name.split(".", 1)
            try:
                instance = assembly.instances[scope_name]
            except KeyError as error:
                raise ModelValidationError(f"装配表面区域 {normalized_name} 引用了不存在的实例 {scope_name}。") from error
            part = model.get_part(instance.part_name)
            if target_name in assembly.element_sets_for_instance(scope_name):
                return scope_name, assembly.element_sets_for_instance(scope_name)[target_name]
            if target_name in part.mesh.element_sets:
                return scope_name, part.mesh.element_sets[target_name]
            if target_name in part.elements:
                return scope_name, (target_name,)
            raise ModelValidationError(f"装配表面区域 {normalized_name} 引用了不存在的单元区域 {target_name}。")

        matches: list[tuple[str, tuple[str, ...]]] = []
        for instance_name, instance in assembly.instances.items():
            element_sets = assembly.element_sets_for_instance(instance_name)
            if normalized_name in element_sets:
                matches.append((instance_name, element_sets[normalized_name]))

        if not matches:
            raise ModelValidationError(f"装配表面区域 {normalized_name} 未找到对应的实例级单元集合。")
        if len(matches) > 1:
            scopes = ", ".join(instance_name for instance_name, _ in matches)
            raise ModelValidationError(f"装配表面区域 {normalized_name} 同时出现在多个实例中: {scopes}。")
        return matches[0]

    def _parse_instance_transform(self, data_lines: tuple[str, ...], dimension: int) -> RigidTransform:
        if not data_lines:
            return RigidTransform()

        parsed_lines = [self._parse_float_line(data_line) for data_line in data_lines]
        if len(parsed_lines) == 1:
            translation = parsed_lines[0]
            if len(translation) != dimension:
                raise ModelValidationError(f"INSTANCE 平移向量维度必须等于部件维度 {dimension}。")
            return RigidTransform(translation=translation)

        if len(parsed_lines) == dimension + 1:
            rotation = tuple(parsed_lines[:dimension])
            translation = parsed_lines[-1]
            if any(len(row) != dimension for row in rotation):
                raise ModelValidationError("INSTANCE 旋转矩阵必须逐行给出方阵。")
            if len(translation) != dimension:
                raise ModelValidationError(f"INSTANCE 平移向量维度必须等于部件维度 {dimension}。")
            return RigidTransform(rotation=rotation, translation=translation)

        raise ModelValidationError(
            "当前 INSTANCE 仅支持三种形式: 无数据行表示恒等变换, 一行表示平移, 或按维度给出旋转矩阵加一行平移。"
        )

    def _translate_nodes(self, keyword: InpKeyword, part: Part) -> None:
        for data_line in keyword.data_lines:
            items = [item.strip() for item in data_line.split(",") if item.strip()]
            node_name = items[0]
            coordinates = tuple(float(value) for value in items[1:])
            part.add_node(NodeRecord(name=node_name, coordinates=coordinates))

    def _translate_elements(self, keyword: InpKeyword, part: Part) -> None:
        element_type = keyword.options["type"].upper()
        elset_name = keyword.options.get("elset")
        orientation_name = keyword.options.get("orientation")
        element_names: list[str] = []
        for data_line in keyword.data_lines:
            items = [item.strip() for item in data_line.split(",") if item.strip()]
            element_name = items[0]
            node_names = tuple(items[1:])
            part.add_element(
                ElementRecord(
                    name=element_name,
                    type_key=element_type,
                    node_names=node_names,
                    orientation_name=orientation_name,
                )
            )
            element_names.append(element_name)
        if elset_name is not None:
            part.add_element_set(elset_name, tuple(element_names))

    def _translate_node_set(self, keyword: InpKeyword, part: Part) -> None:
        set_name = keyword.options["nset"]
        node_names = self._parse_set_members(keyword)
        part.add_node_set(set_name, node_names)

    def _translate_element_set(self, keyword: InpKeyword, part: Part) -> None:
        set_name = keyword.options["elset"]
        element_names = self._parse_set_members(keyword)
        part.add_element_set(set_name, element_names)

    def _translate_orientation(self, keyword: InpKeyword, part: Part) -> None:
        values: list[float] = []
        for data_line in keyword.data_lines:
            values.extend(self._parse_float_line(data_line))
        if len(values) not in {4, 6}:
            raise ModelValidationError("ORIENTATION 当前仅支持一阶 rectangular 方向定义，需给出 axis_1 与 axis_2。")
        half = len(values) // 2
        part.add_orientation(
            Orientation(
                name=keyword.options["name"],
                system=keyword.options.get("system", "rectangular"),
                axis_1=tuple(values[:half]),
                axis_2=tuple(values[half:]),
            )
        )

    def _translate_solid_section(
        self,
        keyword: InpKeyword,
        part: Part,
        *,
        scope_name: str | None,
        section_name: str,
    ) -> SectionDef:
        region_name = keyword.options["elset"]
        material_name = keyword.options["material"]
        element_type = self._resolve_region_element_type(part, region_name)
        parameters: dict[str, Any] = {}
        resolved_scope_name = self._read_optional_text(keyword.options.get("scope"), default_value=scope_name)
        if keyword.data_lines:
            values = self._parse_float_line(keyword.data_lines[0])
            if values:
                parameters["thickness"] = values[0]
        section_type = keyword.options.get("formulation") or keyword.options.get("section_type")
        if section_type is not None:
            normalized_section_type = section_type.strip().lower()
        elif element_type == "C3D8":
            normalized_section_type = "solid"
        elif element_type == "CPS4":
            normalized_section_type = "plane_stress"
        else:
            normalized_section_type = element_type.lower()
        resolved_section_name = keyword.options.get("name", section_name)
        if normalized_section_type == "solid":
            return SectionDef(
                name=resolved_section_name,
                section_type="solid",
                material_name=material_name,
                region_name=region_name,
                scope_name=resolved_scope_name,
                parameters=parameters,
            )
        if normalized_section_type in {"plane_stress", "plane_strain"}:
            return SectionDef(
                name=resolved_section_name,
                section_type=normalized_section_type,
                material_name=material_name,
                region_name=region_name,
                scope_name=resolved_scope_name,
                parameters={"thickness": float(parameters.get("thickness", 1.0))},
            )
        raise ModelValidationError(
            f"SOLID SECTION 当前不支持区域 {region_name} 中的截面形式 {normalized_section_type} / 单元类型 {element_type}。"
        )

    def _translate_beam_section(
        self,
        keyword: InpKeyword,
        *,
        scope_name: str | None,
        section_name: str,
    ) -> SectionDef:
        region_name = keyword.options["elset"]
        material_name = keyword.options["material"]
        values = self._parse_float_line(keyword.data_lines[0]) if keyword.data_lines else (1.0, 1.0)
        resolved_scope_name = self._read_optional_text(keyword.options.get("scope"), default_value=scope_name)
        return SectionDef(
            name=keyword.options.get("name", section_name),
            section_type="beam",
            material_name=material_name,
            region_name=region_name,
            scope_name=resolved_scope_name,
            parameters={
                "area": values[0],
                "moment_inertia_z": values[1],
                "shear_factor": 1.0 if len(values) < 3 else values[2],
            },
        )

    def _translate_surface(self, keyword: InpKeyword, part: Part) -> None:
        surface_type = keyword.options.get("type", "ELEMENT").upper()
        if surface_type != "ELEMENT":
            raise ModelValidationError(f"当前仅支持 ELEMENT 类型表面，收到 {surface_type}。")

        surface_name = keyword.options["name"]
        facets: list[SurfaceFacet] = []
        for data_line in keyword.data_lines:
            items = [item.strip() for item in data_line.split(",") if item.strip()]
            if len(items) < 2:
                raise ModelValidationError(f"表面 {surface_name} 的定义行至少需要给出区域名和局部面标签。")
            region_name = items[0]
            local_face = items[1].upper()
            if region_name in part.mesh.element_sets:
                element_names = part.mesh.element_sets[region_name]
            elif region_name in part.elements:
                element_names = (region_name,)
            else:
                raise ModelValidationError(f"表面 {surface_name} 引用了不存在的区域 {region_name}。")
            facets.extend(SurfaceFacet(element_name=element_name, local_face=local_face) for element_name in element_names)

        part.add_surface(Surface(name=surface_name, facets=tuple(facets)))

    def _translate_step_block(
        self,
        document: InpDocument,
        start_index: int,
        model: ModelDB,
        default_part: Part | None,
        step_index: int,
        boundary_start: int,
        load_start: int,
        output_start: int,
        inherited_boundary_names: tuple[str, ...],
        inherited_load_names: tuple[str, ...],
    ) -> tuple[StepDef, int, int, int, int]:
        step_keyword = document.keywords[start_index]
        step_name = step_keyword.options.get("name", f"step-{step_index}")
        procedure_type = "static_linear"
        parameters: dict[str, Any] = {}
        boundary_names = list(inherited_boundary_names)
        load_names = list(inherited_load_names)
        distributed_load_names: list[str] = []
        explicit_output_names: list[str] = []
        keyword_index = start_index + 1

        while keyword_index < len(document.keywords):
            keyword = document.keywords[keyword_index]
            if keyword.name == "END STEP":
                break
            if keyword.name == "STATIC":
                procedure_type = "static_linear"
                parameters.update(self._translate_step_parameter_options(keyword))
            elif keyword.name == "STATIC NONLINEAR":
                procedure_type = "static_nonlinear"
                parameters.update(self._translate_step_parameter_options(keyword))
            elif keyword.name == "FREQUENCY":
                procedure_type = "modal"
                parameters.update(self._translate_frequency_parameters(keyword))
            elif keyword.name == "DYNAMIC":
                procedure_type = "implicit_dynamic"
                parameters.update(self._translate_dynamic_parameters(keyword))
            elif keyword.name == "BOUNDARY":
                if self._is_structured_definition(keyword):
                    boundary = self._translate_named_boundary_definition(keyword)
                    if boundary.name not in model.boundaries:
                        model.add_boundary(boundary)
                    boundary_names.append(boundary.name)
                else:
                    generated_names = self._translate_boundary_block(model, default_part, keyword, prefix=step_name, start_index=boundary_start)
                    boundary_names.extend(generated_names)
                    boundary_start += len(generated_names)
            elif keyword.name == "CLOAD":
                if self._is_structured_definition(keyword):
                    load = self._translate_named_nodal_load_definition(keyword)
                    if load.name not in model.nodal_loads:
                        model.add_nodal_load(load)
                    load_names.append(load.name)
                else:
                    generated_names = self._translate_cload_block(model, default_part, keyword, prefix=step_name, start_index=load_start)
                    load_names.extend(generated_names)
                    load_start += len(generated_names)
            elif keyword.name == "DSLOAD":
                if self._is_structured_definition(keyword):
                    load = self._translate_named_distributed_load_definition(keyword)
                    if load.name not in model.distributed_loads:
                        model.add_distributed_load(load)
                    distributed_load_names.append(load.name)
                else:
                    generated_names = self._translate_dsload_block(model, default_part, keyword, prefix=step_name, start_index=load_start)
                    distributed_load_names.extend(generated_names)
                    load_start += len(generated_names)
            elif keyword.name == "BOUNDARY REF":
                boundary_names.extend(self._parse_name_lines(keyword))
            elif keyword.name == "CLOAD REF":
                load_names.extend(self._parse_name_lines(keyword))
            elif keyword.name == "DSLOAD REF":
                distributed_load_names.extend(self._parse_name_lines(keyword))
            elif keyword.name == "OUTPUT REQUEST":
                request = self._translate_output_request_definition(keyword)
                if request.name not in model.output_requests:
                    model.add_output_request(request)
                explicit_output_names.append(request.name)
            elif keyword.name == "OUTPUT REQUEST REF":
                explicit_output_names.extend(self._parse_name_lines(keyword))
            elif keyword.name == "RESTART":
                self._translate_restart_keyword(keyword)
            elif keyword.name == "OUTPUT":
                self._translate_abaqus_output_keyword(keyword)
            elif keyword.name == "STEP PARAMETER":
                parameter_name, parameter_value = self._translate_step_parameter_block(keyword)
                parameters[parameter_name] = parameter_value
            elif keyword.name == "RAW KEYWORD":
                model.add_raw_keyword_block(self._translate_raw_keyword_block(keyword, default_step_name=step_name))
            else:
                raise ModelValidationError(f"STEP 块当前不支持关键字 {keyword.name}。")
            keyword_index += 1

        if explicit_output_names:
            output_names = tuple(dict.fromkeys(explicit_output_names))
        else:
            output_names = self._register_default_output_requests(
                model=model,
                procedure_type=procedure_type,
                start_index=output_start,
            )
            output_start += len(output_names)
        step_definition = StepDef(
            name=step_name,
            procedure_type=procedure_type,
            boundary_names=tuple(boundary_names),
            nodal_load_names=tuple(load_names),
            distributed_load_names=tuple(distributed_load_names),
            output_request_names=tuple(output_names),
            parameters=parameters,
        )
        return step_definition, keyword_index + 1, boundary_start, load_start, output_start

    def _is_structured_definition(self, keyword: InpKeyword) -> bool:
        return "target" in keyword.options and "name" in keyword.options

    def _translate_named_boundary_definition(self, keyword: InpKeyword) -> BoundaryDef:
        dof_values: dict[str, float] = {}
        for data_line in keyword.data_lines:
            items = [item.strip() for item in data_line.split(",") if item.strip()]
            if len(items) != 2:
                raise ModelValidationError("结构化 BOUNDARY 定义必须按 `DOF, VALUE` 书写。")
            dof_values[items[0].upper()] = float(items[1])
        return BoundaryDef(
            name=keyword.options["name"],
            target_name=keyword.options["target"],
            target_type=keyword.options.get("target_type", "node_set"),
            scope_name=self._read_optional_text(keyword.options.get("scope")),
            boundary_type=keyword.options.get("boundary_type", "displacement"),
            dof_values=dof_values,
        )

    def _translate_named_nodal_load_definition(self, keyword: InpKeyword) -> NodalLoadDef:
        components: dict[str, float] = {}
        for data_line in keyword.data_lines:
            items = [item.strip() for item in data_line.split(",") if item.strip()]
            if len(items) != 2:
                raise ModelValidationError("结构化 CLOAD 定义必须按 `COMPONENT, VALUE` 书写。")
            components[items[0].upper()] = float(items[1])
        return NodalLoadDef(
            name=keyword.options["name"],
            target_name=keyword.options["target"],
            target_type=keyword.options.get("target_type", "node_set"),
            scope_name=self._read_optional_text(keyword.options.get("scope")),
            components=components,
        )

    def _translate_named_distributed_load_definition(self, keyword: InpKeyword) -> DistributedLoadDef:
        components: dict[str, float] = {}
        for data_line in keyword.data_lines:
            items = [item.strip() for item in data_line.split(",") if item.strip()]
            if len(items) != 2:
                raise ModelValidationError("结构化 DSLOAD 定义必须按 `COMPONENT, VALUE` 书写。")
            components[items[0].upper()] = float(items[1])
        return DistributedLoadDef(
            name=keyword.options["name"],
            target_name=keyword.options["target"],
            target_type=keyword.options.get("target_type", "surface"),
            scope_name=self._read_optional_text(keyword.options.get("scope")),
            load_type=keyword.options.get("load_type", "pressure"),
            components=components,
        )

    def _translate_output_request_definition(self, keyword: InpKeyword) -> OutputRequest:
        variables: list[str] = []
        for data_line in keyword.data_lines:
            variables.extend(item.strip().upper() for item in data_line.split(",") if item.strip())
        return OutputRequest(
            name=keyword.options["name"],
            variables=tuple(variables),
            target_type=keyword.options.get("target_type", "model"),
            target_name=self._read_optional_text(keyword.options.get("target")),
            scope_name=self._read_optional_text(keyword.options.get("scope")),
            position=keyword.options.get("position", "NODE").upper(),
            frequency=int(keyword.options.get("frequency", "1")),
            parameters={
                "request_mode": keyword.options.get("request_mode", self._infer_request_mode(keyword.options.get("position", "NODE"))),
            },
        )

    def _translate_raw_keyword_block(
        self,
        keyword: InpKeyword,
        *,
        default_step_name: str | None = None,
    ) -> RawKeywordBlockDef:
        raw_options = {
            option_name.removeprefix("raw_"): option_value
            for option_name, option_value in keyword.options.items()
            if option_name.startswith("raw_")
        }
        return RawKeywordBlockDef(
            name=keyword.options["name"],
            keyword=keyword.options["keyword"],
            placement=keyword.options.get("placement", "before_steps"),
            step_name=self._read_optional_text(keyword.options.get("step"), default_value=default_step_name),
            options=raw_options,
            data_lines=tuple(keyword.data_lines),
            order=int(keyword.options.get("order", "0")),
            description=keyword.options.get("description", ""),
        )

    def _translate_job_definition(self, keyword: InpKeyword) -> JobDef:
        step_names = self._parse_name_lines(keyword)
        return JobDef(name=keyword.options.get("name", "job-1"), step_names=step_names)

    def _translate_step_parameter_options(self, keyword: InpKeyword) -> dict[str, Any]:
        parameters: dict[str, Any] = {}
        for option_name, option_value in keyword.options.items():
            if option_name in {"name", "target", "target_type", "scope", "boundary_type", "load_type", "request_mode", "position", "frequency"}:
                continue
            parameters[option_name] = self._coerce_option_value(option_value)
        return parameters

    def _translate_frequency_parameters(self, keyword: InpKeyword) -> dict[str, Any]:
        parameters = self._translate_step_parameter_options(keyword)
        if "num_modes" in parameters:
            parameters["num_modes"] = int(parameters["num_modes"])
            return parameters
        if keyword.data_lines:
            parameters["num_modes"] = int(self._parse_float_line(keyword.data_lines[0])[0])
        return parameters

    def _translate_dynamic_parameters(self, keyword: InpKeyword) -> dict[str, Any]:
        parameters = self._translate_step_parameter_options(keyword)
        if keyword.data_lines:
            values = self._parse_float_line(keyword.data_lines[0])
            if len(values) >= 1 and "time_step" not in parameters:
                parameters["time_step"] = values[0]
            if len(values) >= 2 and "total_time" not in parameters:
                parameters["total_time"] = values[1]
        return parameters

    def _translate_step_parameter_block(self, keyword: InpKeyword) -> tuple[str, Any]:
        parameter_name = keyword.options["key"]
        value_kind = keyword.options.get("value_kind", "text")
        text_value = "\n".join(keyword.data_lines)
        if value_kind == "json":
            return parameter_name, json.loads(text_value)
        if value_kind == "number":
            return parameter_name, float(text_value.strip())
        if value_kind == "integer":
            return parameter_name, int(text_value.strip())
        if value_kind == "boolean":
            return parameter_name, self._coerce_option_value(text_value)
        return parameter_name, text_value

    def _parse_name_lines(self, keyword: InpKeyword) -> tuple[str, ...]:
        names: list[str] = []
        for data_line in keyword.data_lines:
            names.extend(item.strip() for item in data_line.split(",") if item.strip())
        return tuple(names)

    def _translate_boundary_block(
        self,
        model: ModelDB,
        default_part: Part | None,
        keyword: InpKeyword,
        prefix: str,
        start_index: int,
    ) -> tuple[str, ...]:
        generated_names: list[str] = []
        for offset, data_line in enumerate(keyword.data_lines, start=1):
            items = [item.strip() for item in data_line.split(",") if item.strip()]
            raw_target_name = items[0]
            scope, target_name = self._resolve_scoped_target(
                model,
                raw_target_name,
                default_part,
                preferred_target_types=("node", "node_set"),
            )
            first_dof = int(float(items[1]))
            last_dof = int(float(items[2])) if len(items) >= 3 else first_dof
            value = float(items[3]) if len(items) >= 4 else 0.0
            dof_values = {
                self._map_abaqus_dof(dof_number): value
                for dof_number in range(first_dof, last_dof + 1)
            }
            boundary_name = f"{prefix}-bc-{start_index + offset}"
            model.add_boundary(
                BoundaryDef(
                    name=boundary_name,
                    target_name=target_name,
                    target_type=self._resolve_target_type(scope, target_name),
                    scope_name=scope.scope_name,
                    dof_values=dof_values,
                )
            )
            generated_names.append(boundary_name)
        return tuple(generated_names)

    def _translate_cload_block(
        self,
        model: ModelDB,
        default_part: Part | None,
        keyword: InpKeyword,
        prefix: str,
        start_index: int,
    ) -> tuple[str, ...]:
        generated_names: list[str] = []
        for offset, data_line in enumerate(keyword.data_lines, start=1):
            items = [item.strip() for item in data_line.split(",") if item.strip()]
            raw_target_name = items[0]
            scope, target_name = self._resolve_scoped_target(
                model,
                raw_target_name,
                default_part,
                preferred_target_types=("node", "node_set"),
            )
            dof_number = int(float(items[1]))
            value = float(items[2])
            load_name = f"{prefix}-load-{start_index + offset}"
            model.add_nodal_load(
                NodalLoadDef(
                    name=load_name,
                    target_name=target_name,
                    target_type=self._resolve_target_type(scope, target_name),
                    scope_name=scope.scope_name,
                    components={self._map_load_component(dof_number): value},
                )
            )
            generated_names.append(load_name)
        return tuple(generated_names)

    def _translate_dsload_block(
        self,
        model: ModelDB,
        default_part: Part | None,
        keyword: InpKeyword,
        prefix: str,
        start_index: int,
    ) -> tuple[str, ...]:
        generated_names: list[str] = []
        for offset, data_line in enumerate(keyword.data_lines, start=1):
            items = [item.strip() for item in data_line.split(",") if item.strip()]
            if len(items) < 3:
                raise ModelValidationError("DSLOAD 定义至少需要给出表面名、载荷类型和值。")
            raw_target_name = items[0]
            scope, target_name = self._resolve_scoped_target(
                model,
                raw_target_name,
                default_part,
                preferred_target_types=("surface",),
            )
            if scope.get_surface(target_name) is None:
                raise ModelValidationError(f"目标表面 {raw_target_name} 不存在。")
            load_code = items[1].upper()
            if load_code != "P":
                raise ModelValidationError(f"当前 *Dsload 仅支持 P 压力载荷，收到 {load_code}。")
            value = float(items[2])
            load_name = f"{prefix}-dload-{start_index + offset}"
            model.add_distributed_load(
                DistributedLoadDef(
                    name=load_name,
                    target_name=target_name,
                    target_type="surface",
                    scope_name=scope.scope_name,
                    load_type="pressure",
                    components={"P": value},
                )
            )
            generated_names.append(load_name)
        return tuple(generated_names)

    def _resolve_scoped_target(
        self,
        model: ModelDB,
        raw_target_name: str,
        default_part: Part | None,
        *,
        preferred_target_types: tuple[str, ...],
    ) -> tuple[CompilationScope, str]:
        normalized_name = raw_target_name.strip()
        if "." in normalized_name:
            scope_name, target_name = normalized_name.split(".", 1)
            scope = model.resolve_compilation_scope(scope_name)
            if scope is not None:
                return scope, target_name
            if model.assembly is not None and scope_name in model.parts:
                raise ModelValidationError(f"装配模型中的目标 {normalized_name} 必须使用实例名而不是部件名。")
            raise ModelValidationError(f"目标 {normalized_name} 引用了不存在的作用域 {scope_name}。")

        if model.assembly is not None and model.assembly.instances:
            scope = self._resolve_assembly_alias_scope(model, normalized_name, preferred_target_types)
            if scope is not None:
                return scope, normalized_name
            raise ModelValidationError(f"装配模型中的目标 {normalized_name} 必须显式写成 INSTANCE.NAME，或先在 ASSEMBLY 中定义唯一别名。")

        if default_part is not None:
            scope = model.resolve_compilation_scope(default_part.name)
            if scope is None:
                raise ModelValidationError(f"未找到默认作用域 {default_part.name}。")
            return scope, normalized_name

        scopes = model.iter_compilation_scopes()
        if len(scopes) == 1:
            return scopes[0], normalized_name
        raise ModelValidationError(f"目标 {normalized_name} 缺少显式作用域，且当前无法唯一推断。")

    def _parse_set_members(self, keyword: InpKeyword) -> tuple[str, ...]:
        if "generate" in keyword.options:
            first_value, last_value, step = (int(value) for value in self._parse_float_line(keyword.data_lines[0]))
            return tuple(str(item) for item in range(first_value, last_value + 1, step))
        members: list[str] = []
        for data_line in keyword.data_lines:
            members.extend(item.strip() for item in data_line.split(",") if item.strip())
        return tuple(members)

    def _resolve_region_element_type(self, part: Part, region_name: str) -> str:
        try:
            first_element_name = part.mesh.element_sets[region_name][0]
        except (KeyError, IndexError) as error:
            raise ModelValidationError(f"区域 {region_name} 不存在或为空。") from error
        return part.get_element(first_element_name).type_key

    def _resolve_assembly_alias_scope(
        self,
        model: ModelDB,
        target_name: str,
        preferred_target_types: tuple[str, ...],
    ) -> CompilationScope | None:
        if model.assembly is None:
            return None

        matched_scope_names: list[str] = []
        for instance_name in model.assembly.instances:
            if "node_set" in preferred_target_types and target_name in model.assembly.node_sets_for_instance(instance_name):
                matched_scope_names.append(instance_name)
            if "element_set" in preferred_target_types and target_name in model.assembly.element_sets_for_instance(instance_name):
                matched_scope_names.append(instance_name)
            if "surface" in preferred_target_types and target_name in model.assembly.surfaces_for_instance(instance_name):
                matched_scope_names.append(instance_name)

        unique_scope_names = tuple(dict.fromkeys(matched_scope_names))
        if not unique_scope_names:
            return None
        if len(unique_scope_names) > 1:
            joined = ", ".join(unique_scope_names)
            raise ModelValidationError(f"装配别名 {target_name} 同时出现在多个实例中: {joined}。")

        resolved_scope = model.resolve_compilation_scope(unique_scope_names[0])
        if resolved_scope is None:
            raise ModelValidationError(f"未能解析装配别名 {target_name} 对应的实例作用域 {unique_scope_names[0]}。")
        return resolved_scope

    def _resolve_target_type(self, scope: CompilationScope, target_name: str) -> str:
        if scope.resolve_node_names("node", target_name):
            return "node"
        if scope.resolve_node_names("node_set", target_name):
            return "node_set"
        raise ModelValidationError(f"目标 {target_name} 既不是节点也不是节点集合。")

    def _register_default_output_requests(self, model: ModelDB, procedure_type: str, start_index: int) -> tuple[str, ...]:
        requests = self._default_output_requests(procedure_type)
        output_names: list[str] = []
        for offset, request in enumerate(requests, start=1):
            output_name = f"output-{start_index + offset}"
            model.add_output_request(
                OutputRequest(
                    name=output_name,
                    variables=request["variables"],
                    target_type="model",
                    position=request["position"],
                    frequency=1,
                )
            )
            output_names.append(output_name)
        return tuple(output_names)

    def _default_output_requests(self, procedure_type: str) -> tuple[dict[str, object], ...]:
        if procedure_type == "modal":
            return (
                {"variables": ("MODE_SHAPE",), "position": "NODE"},
                {"variables": ("FREQUENCY",), "position": "GLOBAL_HISTORY"},
            )
        if procedure_type == "implicit_dynamic":
            return (
                {"variables": ("U",), "position": "NODE"},
                {"variables": ("TIME",), "position": "GLOBAL_HISTORY"},
            )
        return (
            {"variables": ("U", "RF", "U_MAG"), "position": "NODE"},
            {"variables": ("S", "E", "SECTION"), "position": "ELEMENT_CENTROID"},
            {"variables": ("S_IP", "E_IP", "S_VM_IP", "S_PRINCIPAL_IP"), "position": "INTEGRATION_POINT"},
            {"variables": ("S_REC", "E_REC", "S_VM_REC", "S_PRINCIPAL_REC"), "position": "ELEMENT_NODAL"},
            {"variables": ("S_AVG", "S_VM_AVG", "S_PRINCIPAL_AVG"), "position": "NODE_AVERAGED"},
            {"variables": ("TIME",), "position": "GLOBAL_HISTORY"},
        )

    def _map_abaqus_dof(self, dof_number: int) -> str:
        mapping = {1: "UX", 2: "UY", 3: "UZ", 4: "RX", 5: "RY", 6: "RZ"}
        try:
            return mapping[dof_number]
        except KeyError as error:
            raise ModelValidationError(f"当前不支持 INP 自由度编号 {dof_number}。") from error

    def _map_load_component(self, dof_number: int) -> str:
        mapping = {1: "FX", 2: "FY", 3: "FZ", 4: "MX", 5: "MY", 6: "MZ"}
        try:
            return mapping[dof_number]
        except KeyError as error:
            raise ModelValidationError(f"当前不支持 INP 载荷自由度编号 {dof_number}。") from error

    def _coerce_option_value(self, raw_value: str) -> Any:
        normalized = raw_value.strip()
        lowered = normalized.lower()
        if lowered in {"true", "false"}:
            return lowered == "true"
        try:
            integer_value = int(normalized)
        except ValueError:
            try:
                return float(normalized)
            except ValueError:
                return normalized
        return integer_value

    def _read_optional_text(self, value: str | None, default_value: str | None = None) -> str | None:
        if value in {None, "", "none"}:
            return default_value
        return str(value)

    def _read_exported_model_name(self, description: str) -> str | None:
        for line in description.splitlines():
            stripped_line = line.strip()
            if not stripped_line.startswith("pyFEM exported model:"):
                continue
            model_name = stripped_line.partition(":")[2].strip()
            return model_name or None
        return None

    def _infer_request_mode(self, position: str) -> str:
        return "history" if str(position).strip().upper() == "GLOBAL_HISTORY" else "field"

    def _parse_float_line(self, data_line: str) -> tuple[float, ...]:
        return tuple(float(item.strip()) for item in data_line.split(",") if item.strip())


@dataclass(slots=True)
class InpImporter:
    """封装 INP 解析器与翻译器的导入入口。"""

    parser: InpParser = field(default_factory=InpParser)
    translator: InpTranslator = field(default_factory=InpTranslator)

    def import_text(self, text: str, model_name: str | None = None, source_name: str = "<memory>") -> ModelDB:
        """从 INP 文本导入模型数据库。"""

        document = self.parser.parse_text(text=text, source_name=source_name)
        return self.translator.translate(document=document, model_name=model_name)

    def import_file(self, path: str | Path, model_name: str | None = None) -> ModelDB:
        """从 INP 文件导入模型数据库。"""

        document = self.parser.parse_file(path)
        return self.translator.translate(document=document, model_name=model_name)
