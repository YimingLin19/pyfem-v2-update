"""定义参数化模型编辑弹窗。"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from pyfem.gui.model_edit_presenters import (
    BoundaryEditContext,
    EditScopeCandidate,
    EditTargetCandidate,
    LoadEditContext,
    ModelEditContext,
    ModelEditPresenter,
)


class BaseModelEditDialog(QDialog):
    """定义模型编辑弹窗的统一壳层。"""

    applied = Signal()

    def __init__(
        self,
        parent: QWidget | None,
        presenter: ModelEditPresenter,
        *,
        kind: str,
        name: str,
        context: ModelEditContext | None = None,
        window_title: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.presenter = presenter
        self.object_name = name
        self.context = presenter.build_context(kind, name) if context is None else context
        self.setWindowTitle(window_title or f"Edit {self.context.object_type_label}")
        self.resize(520, 420)
        self._build_shell()
        self._refresh_support_messages()

    def _build_shell(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        header_group = QGroupBox("Object", self)
        header_layout = QFormLayout(header_group)
        self.object_name_value = QLabel(self.context.object_name, header_group)
        self.object_type_value = QLabel(self.context.object_type_label, header_group)
        self.owner_value = QLabel(self.context.owner_label, header_group)
        self.owner_value.setWordWrap(True)
        header_layout.addRow("Name", self.object_name_value)
        header_layout.addRow("Type", self.object_type_value)
        header_layout.addRow("Owner", self.owner_value)

        self.form_frame = QFrame(self)
        self.form_layout = QFormLayout(self.form_frame)
        self.form_layout.setContentsMargins(0, 0, 0, 0)
        self.form_layout.setSpacing(6)

        self.support_group = QGroupBox("Support", self)
        support_layout = QVBoxLayout(self.support_group)
        support_layout.setContentsMargins(8, 8, 8, 8)
        self.support_value = QLabel("-", self.support_group)
        self.support_value.setWordWrap(True)
        support_layout.addWidget(self.support_value)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(6)
        self.apply_button = QPushButton("Apply", self)
        self.ok_button = QPushButton("OK", self)
        self.cancel_button = QPushButton("Cancel", self)
        self.apply_button.clicked.connect(self._apply_only)
        self.ok_button.clicked.connect(self._apply_and_close)
        self.cancel_button.clicked.connect(self.reject)
        button_row.addStretch(1)
        button_row.addWidget(self.apply_button)
        button_row.addWidget(self.ok_button)
        button_row.addWidget(self.cancel_button)

        layout.addWidget(header_group)
        layout.addWidget(self.form_frame)
        layout.addWidget(self.support_group)
        layout.addStretch(1)
        layout.addLayout(button_row)

    def _apply_only(self) -> None:
        try:
            self.apply_changes()
        except Exception as error:  # noqa: BLE001
            QMessageBox.critical(self, "Edit Failed", str(error))

    def _apply_and_close(self) -> None:
        try:
            self.apply_changes()
        except Exception as error:  # noqa: BLE001
            QMessageBox.critical(self, "Edit Failed", str(error))
            return
        self.accept()

    def _refresh_support_messages(self) -> None:
        messages = self.context.support_messages or ("当前对象已纳入正式编辑主线。",)
        self.support_value.setText("\n".join(messages))

    def _set_combo_data(self, combo_box: QComboBox, data: object) -> None:
        index = combo_box.findData(data)
        if index >= 0:
            combo_box.setCurrentIndex(index)

    def apply_changes(self) -> None:
        """由子类实现正式写回。"""

        raise NotImplementedError


class MaterialEditDialog(BaseModelEditDialog):
    """定义材料编辑弹窗。"""

    def __init__(self, parent: QWidget | None, presenter: ModelEditPresenter, material_name: str) -> None:
        self.material_name = material_name
        super().__init__(parent, presenter, kind="material", name=material_name)
        self._load_values()

    def _build_shell(self) -> None:
        super()._build_shell()
        self.material_type_combo = QComboBox(self.form_frame)
        self.material_type_combo.addItem("Linear Elastic", "linear_elastic")
        self.material_type_combo.addItem("J2 Plasticity", "j2_plasticity")
        self.young_modulus_edit = QLineEdit(self.form_frame)
        self.poisson_ratio_edit = QLineEdit(self.form_frame)
        self.density_edit = QLineEdit(self.form_frame)
        self.yield_stress_edit = QLineEdit(self.form_frame)
        self.hardening_modulus_edit = QLineEdit(self.form_frame)
        self.tangent_mode_combo = QComboBox(self.form_frame)
        self.tangent_mode_combo.addItem("Consistent", "consistent")
        self.tangent_mode_combo.addItem("Numerical", "numerical")
        self.material_type_combo.currentIndexChanged.connect(self._refresh_field_state)
        self.form_layout.addRow("Material Type", self.material_type_combo)
        self.form_layout.addRow("Young's Modulus", self.young_modulus_edit)
        self.form_layout.addRow("Poisson Ratio", self.poisson_ratio_edit)
        self.form_layout.addRow("Density", self.density_edit)
        self.form_layout.addRow("Yield Stress", self.yield_stress_edit)
        self.form_layout.addRow("Hardening Modulus", self.hardening_modulus_edit)
        self.form_layout.addRow("Tangent Mode", self.tangent_mode_combo)

    def _load_values(self) -> None:
        material = self.presenter.material(self.material_name)
        parameters = material.parameters
        self._set_combo_data(self.material_type_combo, material.material_type)
        self.young_modulus_edit.setText(str(parameters.get("young_modulus", "")))
        self.poisson_ratio_edit.setText(str(parameters.get("poisson_ratio", "")))
        self.density_edit.setText("" if "density" not in parameters else str(parameters.get("density")))
        self.yield_stress_edit.setText("" if "yield_stress" not in parameters else str(parameters.get("yield_stress")))
        self.hardening_modulus_edit.setText("" if "hardening_modulus" not in parameters else str(parameters.get("hardening_modulus")))
        self._set_combo_data(self.tangent_mode_combo, parameters.get("tangent_mode", "consistent"))
        self._refresh_field_state()

    def _refresh_field_state(self) -> None:
        j2_enabled = self.material_type_combo.currentData() == "j2_plasticity"
        for widget in (self.yield_stress_edit, self.hardening_modulus_edit, self.tangent_mode_combo):
            widget.setEnabled(j2_enabled)

    def apply_changes(self) -> None:
        self.presenter.apply_material_update(
            self.material_name,
            material_type=str(self.material_type_combo.currentData()),
            young_modulus_text=self.young_modulus_edit.text(),
            poisson_ratio_text=self.poisson_ratio_edit.text(),
            density_text=self.density_edit.text(),
            yield_stress_text=self.yield_stress_edit.text(),
            hardening_modulus_text=self.hardening_modulus_edit.text(),
            tangent_mode=str(self.tangent_mode_combo.currentData()),
        )
        self.context = self.presenter.build_context("material", self.material_name)
        self._refresh_support_messages()
        self.applied.emit()


class StepEditDialog(BaseModelEditDialog):
    """定义步骤编辑弹窗。"""

    modelChanged = Signal(str, object, str)

    STEP_TYPE_CHOICES: tuple[tuple[str, str], ...] = (
        ("Static Linear", "static_linear"),
        ("Static Nonlinear", "static_nonlinear"),
        ("Modal", "modal"),
        ("Implicit Dynamic", "implicit_dynamic"),
    )

    def __init__(
        self,
        parent: QWidget | None,
        presenter: ModelEditPresenter,
        step_name: str,
        *,
        create_mode: bool = False,
    ) -> None:
        self.step_name = step_name
        self.create_mode = create_mode
        dialog_context = self._build_dialog_context(presenter)
        super().__init__(
            parent,
            presenter,
            kind="step",
            name=step_name,
            context=dialog_context,
            window_title=f"{'Create' if create_mode else 'Edit'} Step",
        )
        self._load_values()

    def _build_dialog_context(self, presenter: ModelEditPresenter) -> ModelEditContext:
        """为创建模式提供壳层上下文。"""

        if not self.create_mode:
            return presenter.build_context("step", self.step_name)
        return ModelEditContext(
            resolved_kind="step",
            object_name=self.step_name,
            object_type_label="Step",
            owner_label="job=-",
            support_messages=("请先选择步骤类型并补全当前类型所需参数，再提交到当前 ModelDB。",),
        )

    def _build_shell(self) -> None:
        super()._build_shell()
        self.procedure_type_combo = QComboBox(self.form_frame)
        for label, value in self.STEP_TYPE_CHOICES:
            self.procedure_type_combo.addItem(label, value)
        self.procedure_type_combo.setPlaceholderText("Select a step type")
        self.step_type_hint_label = QLabel(self.form_frame)
        self.step_type_hint_label.setWordWrap(True)

        general_group = QGroupBox("General", self.form_frame)
        general_layout = QFormLayout(general_group)
        general_layout.addRow("Step Type", self.procedure_type_combo)
        general_layout.addRow("State", self.step_type_hint_label)

        self.initial_increment_edit = QLineEdit(self.form_frame)
        self.max_increments_edit = QLineEdit(self.form_frame)
        self.min_increment_edit = QLineEdit(self.form_frame)
        self.time_step_edit = QLineEdit(self.form_frame)
        self.total_time_edit = QLineEdit(self.form_frame)
        self.initial_increment_label = QLabel("Initial Increment", self.form_frame)
        self.max_increments_label = QLabel("Max Increments", self.form_frame)
        self.min_increment_label = QLabel("Min Increment", self.form_frame)
        self.time_step_label = QLabel("Time Step", self.form_frame)
        self.total_time_label = QLabel("Total Time", self.form_frame)

        self.increment_group = QGroupBox("Increment / Time", self.form_frame)
        increment_layout = QFormLayout(self.increment_group)
        increment_layout.addRow(self.initial_increment_label, self.initial_increment_edit)
        increment_layout.addRow(self.max_increments_label, self.max_increments_edit)
        increment_layout.addRow(self.min_increment_label, self.min_increment_edit)
        increment_layout.addRow(self.time_step_label, self.time_step_edit)
        increment_layout.addRow(self.total_time_label, self.total_time_edit)

        self.nlgeom_checkbox = QCheckBox("Enable nlgeom", self.form_frame)
        self.max_iterations_edit = QLineEdit(self.form_frame)
        self.residual_tolerance_edit = QLineEdit(self.form_frame)
        self.displacement_tolerance_edit = QLineEdit(self.form_frame)
        self.allow_cutback_checkbox = QCheckBox("Allow Cutback", self.form_frame)
        self.line_search_checkbox = QCheckBox("Enable Line Search", self.form_frame)
        self.nonlinear_group = QGroupBox("Nonlinear Controls", self.form_frame)
        nonlinear_layout = QFormLayout(self.nonlinear_group)
        nonlinear_layout.addRow("nlgeom", self.nlgeom_checkbox)
        nonlinear_layout.addRow("Max Iterations", self.max_iterations_edit)
        nonlinear_layout.addRow("Residual Tolerance", self.residual_tolerance_edit)
        nonlinear_layout.addRow("Displacement Tolerance", self.displacement_tolerance_edit)
        nonlinear_layout.addRow("Allow Cutback", self.allow_cutback_checkbox)
        nonlinear_layout.addRow("Line Search", self.line_search_checkbox)

        self.num_modes_edit = QLineEdit(self.form_frame)
        self.modal_group = QGroupBox("Output / Frequency", self.form_frame)
        modal_layout = QFormLayout(self.modal_group)
        modal_layout.addRow("Number of Modes", self.num_modes_edit)

        self.boundary_refs_value = QLabel("-", self.form_frame)
        self.boundary_refs_value.setWordWrap(True)
        self.nodal_load_refs_value = QLabel("-", self.form_frame)
        self.nodal_load_refs_value.setWordWrap(True)
        self.distributed_load_refs_value = QLabel("-", self.form_frame)
        self.distributed_load_refs_value.setWordWrap(True)
        self.output_request_refs_value = QLabel("-", self.form_frame)
        self.output_request_refs_value.setWordWrap(True)
        self.reference_group = QGroupBox("References", self.form_frame)
        reference_layout = QFormLayout(self.reference_group)
        reference_layout.addRow("Boundaries", self.boundary_refs_value)
        reference_layout.addRow("Nodal Loads", self.nodal_load_refs_value)
        reference_layout.addRow("Distributed Loads", self.distributed_load_refs_value)
        reference_layout.addRow("Output Requests", self.output_request_refs_value)

        self.form_layout.addRow(general_group)
        self.form_layout.addRow(self.increment_group)
        self.form_layout.addRow(self.nonlinear_group)
        self.form_layout.addRow(self.modal_group)
        self.form_layout.addRow(self.reference_group)

        self._validation_inputs = (
            self.initial_increment_edit,
            self.max_increments_edit,
            self.min_increment_edit,
            self.max_iterations_edit,
            self.residual_tolerance_edit,
            self.displacement_tolerance_edit,
            self.num_modes_edit,
            self.time_step_edit,
            self.total_time_edit,
        )
        self.procedure_type_combo.currentIndexChanged.connect(self._refresh_field_state)
        self.procedure_type_combo.currentIndexChanged.connect(self._refresh_submit_state)
        for edit in self._validation_inputs:
            edit.textChanged.connect(self._refresh_submit_state)
        for checkbox in (self.nlgeom_checkbox, self.allow_cutback_checkbox, self.line_search_checkbox):
            checkbox.toggled.connect(self._refresh_submit_state)

    def _load_values(self) -> None:
        if self.create_mode:
            self.procedure_type_combo.setCurrentIndex(-1)
            self.nlgeom_checkbox.setChecked(False)
            self.initial_increment_edit.setText("")
            self.max_increments_edit.setText("")
            self.min_increment_edit.setText("")
            self.max_iterations_edit.setText("")
            self.residual_tolerance_edit.setText("")
            self.displacement_tolerance_edit.setText("")
            self.allow_cutback_checkbox.setChecked(True)
            self.line_search_checkbox.setChecked(False)
            self.num_modes_edit.setText("")
            self.time_step_edit.setText("")
            self.total_time_edit.setText("")
        else:
            step = self.presenter.step(self.step_name)
            parameters = step.parameters
            self._set_combo_data(self.procedure_type_combo, self._normalize_procedure_type(step.procedure_type))
            self.nlgeom_checkbox.setChecked(bool(parameters.get("nlgeom", False)))
            self.initial_increment_edit.setText(str(parameters.get("initial_increment", "")))
            self.max_increments_edit.setText(str(parameters.get("max_increments", "")))
            self.min_increment_edit.setText(str(parameters.get("min_increment", "")))
            self.max_iterations_edit.setText(str(parameters.get("max_iterations", "")))
            self.residual_tolerance_edit.setText(str(parameters.get("residual_tolerance", "")))
            self.displacement_tolerance_edit.setText(str(parameters.get("displacement_tolerance", "")))
            self.allow_cutback_checkbox.setChecked(bool(parameters.get("allow_cutback", True)))
            self.line_search_checkbox.setChecked(bool(parameters.get("line_search", False)))
            self.num_modes_edit.setText(str(parameters.get("num_modes", "")))
            self.time_step_edit.setText(str(parameters.get("time_step", "")))
            self.total_time_edit.setText(str(parameters.get("total_time", "")))
        self._refresh_reference_summary()
        self._refresh_field_state()
        self._refresh_submit_state()

    def _refresh_field_state(self) -> None:
        procedure_type = self.current_procedure_type()
        is_nonlinear = procedure_type == "static_nonlinear"
        is_modal = procedure_type == "modal"
        is_dynamic = procedure_type == "implicit_dynamic"

        self.increment_group.setVisible(is_nonlinear or is_dynamic)
        self.nonlinear_group.setVisible(is_nonlinear)
        self.modal_group.setVisible(is_modal)

        self.initial_increment_label.setVisible(is_nonlinear)
        self.initial_increment_edit.setVisible(is_nonlinear)
        self.max_increments_label.setVisible(is_nonlinear)
        self.max_increments_edit.setVisible(is_nonlinear)
        self.min_increment_label.setVisible(is_nonlinear)
        self.min_increment_edit.setVisible(is_nonlinear)
        self.time_step_label.setVisible(is_dynamic)
        self.time_step_edit.setVisible(is_dynamic)
        self.total_time_label.setVisible(is_dynamic)
        self.total_time_edit.setVisible(is_dynamic)

        self.nlgeom_checkbox.setEnabled(is_nonlinear)
        self.max_iterations_edit.setEnabled(is_nonlinear)
        self.residual_tolerance_edit.setEnabled(is_nonlinear)
        self.displacement_tolerance_edit.setEnabled(is_nonlinear)
        self.allow_cutback_checkbox.setEnabled(is_nonlinear)
        self.line_search_checkbox.setEnabled(is_nonlinear)
        self.num_modes_edit.setEnabled(is_modal)
        self._refresh_step_feedback()

    def _refresh_reference_summary(self) -> None:
        """刷新引用概览。"""

        if self.create_mode and self.step_name not in self.presenter.list_step_names():
            self.boundary_refs_value.setText("-")
            self.nodal_load_refs_value.setText("-")
            self.distributed_load_refs_value.setText("-")
            self.output_request_refs_value.setText("-")
            return
        step = self.presenter.step(self.step_name)
        self.boundary_refs_value.setText(", ".join(step.boundary_names) or "-")
        self.nodal_load_refs_value.setText(", ".join(step.nodal_load_names) or "-")
        self.distributed_load_refs_value.setText(", ".join(step.distributed_load_names) or "-")
        self.output_request_refs_value.setText(", ".join(step.output_request_names) or "-")

    def current_procedure_type(self) -> str | None:
        """返回当前选中的步骤类型。"""

        value = self.procedure_type_combo.currentData()
        if value in {None, ""}:
            return None
        return self._normalize_procedure_type(str(value))

    def _required_field_labels(self) -> tuple[str, ...]:
        """返回当前类型所需的最小字段标签。"""

        procedure_type = self.current_procedure_type()
        if procedure_type == "static_nonlinear":
            required_pairs = (
                ("Initial Increment", self.initial_increment_edit.text()),
                ("Max Increments", self.max_increments_edit.text()),
                ("Min Increment", self.min_increment_edit.text()),
                ("Max Iterations", self.max_iterations_edit.text()),
                ("Residual Tolerance", self.residual_tolerance_edit.text()),
                ("Displacement Tolerance", self.displacement_tolerance_edit.text()),
            )
            return tuple(label for label, text in required_pairs if not str(text).strip())
        if procedure_type == "modal":
            return ("Number of Modes",) if not self.num_modes_edit.text().strip() else ()
        if procedure_type == "implicit_dynamic":
            required_pairs = (
                ("Time Step", self.time_step_edit.text()),
                ("Total Time", self.total_time_edit.text()),
            )
            return tuple(label for label, text in required_pairs if not str(text).strip())
        return ()

    def _refresh_step_feedback(self) -> None:
        """同步步骤类型提示与空状态说明。"""

        procedure_type = self.current_procedure_type()
        if procedure_type is None:
            self.step_type_hint_label.setText("Select a step type first. No type is preselected in create mode.")
            return
        missing_labels = self._required_field_labels()
        if missing_labels:
            self.step_type_hint_label.setText(f"{self.procedure_type_combo.currentText()} requires: {', '.join(missing_labels)}.")
            return
        if procedure_type == "static_linear":
            self.step_type_hint_label.setText("Static Linear is ready. Advanced nonlinear controls stay hidden for this type.")
            return
        if procedure_type == "static_nonlinear":
            self.step_type_hint_label.setText("Static Nonlinear is ready. Nonlinear controls are now enabled.")
            return
        if procedure_type == "modal":
            self.step_type_hint_label.setText("Modal is ready. Only mode-count controls remain enabled for this type.")
            return
        self.step_type_hint_label.setText("Implicit Dynamic is ready. Time controls are enabled for this type.")

    def _refresh_submit_state(self) -> None:
        """实时同步提交按钮启停。"""

        can_submit = self.current_procedure_type() is not None and not self._required_field_labels()
        self.apply_button.setEnabled(can_submit)
        self.ok_button.setEnabled(can_submit)

    def _normalize_procedure_type(self, procedure_type: str) -> str:
        """归一化步骤类型别名。"""

        normalized_type = str(procedure_type).strip().lower()
        aliases = {
            "static": "static_linear",
            "static_linear": "static_linear",
            "static_nonlinear": "static_nonlinear",
            "modal": "modal",
            "dynamic": "implicit_dynamic",
            "implicit_dynamic": "implicit_dynamic",
        }
        return aliases.get(normalized_type, normalized_type)

    def apply_changes(self) -> None:
        operation = "created" if self.create_mode else "updated"
        self.presenter.apply_step_editor_update(
            self.step_name,
            creating=self.create_mode,
            procedure_type="" if self.current_procedure_type() is None else self.current_procedure_type(),
            nlgeom=self.nlgeom_checkbox.isChecked(),
            initial_increment_text=self.initial_increment_edit.text(),
            max_increments_text=self.max_increments_edit.text(),
            min_increment_text=self.min_increment_edit.text(),
            max_iterations_text=self.max_iterations_edit.text(),
            residual_tolerance_text=self.residual_tolerance_edit.text(),
            displacement_tolerance_text=self.displacement_tolerance_edit.text(),
            allow_cutback=self.allow_cutback_checkbox.isChecked(),
            line_search=self.line_search_checkbox.isChecked(),
            num_modes_text=self.num_modes_edit.text(),
            time_step_text=self.time_step_edit.text(),
            total_time_text=self.total_time_edit.text(),
        )
        self.create_mode = False
        self.context = self.presenter.build_context("step", self.step_name)
        self.object_type_value.setText(self.context.object_type_label)
        self.owner_value.setText(self.context.owner_label)
        self._refresh_reference_summary()
        self._refresh_support_messages()
        self.applied.emit()
        self.modelChanged.emit("step", self.step_name, operation)


class LoadEditDialog(BaseModelEditDialog):
    """定义载荷编辑弹窗。"""

    modelChanged = Signal(str, object, str)

    def __init__(
        self,
        parent: QWidget | None,
        presenter: ModelEditPresenter,
        kind: str,
        load_name: str,
        *,
        create_mode: bool = False,
        edit_context: LoadEditContext | None = None,
    ) -> None:
        self.load_name = load_name
        self.create_mode = create_mode
        self.edit_context = edit_context or LoadEditContext()
        self.original_kind = str(kind).strip().lower()
        self.load_kind = self.original_kind if create_mode else presenter.resolve_kind(kind, load_name)
        self._scope_candidates: tuple[EditScopeCandidate, ...] = ()
        self._target_candidates: tuple[EditTargetCandidate, ...] = ()
        dialog_context = self._build_dialog_context(presenter)
        super().__init__(
            parent,
            presenter,
            kind=self.load_kind,
            name=load_name,
            context=dialog_context,
            window_title=f"{'Create' if create_mode else 'Edit'} {self._type_label_for_kind(self.load_kind)}",
        )
        self._load_values()

    def _build_dialog_context(self, presenter: ModelEditPresenter) -> ModelEditContext:
        """为创建模式提供壳层上下文。"""

        if not self.create_mode:
            return presenter.build_context(self.load_kind, self.load_name)
        preferred_step_name = self.edit_context.preferred_step_name
        return ModelEditContext(
            resolved_kind=self.load_kind,
            object_name=self.load_name,
            object_type_label=self._type_label_for_kind(self.load_kind),
            owner_label=f"Step: {preferred_step_name}" if preferred_step_name else "Step: 未绑定",
            support_messages=("请先补全最小必要信息，再提交到当前 ModelDB。",),
        )

    def _build_shell(self) -> None:
        super()._build_shell()
        self.step_combo = QComboBox(self.form_frame)
        self.step_combo.setPlaceholderText("Select a step")
        self.step_hint_label = QLabel(self.form_frame)
        self.step_hint_label.setWordWrap(True)
        self.load_kind_combo = QComboBox(self.form_frame)
        self.load_kind_combo.addItem("Nodal Load", "nodal_load")
        self.load_kind_combo.addItem("Distributed Load", "distributed_load")
        self.scope_combo = QComboBox(self.form_frame)
        self.scope_combo.setPlaceholderText("Select a scope")
        self.target_type_combo = QComboBox(self.form_frame)
        self.target_combo = QComboBox(self.form_frame)
        self.target_combo.setPlaceholderText("Select a target")
        self.target_hint_label = QLabel(self.form_frame)
        self.target_hint_label.setWordWrap(True)
        self.components_edit = QLineEdit(self.form_frame)
        self.components_edit.setPlaceholderText("FX=0, FY=-10")
        self.load_type_combo = QComboBox(self.form_frame)
        self.load_type_combo.addItem("Pressure", "pressure")
        self.load_type_combo.addItem("Follower Pressure", "follower_pressure")
        self.load_type_combo.addItem("Traction", "traction")
        self.load_value_edit = QLineEdit(self.form_frame)
        self.load_value_edit.setPlaceholderText("Magnitude")

        step_container = QWidget(self.form_frame)
        step_layout = QVBoxLayout(step_container)
        step_layout.setContentsMargins(0, 0, 0, 0)
        step_layout.setSpacing(4)
        step_layout.addWidget(self.step_combo)
        step_layout.addWidget(self.step_hint_label)

        target_container = QWidget(self.form_frame)
        target_layout = QVBoxLayout(target_container)
        target_layout.setContentsMargins(0, 0, 0, 0)
        target_layout.setSpacing(4)
        target_layout.addWidget(self.target_combo)
        target_layout.addWidget(self.target_hint_label)

        self.nodal_container = QWidget(self.form_frame)
        nodal_layout = QFormLayout(self.nodal_container)
        nodal_layout.setContentsMargins(0, 0, 0, 0)
        nodal_layout.addRow("Components", self.components_edit)

        self.distributed_container = QWidget(self.form_frame)
        distributed_layout = QFormLayout(self.distributed_container)
        distributed_layout.setContentsMargins(0, 0, 0, 0)
        distributed_layout.addRow("Distributed Type", self.load_type_combo)
        distributed_layout.addRow("Magnitude", self.load_value_edit)

        self.form_layout.addRow("Step", step_container)
        self.form_layout.addRow("Load Type", self.load_kind_combo)
        self.form_layout.addRow("Scope", self.scope_combo)
        self.form_layout.addRow("Target Type", self.target_type_combo)
        self.form_layout.addRow("Target", target_container)
        self.form_layout.addRow("Nodal Parameters", self.nodal_container)
        self.form_layout.addRow("Distributed Parameters", self.distributed_container)

        self.step_combo.currentIndexChanged.connect(self._refresh_step_feedback)
        self.step_combo.currentIndexChanged.connect(self._refresh_submit_state)
        self.load_kind_combo.currentIndexChanged.connect(self._on_load_kind_changed)
        self.scope_combo.currentIndexChanged.connect(self._on_scope_changed)
        self.target_type_combo.currentIndexChanged.connect(self._rebuild_target_choices)
        self.target_combo.currentIndexChanged.connect(self._refresh_target_feedback)
        self.target_combo.currentIndexChanged.connect(self._refresh_submit_state)
        self.components_edit.textChanged.connect(self._refresh_submit_state)
        self.load_value_edit.textChanged.connect(self._refresh_submit_state)

    def _load_values(self) -> None:
        self._rebuild_step_choices()
        self._set_combo_data(self.load_kind_combo, self.load_kind)
        self._rebuild_scope_choices()
        if self.load_kind == "nodal_load" and not self.create_mode:
            load = self.presenter.nodal_load(self.load_name)
            self.components_edit.setText(", ".join(f"{key}={value}" for key, value in load.components.items()))
        elif not self.create_mode:
            load = self.presenter.distributed_load(self.load_name)
            self._set_combo_data(self.load_type_combo, load.load_type)
            self.load_value_edit.setText(str(next(iter(load.components.values()), "")))
        self._rebuild_target_type_choices()
        self._rebuild_target_choices()
        self._refresh_mode_visibility()
        self._refresh_step_feedback()
        self._refresh_target_feedback()
        self._refresh_submit_state()

    def _rebuild_step_choices(self) -> None:
        """重建步骤选择。"""

        step_names = self.presenter.list_step_names()
        preferred_step_name = self.edit_context.preferred_step_name
        if not self.create_mode:
            referenced_steps = self.presenter.load_reference_steps(self.load_name, resolved_kind=self.load_kind)
            preferred_step_name = referenced_steps[0] if referenced_steps else preferred_step_name
        self.step_combo.blockSignals(True)
        self.step_combo.clear()
        for step_name in step_names:
            self.step_combo.addItem(step_name, step_name)
        if preferred_step_name in step_names:
            self.step_combo.setCurrentIndex(self.step_combo.findData(preferred_step_name))
        else:
            self.step_combo.setCurrentIndex(-1)
        self.step_combo.setEnabled(bool(step_names))
        self.step_combo.blockSignals(False)

    def _rebuild_scope_choices(self) -> None:
        """重建作用域选择。"""

        self._scope_candidates = self.presenter.list_edit_scope_candidates()
        preferred_scope_name = self.edit_context.preferred_scope_name
        if not self.create_mode:
            load = self.presenter.nodal_load(self.load_name) if self.load_kind == "nodal_load" else self.presenter.distributed_load(self.load_name)
            preferred_scope_name = load.scope_name
        self.scope_combo.blockSignals(True)
        self.scope_combo.clear()
        for candidate in self._scope_candidates:
            self.scope_combo.addItem(f"{candidate.scope_name} [{candidate.part_name}]", candidate.scope_name)
        if preferred_scope_name is not None and self.scope_combo.findData(preferred_scope_name) >= 0:
            self.scope_combo.setCurrentIndex(self.scope_combo.findData(preferred_scope_name))
        else:
            self.scope_combo.setCurrentIndex(-1)
        self.scope_combo.setEnabled(bool(self._scope_candidates))
        self.scope_combo.blockSignals(False)

    def _on_load_kind_changed(self) -> None:
        """处理载荷类型切换。"""

        self.load_kind = self.current_load_kind()
        self._rebuild_target_type_choices()
        self._rebuild_target_choices()
        self._refresh_mode_visibility()
        self._refresh_submit_state()

    def _on_scope_changed(self) -> None:
        """处理作用域切换。"""

        self._rebuild_target_choices()
        self._refresh_target_feedback()
        self._refresh_submit_state()

    def _rebuild_target_type_choices(self) -> None:
        """按载荷类型重建目标类型。"""

        current_kind = self.current_load_kind()
        preferred_target_type = self.edit_context.preferred_target_type
        if not self.create_mode:
            load = self.presenter.nodal_load(self.load_name) if current_kind == "nodal_load" else self.presenter.distributed_load(self.load_name)
            preferred_target_type = load.target_type
        choices = (("Node", "node"), ("Node Set", "node_set")) if current_kind == "nodal_load" else (("Surface", "surface"), ("Element Set", "element_set"))
        self.target_type_combo.blockSignals(True)
        self.target_type_combo.clear()
        for label, value in choices:
            self.target_type_combo.addItem(label, value)
        if preferred_target_type is not None and self.target_type_combo.findData(preferred_target_type) >= 0:
            self.target_type_combo.setCurrentIndex(self.target_type_combo.findData(preferred_target_type))
        else:
            self.target_type_combo.setCurrentIndex(0 if choices else -1)
        self.target_type_combo.setEnabled(bool(choices) and self.scope_combo.currentData() is not None)
        self.target_type_combo.blockSignals(False)

    def _rebuild_target_choices(self) -> None:
        """按当前 scope 过滤目标。"""

        scope_name = self.current_scope_name()
        target_type = self.current_target_type()
        preferred_target_name = self.edit_context.preferred_target_name
        if not self.create_mode:
            load = self.presenter.nodal_load(self.load_name) if self.current_load_kind() == "nodal_load" else self.presenter.distributed_load(self.load_name)
            preferred_target_name = load.target_name
        self._target_candidates = ()
        self.target_combo.blockSignals(True)
        self.target_combo.clear()
        if scope_name is not None and target_type is not None:
            self._target_candidates = self.presenter.list_target_candidates(scope_name=scope_name, target_type=target_type)
            for candidate in self._target_candidates:
                self.target_combo.addItem(candidate.display_label, candidate.target_name)
        if preferred_target_name is not None and self.target_combo.findData(preferred_target_name) >= 0:
            self.target_combo.setCurrentIndex(self.target_combo.findData(preferred_target_name))
        elif self._target_candidates:
            self.target_combo.setCurrentIndex(-1 if self.create_mode else 0)
        else:
            self.target_combo.setCurrentIndex(-1)
        self.target_combo.setEnabled(bool(self._target_candidates))
        self.target_combo.blockSignals(False)

    def _refresh_mode_visibility(self) -> None:
        """按当前载荷类型切换参数区。"""

        is_nodal = self.current_load_kind() == "nodal_load"
        self.nodal_container.setVisible(is_nodal)
        self.distributed_container.setVisible(not is_nodal)

    def _refresh_step_feedback(self) -> None:
        """刷新步骤提示。"""

        if not self.presenter.list_step_names():
            self.step_hint_label.setText("当前模型没有可用 step。请先创建 step，再定义载荷。")
            self.owner_value.setText("Step: 未绑定")
        elif self.current_step_name() is None:
            self.step_hint_label.setText("请选择一个 step，载荷不会偷偷绑定到默认步骤。")
            self.owner_value.setText("Step: 未绑定")
        else:
            self.step_hint_label.setText(f"当前载荷将挂接到 step: {self.current_step_name()}")
            self.owner_value.setText(f"Step: {self.current_step_name()}")

    def _refresh_target_feedback(self) -> None:
        """刷新目标联动提示。"""

        if not self._scope_candidates:
            self.target_hint_label.setText("当前模型没有可用 scope，无法分配载荷目标。")
        elif self.current_scope_name() is None:
            self.target_hint_label.setText("请先选择 scope，再过滤目标列表。")
        elif not self._target_candidates:
            self.target_hint_label.setText("当前 scope 下没有可用 target，请切换 scope 或 target type。")
        elif self.current_target_name() is None:
            self.target_hint_label.setText("请选择一个有效 target 后才能提交。")
        else:
            self.target_hint_label.setText(f"当前目标: {self.current_target_name()}")

    def _refresh_submit_state(self) -> None:
        """刷新提交按钮状态。"""

        enabled = self._can_submit()
        self.apply_button.setEnabled(enabled)
        self.ok_button.setEnabled(enabled)

    def _can_submit(self) -> bool:
        """判断当前是否满足最小提交条件。"""

        if self.current_step_name() is None or self.current_scope_name() is None:
            return False
        if self.current_target_type() is None or self.current_target_name() is None:
            return False
        return bool(self.components_edit.text().strip()) if self.current_load_kind() == "nodal_load" else bool(self.load_value_edit.text().strip())

    def current_load_kind(self) -> str:
        """返回当前载荷类型。"""

        return str(self.load_kind_combo.currentData() or self.load_kind).strip().lower()

    def current_step_name(self) -> str | None:
        """返回当前步骤名称。"""

        value = self.step_combo.currentData()
        return None if value in {None, ""} else str(value)

    def current_scope_name(self) -> str | None:
        """返回当前作用域名称。"""

        value = self.scope_combo.currentData()
        return None if value in {None, ""} else str(value)

    def current_target_type(self) -> str | None:
        """返回当前目标类型。"""

        value = self.target_type_combo.currentData()
        return None if value in {None, ""} else str(value)

    def current_target_name(self) -> str | None:
        """返回当前目标名称。"""

        value = self.target_combo.currentData()
        return None if value in {None, ""} else str(value)

    def _type_label_for_kind(self, load_kind: str) -> str:
        """返回载荷类型显示名。"""

        return "Nodal Load" if str(load_kind).strip().lower() == "nodal_load" else "Distributed Load"

    def apply_changes(self) -> None:
        operation = "created" if self.create_mode else "updated"
        self.presenter.apply_load_editor_update(
            self.load_name,
            creating=self.create_mode,
            original_kind=self.original_kind,
            load_kind=self.current_load_kind(),
            step_name=self.current_step_name(),
            target_name_text="" if self.current_target_name() is None else self.current_target_name(),
            target_type="" if self.current_target_type() is None else self.current_target_type(),
            scope_name_text="" if self.current_scope_name() is None else self.current_scope_name(),
            components_text=self.components_edit.text(),
            load_type=str(self.load_type_combo.currentData() or "pressure"),
            load_value_text=self.load_value_edit.text(),
        )
        self.create_mode = False
        self.original_kind = self.current_load_kind()
        self.load_kind = self.current_load_kind()
        self.context = self.presenter.build_context(self.load_kind, self.load_name)
        self.object_type_value.setText(self.context.object_type_label)
        self.owner_value.setText(self.context.owner_label)
        self._refresh_support_messages()
        self.applied.emit()
        self.modelChanged.emit(self.load_kind, self.load_name, operation)


class BoundaryEditDialog(BaseModelEditDialog):
    """定义边界条件编辑弹窗。"""

    modelChanged = Signal(str, object, str)

    DOF_KEYS: tuple[str, ...] = ("UX", "UY", "UZ", "RX", "RY", "RZ")

    def __init__(
        self,
        parent: QWidget | None,
        presenter: ModelEditPresenter,
        boundary_name: str,
        *,
        create_mode: bool = False,
        edit_context: BoundaryEditContext | None = None,
    ) -> None:
        self.boundary_name = boundary_name
        self.create_mode = create_mode
        self.edit_context = edit_context or BoundaryEditContext()
        self._scope_candidates: tuple[EditScopeCandidate, ...] = ()
        self._target_candidates: tuple[EditTargetCandidate, ...] = ()
        self._dof_checks: dict[str, QCheckBox] = {}
        self._dof_edits: dict[str, QLineEdit] = {}
        dialog_context = self._build_dialog_context(presenter)
        super().__init__(
            parent,
            presenter,
            kind="boundary",
            name=boundary_name,
            context=dialog_context,
            window_title=f"{'Create' if create_mode else 'Edit'} Boundary",
        )
        self._load_values()

    def _build_dialog_context(self, presenter: ModelEditPresenter) -> ModelEditContext:
        """为创建模式提供壳层上下文。"""

        if not self.create_mode:
            return presenter.build_context("boundary", self.boundary_name)
        preferred_step_name = self.edit_context.preferred_step_name
        return ModelEditContext(
            resolved_kind="boundary",
            object_name=self.boundary_name,
            object_type_label="Boundary",
            owner_label=f"Step: {preferred_step_name}" if preferred_step_name else "Step: 未绑定",
            support_messages=("请至少指定一个目标与一个有效自由度后再提交。",),
        )

    def _build_shell(self) -> None:
        super()._build_shell()
        self.step_combo = QComboBox(self.form_frame)
        self.step_combo.setPlaceholderText("Select a step")
        self.step_hint_label = QLabel(self.form_frame)
        self.step_hint_label.setWordWrap(True)
        self.scope_combo = QComboBox(self.form_frame)
        self.scope_combo.setPlaceholderText("Select a scope")
        self.target_type_combo = QComboBox(self.form_frame)
        self.target_type_combo.addItem("Node", "node")
        self.target_type_combo.addItem("Node Set", "node_set")
        self.target_combo = QComboBox(self.form_frame)
        self.target_combo.setPlaceholderText("Select a target")
        self.target_hint_label = QLabel(self.form_frame)
        self.target_hint_label.setWordWrap(True)

        step_container = QWidget(self.form_frame)
        step_layout = QVBoxLayout(step_container)
        step_layout.setContentsMargins(0, 0, 0, 0)
        step_layout.setSpacing(4)
        step_layout.addWidget(self.step_combo)
        step_layout.addWidget(self.step_hint_label)

        target_container = QWidget(self.form_frame)
        target_layout = QVBoxLayout(target_container)
        target_layout.setContentsMargins(0, 0, 0, 0)
        target_layout.setSpacing(4)
        target_layout.addWidget(self.target_combo)
        target_layout.addWidget(self.target_hint_label)

        dof_container = QWidget(self.form_frame)
        dof_layout = QFormLayout(dof_container)
        dof_layout.setContentsMargins(0, 0, 0, 0)
        for dof_key in self.DOF_KEYS:
            row = QWidget(dof_container)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)
            checkbox = QCheckBox(f"Use {dof_key}", row)
            value_edit = QLineEdit(row)
            value_edit.setEnabled(False)
            value_edit.setPlaceholderText("0.0")
            checkbox.toggled.connect(value_edit.setEnabled)
            checkbox.toggled.connect(self._refresh_submit_state)
            value_edit.textChanged.connect(self._refresh_submit_state)
            row_layout.addWidget(checkbox)
            row_layout.addWidget(value_edit, 1)
            self._dof_checks[dof_key] = checkbox
            self._dof_edits[dof_key] = value_edit
            dof_layout.addRow(dof_key, row)

        self.form_layout.addRow("Step", step_container)
        self.form_layout.addRow("Scope", self.scope_combo)
        self.form_layout.addRow("Target Type", self.target_type_combo)
        self.form_layout.addRow("Target", target_container)
        self.form_layout.addRow("DOF Values", dof_container)

        self.step_combo.currentIndexChanged.connect(self._refresh_step_feedback)
        self.step_combo.currentIndexChanged.connect(self._refresh_submit_state)
        self.scope_combo.currentIndexChanged.connect(self._rebuild_target_choices)
        self.scope_combo.currentIndexChanged.connect(self._refresh_submit_state)
        self.target_type_combo.currentIndexChanged.connect(self._rebuild_target_choices)
        self.target_combo.currentIndexChanged.connect(self._refresh_target_feedback)
        self.target_combo.currentIndexChanged.connect(self._refresh_submit_state)

    def _load_values(self) -> None:
        self._rebuild_step_choices()
        self._rebuild_scope_choices()
        if not self.create_mode:
            boundary = self.presenter.boundary(self.boundary_name)
            self._set_combo_data(self.target_type_combo, boundary.target_type)
        self._rebuild_target_choices()
        if not self.create_mode:
            boundary = self.presenter.boundary(self.boundary_name)
            for dof_key, dof_value in boundary.dof_values.items():
                if dof_key in self._dof_checks:
                    self._dof_checks[dof_key].setChecked(True)
                    self._dof_edits[dof_key].setText(str(dof_value))
        self._refresh_step_feedback()
        self._refresh_target_feedback()
        self._refresh_submit_state()

    def _rebuild_step_choices(self) -> None:
        """重建步骤选择。"""

        step_names = self.presenter.list_step_names()
        preferred_step_name = self.edit_context.preferred_step_name
        if not self.create_mode:
            referenced_steps = self.presenter.boundary_reference_steps(self.boundary_name)
            preferred_step_name = referenced_steps[0] if referenced_steps else preferred_step_name
        self.step_combo.blockSignals(True)
        self.step_combo.clear()
        for step_name in step_names:
            self.step_combo.addItem(step_name, step_name)
        if preferred_step_name in step_names:
            self.step_combo.setCurrentIndex(self.step_combo.findData(preferred_step_name))
        else:
            self.step_combo.setCurrentIndex(-1)
        self.step_combo.setEnabled(bool(step_names))
        self.step_combo.blockSignals(False)

    def _rebuild_scope_choices(self) -> None:
        """重建作用域选择。"""

        self._scope_candidates = self.presenter.list_edit_scope_candidates()
        preferred_scope_name = self.edit_context.preferred_scope_name
        if not self.create_mode:
            preferred_scope_name = self.presenter.boundary(self.boundary_name).scope_name
        self.scope_combo.blockSignals(True)
        self.scope_combo.clear()
        for candidate in self._scope_candidates:
            self.scope_combo.addItem(f"{candidate.scope_name} [{candidate.part_name}]", candidate.scope_name)
        if preferred_scope_name is not None and self.scope_combo.findData(preferred_scope_name) >= 0:
            self.scope_combo.setCurrentIndex(self.scope_combo.findData(preferred_scope_name))
        else:
            self.scope_combo.setCurrentIndex(-1)
        self.scope_combo.setEnabled(bool(self._scope_candidates))
        self.scope_combo.blockSignals(False)

    def _rebuild_target_choices(self) -> None:
        """按当前作用域过滤边界目标。"""

        scope_name = self.current_scope_name()
        target_type = self.current_target_type()
        preferred_target_name = self.edit_context.preferred_target_name
        if not self.create_mode:
            preferred_target_name = self.presenter.boundary(self.boundary_name).target_name
        self._target_candidates = ()
        self.target_combo.blockSignals(True)
        self.target_combo.clear()
        if scope_name is not None and target_type is not None:
            self._target_candidates = self.presenter.list_target_candidates(scope_name=scope_name, target_type=target_type)
            for candidate in self._target_candidates:
                self.target_combo.addItem(candidate.display_label, candidate.target_name)
        if preferred_target_name is not None and self.target_combo.findData(preferred_target_name) >= 0:
            self.target_combo.setCurrentIndex(self.target_combo.findData(preferred_target_name))
        elif self._target_candidates:
            self.target_combo.setCurrentIndex(-1 if self.create_mode else 0)
        else:
            self.target_combo.setCurrentIndex(-1)
        self.target_combo.setEnabled(bool(self._target_candidates))
        self.target_combo.blockSignals(False)

    def _refresh_step_feedback(self) -> None:
        """刷新步骤提示。"""

        if not self.presenter.list_step_names():
            self.step_hint_label.setText("当前模型没有可用 step。请先创建 step，再定义边界。")
            self.owner_value.setText("Step: 未绑定")
        elif self.current_step_name() is None:
            self.step_hint_label.setText("请选择一个 step，边界不会偷偷挂到默认步骤。")
            self.owner_value.setText("Step: 未绑定")
        else:
            self.step_hint_label.setText(f"当前边界将挂接到 step: {self.current_step_name()}")
            self.owner_value.setText(f"Step: {self.current_step_name()}")

    def _refresh_target_feedback(self) -> None:
        """刷新目标联动提示。"""

        if not self._scope_candidates:
            self.target_hint_label.setText("当前模型没有可用 scope，无法指定边界目标。")
        elif self.current_scope_name() is None:
            self.target_hint_label.setText("请先选择 scope，再过滤 target。")
        elif not self._target_candidates:
            self.target_hint_label.setText("当前 scope 下没有可用 target，请切换 scope 或 target type。")
        elif self.current_target_name() is None:
            self.target_hint_label.setText("请选择一个有效 target。")
        else:
            self.target_hint_label.setText(f"当前目标: {self.current_target_name()}")

    def _refresh_submit_state(self) -> None:
        """刷新提交按钮状态。"""

        enabled = self._can_submit()
        self.apply_button.setEnabled(enabled)
        self.ok_button.setEnabled(enabled)

    def _can_submit(self) -> bool:
        """判断当前是否满足最小提交条件。"""

        if self.current_step_name() is None or self.current_scope_name() is None or self.current_target_name() is None:
            return False
        return any(
            checkbox.isChecked() and bool(self._dof_edits[dof_key].text().strip())
            for dof_key, checkbox in self._dof_checks.items()
        )

    def current_step_name(self) -> str | None:
        """返回当前步骤名称。"""

        value = self.step_combo.currentData()
        return None if value in {None, ""} else str(value)

    def current_scope_name(self) -> str | None:
        """返回当前作用域名称。"""

        value = self.scope_combo.currentData()
        return None if value in {None, ""} else str(value)

    def current_target_type(self) -> str | None:
        """返回当前目标类型。"""

        value = self.target_type_combo.currentData()
        return None if value in {None, ""} else str(value)

    def current_target_name(self) -> str | None:
        """返回当前目标名称。"""

        value = self.target_combo.currentData()
        return None if value in {None, ""} else str(value)

    def _collect_dof_values_text(self) -> str:
        """将勾选的自由度汇总为正式写回文本。"""

        items: list[str] = []
        for dof_key in self.DOF_KEYS:
            if not self._dof_checks[dof_key].isChecked():
                continue
            value_text = self._dof_edits[dof_key].text().strip()
            if value_text:
                items.append(f"{dof_key}={value_text}")
        return ", ".join(items)

    def apply_changes(self) -> None:
        operation = "created" if self.create_mode else "updated"
        self.presenter.apply_boundary_editor_update(
            self.boundary_name,
            creating=self.create_mode,
            step_name=self.current_step_name(),
            target_name_text="" if self.current_target_name() is None else self.current_target_name(),
            target_type="" if self.current_target_type() is None else self.current_target_type(),
            scope_name_text="" if self.current_scope_name() is None else self.current_scope_name(),
            dof_values_text=self._collect_dof_values_text(),
        )
        self.create_mode = False
        self.context = self.presenter.build_context("boundary", self.boundary_name)
        self.object_type_value.setText(self.context.object_type_label)
        self.owner_value.setText(self.context.owner_label)
        self._refresh_support_messages()
        self.applied.emit()
        self.modelChanged.emit("boundary", self.boundary_name, operation)


class OutputRequestEditDialog(BaseModelEditDialog):
    """定义输出请求编辑弹窗。"""

    def __init__(self, parent: QWidget | None, presenter: ModelEditPresenter, request_name: str) -> None:
        self.request_name = request_name
        super().__init__(parent, presenter, kind="output_request", name=request_name)
        self._load_values()

    def _build_shell(self) -> None:
        super()._build_shell()
        self.request_mode_combo = QComboBox(self.form_frame)
        self.request_mode_combo.addItem("Field", "field")
        self.request_mode_combo.addItem("History", "history")
        self.variables_edit = QLineEdit(self.form_frame)
        self.target_type_combo = QComboBox(self.form_frame)
        self.target_type_combo.addItem("Model", "model")
        self.target_type_combo.addItem("Node", "node")
        self.target_type_combo.addItem("Node Set", "node_set")
        self.target_type_combo.addItem("Element", "element")
        self.target_type_combo.addItem("Element Set", "element_set")
        self.target_name_edit = QLineEdit(self.form_frame)
        self.scope_name_edit = QLineEdit(self.form_frame)
        self.position_combo = QComboBox(self.form_frame)
        for position_name in ("NODE", "ELEMENT_CENTROID", "INTEGRATION_POINT", "ELEMENT_NODAL", "NODE_AVERAGED", "GLOBAL_HISTORY"):
            self.position_combo.addItem(position_name, position_name)
        self.frequency_edit = QLineEdit(self.form_frame)
        self.semantic_value = QLabel("-", self.form_frame)
        self.semantic_value.setWordWrap(True)
        self.form_layout.addRow("Request Mode", self.request_mode_combo)
        self.form_layout.addRow("Variables", self.variables_edit)
        self.form_layout.addRow("Target Type", self.target_type_combo)
        self.form_layout.addRow("Target Name", self.target_name_edit)
        self.form_layout.addRow("Scope", self.scope_name_edit)
        self.form_layout.addRow("Position", self.position_combo)
        self.form_layout.addRow("Frequency", self.frequency_edit)
        self.form_layout.addRow("Semantics", self.semantic_value)

    def _load_values(self) -> None:
        request = self.presenter.output_request(self.request_name)
        self._set_combo_data(self.request_mode_combo, request.parameters.get("request_mode", "field"))
        self.variables_edit.setText(", ".join(request.variables))
        self._set_combo_data(self.target_type_combo, request.target_type)
        self.target_name_edit.setText("" if request.target_name is None else request.target_name)
        self.scope_name_edit.setText("" if request.scope_name is None else request.scope_name)
        self._set_combo_data(self.position_combo, request.position)
        self.frequency_edit.setText(str(request.frequency))
        self.semantic_value.setText(self.presenter.output_semantics_message(self.request_name))

    def apply_changes(self) -> None:
        self.presenter.apply_output_request_update(
            self.request_name,
            request_mode=str(self.request_mode_combo.currentData()),
            variables_text=self.variables_edit.text(),
            target_type=str(self.target_type_combo.currentData()),
            target_name_text=self.target_name_edit.text(),
            scope_name_text=self.scope_name_edit.text(),
            position=str(self.position_combo.currentData()),
            frequency_text=self.frequency_edit.text(),
        )
        self.context = self.presenter.build_context("output_request", self.request_name)
        self.semantic_value.setText(self.presenter.output_semantics_message(self.request_name))
        self._refresh_support_messages()
        self.applied.emit()


class InstanceTransformDialog(BaseModelEditDialog):
    """定义实例放置变换编辑弹窗。"""

    def __init__(self, parent: QWidget | None, presenter: ModelEditPresenter, instance_name: str) -> None:
        self.instance_name = instance_name
        super().__init__(parent, presenter, kind="instance", name=instance_name)
        self._load_values()

    def _build_shell(self) -> None:
        super()._build_shell()
        self.translation_edit = QLineEdit(self.form_frame)
        self.rotation_row_1_edit = QLineEdit(self.form_frame)
        self.rotation_row_2_edit = QLineEdit(self.form_frame)
        self.rotation_row_3_edit = QLineEdit(self.form_frame)
        self.form_layout.addRow("Translation", self.translation_edit)
        self.form_layout.addRow("Rotation Row 1", self.rotation_row_1_edit)
        self.form_layout.addRow("Rotation Row 2", self.rotation_row_2_edit)
        self.form_layout.addRow("Rotation Row 3", self.rotation_row_3_edit)

    def _load_values(self) -> None:
        instance = self.presenter.instance(self.instance_name)
        self.translation_edit.setText(", ".join(str(value) for value in instance.transform.translation))
        rotation_rows = instance.transform.rotation
        edits = (self.rotation_row_1_edit, self.rotation_row_2_edit, self.rotation_row_3_edit)
        for edit, row in zip(edits, rotation_rows, strict=False):
            edit.setText(", ".join(str(value) for value in row))
        dimension = len(instance.transform.translation) or len(rotation_rows) or 3
        self.rotation_row_3_edit.setVisible(dimension == 3)

    def apply_changes(self) -> None:
        rotation_rows = (
            self.rotation_row_1_edit.text(),
            self.rotation_row_2_edit.text(),
            self.rotation_row_3_edit.text(),
        )
        self.presenter.apply_instance_transform_update(
            self.instance_name,
            translation_text=self.translation_edit.text(),
            rotation_rows=rotation_rows,
        )
        self.context = self.presenter.build_context("instance", self.instance_name)
        self._refresh_support_messages()
        self.applied.emit()


class SectionEditDialog(BaseModelEditDialog):
    modelChanged = Signal(str, object, str)
    """定义截面编辑弹窗。"""

    def __init__(self, parent: QWidget | None, presenter: ModelEditPresenter, section_name: str) -> None:
        self.section_name = section_name
        self._active_material_dialog: QDialog | None = None
        super().__init__(parent, presenter, kind="section", name=section_name)
        self._load_values()

    def _build_shell(self) -> None:
        super()._build_shell()
        self.material_name_combo = QComboBox(self.form_frame)
        self.material_new_button = QPushButton("New...", self.form_frame)
        self.material_edit_button = QPushButton("Edit...", self.form_frame)
        self.material_new_button.setToolTip("Create a material without leaving the current section editor.")
        self.material_edit_button.setToolTip("Edit the currently selected material.")
        self.material_new_button.setToolTip("本轮仅预留入口，后续可直接联动 Materials 管理器。")
        self.material_edit_button.setToolTip("本轮仅预留入口，后续可直接联动 Materials 管理器。")
        material_row = QWidget(self.form_frame)
        material_row_layout = QHBoxLayout(material_row)
        material_row_layout.setContentsMargins(0, 0, 0, 0)
        material_row_layout.setSpacing(6)
        material_row_layout.addWidget(self.material_name_combo, 1)
        material_row_layout.addWidget(self.material_new_button)
        material_row_layout.addWidget(self.material_edit_button)
        self.material_new_button.setToolTip("Create a material without leaving the current section editor.")
        self.material_edit_button.setToolTip("Edit the currently selected material and keep the section selection in sync.")
        self.material_hint_label = QLabel(self.form_frame)
        self.material_hint_label.setWordWrap(True)
        material_container = QWidget(self.form_frame)
        material_container_layout = QVBoxLayout(material_container)
        material_container_layout.setContentsMargins(0, 0, 0, 0)
        material_container_layout.setSpacing(4)
        material_container_layout.addWidget(material_row)
        material_container_layout.addWidget(self.material_hint_label)
        self.region_name_edit = QLineEdit(self.form_frame)
        self.scope_name_edit = QLineEdit(self.form_frame)
        self.primary_value_edit = QLineEdit(self.form_frame)
        self.secondary_value_edit = QLineEdit(self.form_frame)
        self.thickness_edit = QLineEdit(self.form_frame)
        self.form_layout.addRow("Material", material_container)
        self.form_layout.addRow("Region", self.region_name_edit)
        self.form_layout.addRow("Scope", self.scope_name_edit)
        self.form_layout.addRow("Primary Value", self.primary_value_edit)
        self.form_layout.addRow("Secondary Value", self.secondary_value_edit)
        self.form_layout.addRow("Thickness", self.thickness_edit)
        self.material_name_combo.currentIndexChanged.connect(self._refresh_material_controls)
        self.material_new_button.clicked.connect(self._create_material_from_dialog)
        self.material_edit_button.clicked.connect(self._edit_selected_material)

    def _load_values(self) -> None:
        section = self.presenter.section(self.section_name)
        self._reload_material_choices(section.material_name)
        self.region_name_edit.setText("" if section.region_name is None else section.region_name)
        self.scope_name_edit.setText("" if section.scope_name is None else section.scope_name)
        self.primary_value_edit.setText(str(section.parameters.get("area", "")))
        self.secondary_value_edit.setText(str(section.parameters.get("moment_inertia_z", "")))
        self.thickness_edit.setText(str(section.parameters.get("thickness", "")))

    def _reload_material_choices(self, selected_name: str | None) -> None:
        """按当前模型刷新材料下拉框。"""

        material_names = self.presenter.list_material_names()
        self.material_name_combo.blockSignals(True)
        self.material_name_combo.clear()
        if not material_names:
            self.material_name_combo.addItem("No materials available. Click New... to create one.", None)
            self.material_name_combo.setEnabled(False)
            self.material_hint_label.setText("No materials are available in the current model. Use New... to create one, then bind it back to this section.")
            self.material_name_combo.blockSignals(False)
            self._refresh_material_controls()
            return
        for material_name in material_names:
            self.material_name_combo.addItem(material_name, material_name)
        self.material_name_combo.setEnabled(True)
        self.material_hint_label.setText("Material choices are read directly from the current ModelDB materials list.")
        target_name = selected_name if selected_name in material_names else material_names[0]
        self._set_combo_data(self.material_name_combo, target_name)
        self.material_name_combo.blockSignals(False)
        self._refresh_material_controls()

    def _refresh_material_controls(self) -> None:
        """同步材料选择区的空状态与按钮状态。"""

        current_name = self.material_name_combo.currentData()
        has_valid_selection = isinstance(current_name, str) and bool(current_name.strip())
        self.material_new_button.setEnabled(True)
        self.material_edit_button.setEnabled(has_valid_selection)
        if not self.material_name_combo.isEnabled():
            self.material_hint_label.setText("No materials are available in the current model. Use New... to create one, then return here to bind it to this section.")
            return
        if has_valid_selection:
            self.material_hint_label.setText(f"Current material: {current_name}. You can edit it in-place without leaving the section workflow.")
            return
        self.material_hint_label.setText("Select a material for this section, or create one inline with New....")

    def _run_material_dialog(self, dialog_factory) -> bool:
        """执行截面弹窗内部拉起的材料编辑子窗。"""

        dialog = dialog_factory()
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self._active_material_dialog = dialog
        dialog.destroyed.connect(lambda *_args: self._clear_active_material_dialog(dialog))
        dialog_applied = {"value": False}
        if hasattr(dialog, "applied"):
            dialog.applied.connect(lambda: dialog_applied.__setitem__("value", True))
        try:
            result = dialog.exec()
        finally:
            if self._active_material_dialog is dialog:
                self._active_material_dialog = None
        return dialog_applied["value"] or result == QDialog.DialogCode.Accepted

    def _clear_active_material_dialog(self, dialog: QDialog | None = None) -> None:
        """在材料子窗销毁后清空跟踪引用。"""

        if dialog is None or self._active_material_dialog is dialog:
            self._active_material_dialog = None

    def _resolve_material_selection_after_refresh(
        self,
        previous_name: str | None,
        original_names: tuple[str, ...],
        refreshed_names: tuple[str, ...],
    ) -> str | None:
        """在刷新材料列表后尽量保持当前选中项。"""

        if previous_name in refreshed_names:
            return previous_name
        added_names = tuple(sorted(set(refreshed_names) - set(original_names)))
        removed_names = tuple(sorted(set(original_names) - set(refreshed_names)))
        if previous_name in removed_names and len(added_names) == 1:
            return added_names[0]
        return refreshed_names[0] if refreshed_names else None

    def _create_material_from_dialog(self) -> None:
        """在截面编辑流程中直接新建材料。"""

        default_name = self.presenter.suggest_new_material_name()
        material_name, accepted = QInputDialog.getText(self, "Create Material", "Material name:", text=default_name)
        if not accepted:
            return
        normalized_name = str(material_name).strip()
        if not normalized_name:
            QMessageBox.information(self, "Create Material", "Material name cannot be empty.")
            return

        original_selected_name = self.material_name_combo.currentData()
        original_names = self.presenter.list_material_names()
        original_model = self.presenter.snapshot_model()
        original_dirty = self.presenter.model_dirty()
        try:
            self.presenter.create_material(normalized_name)
            committed = self._run_material_dialog(lambda: MaterialEditDialog(self, self.presenter, normalized_name))
            if not committed:
                self.presenter.restore_model(original_model, mark_dirty=original_dirty)
                restored_names = self.presenter.list_material_names()
                self._reload_material_choices(
                    self._resolve_material_selection_after_refresh(
                        original_selected_name if isinstance(original_selected_name, str) else None,
                        original_names,
                        restored_names,
                    )
                )
                return
        except Exception as error:  # noqa: BLE001
            self.presenter.restore_model(original_model, mark_dirty=original_dirty)
            restored_names = self.presenter.list_material_names()
            self._reload_material_choices(
                self._resolve_material_selection_after_refresh(
                    original_selected_name if isinstance(original_selected_name, str) else None,
                    original_names,
                    restored_names,
                )
            )
            QMessageBox.critical(self, "Create Material", str(error))
            return

        self._reload_material_choices(normalized_name)
        self.modelChanged.emit("material", normalized_name, "created")

    def _edit_selected_material(self) -> None:
        """编辑当前截面选中的材料。"""

        selected_name = self.material_name_combo.currentData()
        if not isinstance(selected_name, str) or not selected_name.strip():
            QMessageBox.information(self, "Edit Material", "Select a material first, or create one with New....")
            return

        original_names = self.presenter.list_material_names()
        try:
            committed = self._run_material_dialog(lambda: MaterialEditDialog(self, self.presenter, selected_name))
        except Exception as error:  # noqa: BLE001
            QMessageBox.critical(self, "Edit Material", str(error))
            return
        if not committed:
            self._refresh_material_controls()
            return

        refreshed_names = self.presenter.list_material_names()
        resolved_name = self._resolve_material_selection_after_refresh(selected_name, original_names, refreshed_names)
        self._reload_material_choices(resolved_name)
        self.modelChanged.emit("material", resolved_name or selected_name, "updated")

    def apply_changes(self) -> None:
        material_name = self.material_name_combo.currentData()
        self.presenter.apply_section_update(
            self.section_name,
            material_name_text="" if material_name is None else str(material_name),
            region_name_text=self.region_name_edit.text(),
            scope_name_text=self.scope_name_edit.text(),
            primary_value_text=self.primary_value_edit.text(),
            secondary_value_text=self.secondary_value_edit.text(),
            thickness_text=self.thickness_edit.text(),
        )
        self.context = self.presenter.build_context("section", self.section_name)
        self._refresh_support_messages()
        self.applied.emit()

    def closeEvent(self, event) -> None:
        """关闭截面编辑窗时一并收拢内部材料子窗。"""

        dialog = self._active_material_dialog
        self._active_material_dialog = None
        if dialog is not None:
            dialog.close()
        super().closeEvent(event)
